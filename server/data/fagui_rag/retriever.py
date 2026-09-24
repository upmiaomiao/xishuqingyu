"""
RAG 检索模块（部署到 31.10）
加载 vectors.npy + chunks.jsonl 到内存
retrieve(query, top_k) → 候选 chunk 列表（含元数据 + 分数）

=====================================================================
2026-09-19 改造：语料配额召回 + 引用配额选取 + 副本去重
---------------------------------------------------------------------
问题：报告语料占索引 82.7% 的 chunk（219,258 / 265,248），向量召回天然
      被它占满；报告正文又逐字抄了大量标准条文，于是在向量空间里和
      "依据原文"几乎等价，却有几百个副本在抢位置。实测：
        · "二噁英排放限值"        → top-5 全是报告，标准 0 条 → 答"材料没有"
        · "一般固废 I 类场防渗要求" → 4 条报告 + 1 条标准(还只是标题块) → 拒答
      而"依据"就在库里（GB 18599-2020 / 生活垃圾焚烧污染控制标准）。

办法（三层，都可单独关掉）：
  ① 召回：按语料各留名额，保证依据类一定进候选池（不再被报告淹没）；
  ② 选取：依据类保底条数 —— 问标准/限值类问题保 3 条，案例类问题保 1 条；
  ③ 去重：引用去重键归一化（copy / 副本 / (1) / 通用后缀），
     同一份文件（含它的副本）不再重复占引用位。

开关：RAG_QUOTA_OFF=1 → 完全退回改造前行为（用于 A/B 对比与回滚验证）。
=====================================================================
"""
import json
import os
import re
from pathlib import Path

import numpy as np
import requests

# 索引目录：默认线上目录；可用环境变量指向暂存目录，
# 这样"建暂存索引 → 影子实例验证 → 再切换"这条两阶段上线路径才走得通。
INDEX_DIR = Path(os.environ.get("RAG_INDEX_DIR", "/data/fagui_rag/index"))

BGE_M3_URL = "http://127.0.0.1:34004/v1/embeddings"
BGE_M3_MODEL = "BGE-M3"
BGE_RERANK_URL = "http://127.0.0.1:34005/v1/rerank"
BGE_RERANK_MODEL = "BGE-RERANK-V2-M3"

# ---- 可调参数（全部可用环境变量覆盖，便于线上调参不用改代码）----
QUOTA_OFF = os.environ.get("RAG_QUOTA_OFF") == "1"
# 候选池预算：调用方传的 top_k_vec 是"总预算"的基准，最终预算 = 基准 × 倍数
BUDGET_FACTOR = int(os.environ.get("RAG_BUDGET_FACTOR", "3"))
BUDGET_MIN = int(os.environ.get("RAG_BUDGET_MIN", "48"))
BUDGET_MAX = int(os.environ.get("RAG_BUDGET_MAX", "80"))
# 每个语料在候选池里的保底名额（不求平均，只求"别被挤没"）
MIN_PER_CORPUS = {
    "环评报告": 16,
    "生态环境标准规范": 24,
    "生态环境法律法规": 8,
    "生态环境监管执法": 6,
    "环评导则": 6,
}
# 引用位里依据类的保底条数
AUTH_MIN_DEFAULT = int(os.environ.get("RAG_AUTH_MIN", "2"))
AUTH_MIN_STRICT = int(os.environ.get("RAG_AUTH_MIN_STRICT", "3"))
AUTH_MIN_CASE_Q = int(os.environ.get("RAG_AUTH_MIN_CASE_Q", "1"))
# 依据类的"邻块扩展"：标准的条文是连续读的，命中「5.2 I 类场技术要求」这种标题块时，
# 具体的数值往往在紧邻的下一块里。实测 GB 18599-2020 的 5.2.1（含 1.0×10⁻⁵ cm/s）
# 就是因为没进候选池，才导致回答只能"拒答"。
NEIGHBOR_EXPAND = os.environ.get("RAG_NEIGHBOR_EXPAND", "1") == "1"
NEIGHBOR_TOP = int(os.environ.get("RAG_NEIGHBOR_TOP", "12"))
# 依据类"顶上来"的最低重排分（防呆：分数太低的不硬塞）
AUTH_FLOOR = float(os.environ.get("RAG_AUTH_FLOOR", "0.2"))
# 依据类还要过一个"相对底线"：低于「本批最高分 - AUTH_GAP」的依据一律不保底。
# 实测教训：不加这条时，“未批先建的法律责任”会被硬塞进《河北省非煤矿山综合治理条例》
# （0.657 vs 本批最高 0.978），把真正该引的《未批先建类案件学习要点》挤下去。
AUTH_GAP = float(os.environ.get("RAG_AUTH_GAP", "0.25"))
# 「带数值的块」加权：问限值/标准要求时，重排器会偏好"提到关键词"的块，
# 而不是"装着答案数值"的块。实测 GB 18599-2020 里：
#   #12「…5.1.4 施工质量…5.2 I 类场技术要求」重排 0.9858 ← 只有标题
#   #15「6.1 进入 I 类场…应同时满足」        重排 0.9661 ← 讲的是入场要求
#   #13「5.2.1 天然基础层饱和渗透系数不大于 1.0×10⁻⁵ cm/s…」重排 0.8430 ← 才是答案
# 前两条会把真答案挤出引用位，于是"有引用、答不出数"。这里给带限值/单位/量级的块
# 一个小的排序加成（只影响排序，不改输出里的 rerank_score）。
RE_NUMERIC = re.compile(
    r"10\^?\{?-?\d+|×\s*10|\\times\}\s*10|"
    r"mg\s*/\s*[mLm³]|µg|μg|ng\s*/|cm\s*/\s*s|m\s*/\s*s|"
    r"限值|排放浓度|不大于|不应大于"
)
NUM_BONUS = float(os.environ.get("RAG_NUM_BONUS", "0.15"))
# 同一份文档在引用列表里最多占几条。
# 案例类取 3：一份环评报告的不同章节块（现状、工艺、环境影响、措施）对回答确有用；
# 取 1 会白白浪费引用位（实测济宁那条会只剩 1 条相关块）。
PER_DOC_CAP_AUTH = int(os.environ.get("RAG_PER_DOC_CAP_AUTH", "2"))
PER_DOC_CAP_CASE = int(os.environ.get("RAG_PER_DOC_CAP_CASE", "3"))
# 「已废止」降权：索引里还留着 2,519 块 status=已废止 的正文（以大气移动源标准为主，
# 语料归档不删除）。2026-09-21 实测：问 HG/T 3650-2012 时引到了两条作废标准
# （《三轮汽车和低速货车用柴油机排气污染物排放限值及测量方法》《研究堆运行安全规定》），
# 与问题毫无关系却占掉引用位。这里只降排序分与保底判定，**不改输出里的 rerank_score**，
# 前端仍能看到原始分与 status=已废止 的标注。
ABOLISHED_PENALTY = float(os.environ.get("RAG_ABOLISHED_PENALTY", "0.35"))
ABOLISHED_STATUS = ("已废止", "废止", "已失效", "已作废")

# 语料分类：按 source 顶层目录
AUTHORITY_CORPORA = ("生态环境标准规范", "生态环境法律法规", "环评导则")

# 问句意图识别（纯正则，不调模型）
RE_STD_CODE = re.compile(r"(GB|HJ|DB)\s*[/T]*\s*\d{2,5}", re.I)
RE_AUTH_Q = re.compile(
    r"限值|标准值|排放浓度|排放标准|评价等级|等级判定|适用范围|分类管理名录|名录|"
    r"法律责任|罚款|处罚|有效期|是否有效|现行|作废|编制依据|技术导则|导则|"
    r"防护距离|临界量|风险潜势|评价工作等级|判定依据|"
    r"防渗要求|技术要求|标准要求|排放要求|指标要求|要求是什么|规定是什么|怎么规定"
)
RE_CASE_Q = re.compile(
    r"项目|工程|公司|有限公司|厂|案例|这家|该企业|建设内容|生产工艺|产污环节|防治措施|"
    r"总投资|占地面积|环境影响报告书|环境影响报告表"
)
# 文档名归一：这些尾巴不改变"这是同一份文件"
DOC_SUFFIXES = (
    "环境影响报告书", "环境影响报告表", "环境影响报告", "环境影响评价",
    "环评报告书", "环评报告表", "环评报告", "环评书", "环评表",
    "报告书", "报告表", "全文", "全本", "文本", "终稿", "最终稿",
    "公示版", "公示稿", "送审版", "报批稿", "pdf版", "压缩版", "正文", "全本公示",
)
RE_COPY_TAIL = re.compile(r"[\s_\-]*(\bcopy\b|副本|拷贝)\s*$", re.I)
RE_NUM_TAIL = re.compile(r"\s*[（(]\s*\d+\s*[）)]\s*$")
RE_PUNCT = re.compile(r"[\s\u3000_\-—－–·．.,，。、:：;；()（）\[\]【】{}<>《》\"'`]+")


def doc_key(source: str) -> str:
    """引用去重键：把同一份文件的副本归一到一个键。

    线上实测到的三种重复形态都要能合并：
      · 「环评气化80t 宜川县.md」与「… copy.md」（差 5 字节）
      · 「x电梯配件…新建项目.md」与「…新建项目环境影响报告.md」
      · 「济宁市…报告书.md」与「…报告书 copy.md」
    """
    s = source or ""
    if s.endswith(".md"):
        s = s[:-3]
    s = RE_COPY_TAIL.sub("", s)
    s = RE_NUM_TAIL.sub("", s).strip()
    corpus = s.split("/")[0]
    base = s.split("/")[-1]
    n = RE_PUNCT.sub("", base).lower()
    # 反复剥尾巴：「…环评报告书全本」要剥两次才能和「…环评报告书」对上。
    for _ in range(3):
        for suf in DOC_SUFFIXES:
            # 剥掉尾巴后至少还剩 6 个字符才允许剥：
            # 否则「环评报告」「环评报告表」这种短名会被剥成空串或同一个键，
            # 把真正不同的文件误并到一起。
            if n.endswith(suf) and len(n) - len(suf) >= 6:
                n = n[: -len(suf)]
                break
        else:
            break
    return f"{corpus}|{n}"


def corpus_of(meta: dict) -> str:
    return (meta.get("source") or "").split("/")[0]


def is_authority(meta: dict) -> bool:
    return corpus_of(meta) in AUTHORITY_CORPORA


def is_abolished(meta: dict) -> bool:
    """这块正文是否来自已废止的文档（索引元数据 status 字段）。"""
    return str(meta.get("status") or "").strip() in ABOLISHED_STATUS


def auth_need(query: str) -> int:
    """这条问题该给依据类保底几个引用位。"""
    if RE_STD_CODE.search(query) or RE_AUTH_Q.search(query):
        return AUTH_MIN_STRICT
    if RE_CASE_Q.search(query):
        return AUTH_MIN_CASE_Q
    return AUTH_MIN_DEFAULT


# ---------------------------------------------------------------------------
# 标准号"硬命中"（2026-09-22 第三批，B5 的修法）
#
# 现象（实测，非推测）：问「GB8978总汞0.05 mg/L，是排到哪类排放口？是三级标准吗？」
# 召回 72 块里**一条 8978 的块都没有**，最终 5 条引用全是环评报告；
# 而把问法换成"标准原文式"（《污水综合排放标准》第一类污染物在车间…采样），
# 该标准的块立刻排到第 4 名。也就是说：**标准号是确定性线索，却被当成普通语义在碰运气**。
# 后果是模型从头到尾没见过该标准的原文 —— 再怎么改提示词都救不回来。
#
# 所以这里做两件确定性的小事，只在"题面确实点名了标准号"时生效：
#   ① 召回阶段：把该标准自己的块按相似度注入候选池（否则重排再准也没用）；
#   ② 挑选阶段：保证最终引用里至少有一块来自被点名的标准（否则等于问了个寂寞）。
# 环境变量可一键关掉回滚：RAG_STD_PIN=0（注入条数 RAG_STD_PIN_POOL / 保底条数 RAG_STD_PIN_FINAL）。
# ---------------------------------------------------------------------------
RE_CODE_TOKEN = re.compile(r"(GB|HJ|DB)\s*/?\s*T?\s*(\d{2,5})", re.I)
STD_PIN_ON = os.environ.get("RAG_STD_PIN", "1") != "0"
STD_PIN_POOL = int(os.environ.get("RAG_STD_PIN_POOL", "6"))
STD_PIN_FINAL = int(os.environ.get("RAG_STD_PIN_FINAL", "2"))


def codes_in(text: str) -> set:
    """题面里出现的标准号数字核心：GB8978 / GB 8978-1996 / HJ 544—2016 → {8978}/{544}。"""
    return {m.group(2) for m in RE_CODE_TOKEN.finditer(text or "")}


def code_of(meta: dict) -> str:
    """这一块属于哪个标准号（先看 standard_id，再退回标题/路径里的编号）。"""
    for field in ("standard_id", "title", "source"):
        for m in RE_CODE_TOKEN.finditer(str(meta.get(field) or "")):
            return m.group(2)
    return ""


def _bigrams(text: str) -> set:
    """中文字符二元组 —— 只用来做字面重合度，不做分词（不引依赖）。"""
    zh = re.sub(r"[^\u4e00-\u9fa5]", "", text or "")
    return {zh[i:i + 2] for i in range(len(zh) - 1)}


_TERM_CACHE: dict = {}


def query_terms(text: str) -> set:
    """题面的"内容词"字面特征：中文二元组 + 数值 + 字母数字词。

    为什么不用分数硬挑（这是 B5 第一版栽的跟头）：第一版只按 rerank 分把该标准
    最"像"的块补进来，结果补的是《污水综合排放标准》的**标准分级**那一块
    （讲一级/二级/三级），模型据此答成"存在三级标准"—— 反而更错。
    真正要的是含"第一类污染物""车间排放口""总汞"**字面**的那一块，
    而这类"法典条文式"的块与口语化提问的语义相似度天生不高，只能靠字面兜。
    """
    if text in _TERM_CACHE:
        return _TERM_CACHE[text]
    terms = _bigrams(text)
    terms |= {m.group(0).lower() for m in re.finditer(r"\d+(?:\.\d+)?", text or "")}
    _TERM_CACHE[text] = terms
    return terms


class Retriever:
    def __init__(self, index_dir: Path = INDEX_DIR, quota: bool | None = None):
        self.index_dir = Path(index_dir)
        # quota=False 完全退回改造前行为（A/B 对比、回滚验证用）
        self.quota = (not QUOTA_OFF) if quota is None else quota
        self._key_cache: dict[str, str] = {}
        self._load()

    def _load(self):
        self.vectors = np.load(self.index_dir / "vectors.npy")
        norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
        self.vectors_norm = self.vectors / np.maximum(norms, 1e-8)

        self.chunks = []
        with open(self.index_dir / "chunks.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                self.chunks.append(json.loads(line))

        assert len(self.chunks) == self.vectors.shape[0]

        # 语料 → chunk 下标（召回阶段按语料切分用；启动时算一次）
        buckets: dict[str, list[int]] = {}
        for i, c in enumerate(self.chunks):
            buckets.setdefault(corpus_of(c), []).append(i)
        self.corpus_idx = {k: np.asarray(v, dtype=np.int64) for k, v in buckets.items()}
        print(f"[Retriever] {len(self.chunks)} chunks, dim={self.vectors.shape[1]}, "
              f"语料 {len(self.corpus_idx)} 个: "
              + ", ".join(f"{k}={len(v)}" for k, v in sorted(self.corpus_idx.items())))
        print(f"[Retriever] 语料配额 {'开启' if self.quota else '关闭（改造前行为）'}")

    def embed(self, text: str) -> np.ndarray:
        r = requests.post(
            BGE_M3_URL,
            json={"model": BGE_M3_MODEL, "input": [text]},
            timeout=30,
        )
        r.raise_for_status()
        return np.array(r.json()["data"][0]["embedding"], dtype=np.float32)

    def _key(self, source: str) -> str:
        k = self._key_cache.get(source)
        if k is None:
            k = doc_key(source)
            self._key_cache[source] = k
        return k

    def search(self, query_vec: np.ndarray, top_k: int = 20):
        q = query_vec / max(np.linalg.norm(query_vec), 1e-8)
        sims = self.vectors_norm @ q
        if top_k >= len(sims):
            idxs = np.argsort(-sims)
        else:
            idxs = np.argpartition(-sims, top_k)[:top_k]
            idxs = idxs[np.argsort(-sims[idxs])]
        return [(int(i), float(sims[i])) for i in idxs]

    def recall(self, query_vec: np.ndarray, top_k_vec: int = 20, codes: set | None = None,
               terms: set | None = None):
        """召回候选。开启配额时：每个语料先各占名额，再按全局相似度补足预算。

        这一步是整个改造的关键 —— 全局 top-60 里塞得下 219,258 个报告 chunk，
        标准的块连候选池都进不来，后面重排再准也救不回来。
        """
        if not self.quota:
            return self.search(query_vec, top_k=top_k_vec)

        q = query_vec / max(np.linalg.norm(query_vec), 1e-8)
        sims = self.vectors_norm @ q

        budget = max(BUDGET_MIN, min(BUDGET_MAX, top_k_vec * BUDGET_FACTOR))
        picked: dict[int, float] = {}
        for corpus, idxs in self.corpus_idx.items():
            quota = min(MIN_PER_CORPUS.get(corpus, 4), len(idxs), budget)
            sub = sims[idxs]
            if quota >= len(sub):
                top_local = np.argsort(-sub)
            else:
                top_local = np.argpartition(-sub, quota)[:quota]
                top_local = top_local[np.argsort(-sub[top_local])]
            for j in top_local:
                picked[int(idxs[j])] = float(sub[j])

        if len(picked) < budget:
            for i in np.argsort(-sims):
                if len(picked) >= budget:
                    break
                picked.setdefault(int(i), float(sims[i]))

        if NEIGHBOR_EXPAND:
            # 邻块扩展允许在预算之外追加（上限 budget + NEIGHBOR_TOP）：
            # 上面那一步已经把池子填到 budget，若共用同一个上限就永远扩不进来。
            self._expand_neighbors(picked, sims, budget + NEIGHBOR_TOP)

        # 标准号硬命中：题面点名了 GB/HJ/DB 编号，就把该标准自己的块补进池子。
        # 补哪几块不只看相似度，还要看**字面重合**（见 query_terms 的注释：只按分数挑，
        # 会挑到"标准分级"这种看着相关、实则把模型带偏的块）。
        # 允许超出预算（只在依据语料上、条数很少），否则"补进来"和"被预算挡住"会打架。
        if STD_PIN_ON and codes:
            terms = terms or set()
            mine = []
            for i in np.argsort(-sims):
                idx = int(i)
                c = self.chunks[idx]
                if code_of(c) not in codes:
                    continue
                text = c.get("text") or ""
                overlap = len(terms & _bigrams(text))
                mine.append((overlap, float(sims[idx]), idx))
                if len(mine) >= 400:          # 该标准的块不会太多，扫够了就停
                    break
            # 字面重合优先、相似度次之；重合为 0 的也要（保底给原文，不给报告转述）
            mine.sort(key=lambda t: (-t[0], -t[1]))
            added = 0
            for _ov, _sim, idx in mine:
                if added >= STD_PIN_POOL:
                    break
                if idx in picked:
                    continue
                picked[idx] = float(sims[idx])
                added += 1
            if added:
                print(f"[Retriever] 标准号硬命中：补入 {added} 块"
                      f"（{','.join(sorted(codes))}，最高字面重合 "
                      f"{mine[0][0] if mine else 0}）")

        out = sorted(picked.items(), key=lambda kv: -kv[1])
        return [(i, s) for i, s in out]

    def _expand_neighbors(self, picked: dict, sims, budget: int) -> None:
        """给依据类命中的块补上同文档的紧邻块（±1），原地写入 picked。

        只在依据语料上做：标准/法规/导则的条文连续，命中了条标题却没命中数值
        是最要命的失败形态（"有引用、但答不出数"）。
        """
        added = 0
        for idx in sorted(picked, key=lambda i: -picked[i]):
            if added >= NEIGHBOR_TOP or len(picked) >= budget:
                break
            src = self.chunks[idx].get("source") or ""
            if src.split("/")[0] not in AUTHORITY_CORPORA:
                continue
            for nb in (idx + 1, idx - 1):
                if len(picked) >= budget or added >= NEIGHBOR_TOP:
                    break
                if not (0 <= nb < len(self.chunks)):
                    continue
                if (self.chunks[nb].get("source") or "") != src:
                    continue          # 不许跨文档扩展
                if nb in picked:
                    continue
                picked[int(nb)] = float(sims[nb])
                added += 1

    @staticmethod
    def _collapse_copies(cands: list):
        """按引用去重键折叠候选，同一份文件（含副本）只留一条。

        **只在重排之后用**，不要在重排之前用：实测把"每份文档留向量最高的那块"
        提前到重排前，会留下"向量像、重排不像"的块，把"向量次高但重排 0.99"的块
        扔掉 —— 济宁那条问题的引用分因此从 0.9945 掉到 0.3584。
        """
        best: dict[str, tuple] = {}
        for idx, sim, meta in cands:
            k = doc_key(meta.get("source") or "")
            cur = best.get(k)
            if cur is None or (sim or 0) > (cur[1] or 0):
                best[k] = (idx, sim, meta)
        return [best[k] for k in sorted(best, key=lambda k: -(best[k][1] or 0))]

    def rerank(self, query: str, candidates: list, top_k: int = 5):
        docs = [c[2]["text"] for c in candidates]
        r = requests.post(
            BGE_RERANK_URL,
            json={"model": BGE_RERANK_MODEL, "query": query, "documents": docs},
            timeout=60,
        )
        r.raise_for_status()
        results = r.json()["results"]
        results.sort(key=lambda x: -x["relevance_score"])
        out = []
        for r_ in results[:top_k]:
            idx_in_candidates = r_["index"]
            meta = candidates[idx_in_candidates][2]
            out.append({
                **meta,
                "rerank_score": float(r_["relevance_score"]),
                "vec_sim": float(candidates[idx_in_candidates][1]),
            })
        return out

    def _select(self, scored: list, top_k_final: int, n_auth: int,
                strict: bool = False, pins: set | None = None,
                terms: set | None = None) -> list:
        """按分数选引用，但给依据类留保底位，并把副本/同文档挡在外面。

        保底有两条底线：绝对分 AUTH_FLOOR、相对分（本批最高分 - AUTH_GAP）。
        依据只有在够得着这两条线时才占保底位，避免把不相关的法规硬塞给用户。

        strict=True（问的是限值/标准要求）时，给"带数值的依据块"加排序权重，
        让装着答案的那一块能进引用位，而不是被"提到关键词"的块挤掉。
        """
        picked: list = []
        picked_ids: set[int] = set()
        per_doc: dict[str, int] = {}

        def bonus(c: dict) -> float:
            if not (strict and is_authority(c)):
                return 0.0
            return NUM_BONUS if RE_NUMERIC.search(c.get("text") or "") else 0.0

        def eff(c: dict) -> float:
            """排序/保底判定用的有效分：已废止扣分（输出里的 rerank_score 不变）。"""
            s = (c.get("rerank_score") or 0.0) + bonus(c)
            return s - ABOLISHED_PENALTY if is_abolished(c) else s

        scores = [eff(c) for c in scored]
        top_score = max(scores) if scores else 0.0
        auth_line = max(AUTH_FLOOR, top_score - AUTH_GAP)

        order = sorted(scored, key=lambda c: -eff(c))

        def take(c: dict) -> bool:
            cid = id(c)
            if cid in picked_ids:
                return False
            k = self._key(c.get("source") or "")
            cap = PER_DOC_CAP_AUTH if is_authority(c) else PER_DOC_CAP_CASE
            if per_doc.get(k, 0) >= cap:
                return False
            per_doc[k] = per_doc.get(k, 0) + 1
            picked.append(c)
            picked_ids.add(cid)
            return True

        if n_auth > 0:
            for c in order:
                if sum(1 for p in picked if is_authority(p)) >= n_auth:
                    break
                if is_authority(c) and (c.get("rerank_score") or 0.0) >= auth_line:
                    take(c)

        # 题面点名的标准，必须在引用里出现（B5：问的是 GB8978，结果 5 条引用全是报告）。
        # 挑哪一块要与召回一致：**先看字面重合**，再看有效分 ——
        # 否则会把该标准里"看着像"的分级块顶上来，反而把模型带偏（B5 第一版实测）。
        if STD_PIN_ON and pins:
            terms = terms or set()

            def pin_key(c: dict):
                return (-len(terms & _bigrams(c.get("text") or "")), -eff(c))

            for c in sorted(order, key=pin_key):
                if sum(1 for p in picked if code_of(p) in pins) >= STD_PIN_FINAL:
                    break
                if code_of(c) in pins:
                    take(c)

        for c in order:
            if len(picked) >= top_k_final:
                break
            take(c)

        # 去重把名额卡住时，放宽限制补足（宁可重复，也不少于用户要的条数）
        if len(picked) < top_k_final:
            for c in order:
                if len(picked) >= top_k_final:
                    break
                if id(c) not in picked_ids:
                    picked.append(c)
                    picked_ids.add(id(c))
        return picked[:top_k_final]

    def retrieve(self, query: str, top_k_vec: int = 20, top_k_final: int = 5):
        qv = self.embed(query)
        codes = codes_in(query) if (STD_PIN_ON and self.quota) else set()
        terms = query_terms(query) if codes else set()
        hits = self.recall(qv, top_k_vec=top_k_vec, codes=codes, terms=terms)
        candidates = [(idx, sim, self.chunks[idx]) for idx, sim in hits]
        n_auth = auth_need(query) if self.quota else 0
        strict = self.quota and n_auth >= AUTH_MIN_STRICT
        try:
            scored = self.rerank(query, candidates, top_k=max(len(candidates), top_k_final))
        except Exception as e:
            print(f"[Retriever] rerank failed ({e}), fallback to vec only")
            scored = [{**c[2], "vec_sim": c[1], "rerank_score": None} for c in candidates]
        if not self.quota:
            return scored[:top_k_final]
        return self._select(scored, top_k_final, n_auth, strict=strict, pins=codes, terms=terms)


if __name__ == "__main__":
    r = Retriever()
    queries = [
        "排污许可证的有效期是多久？",
        "未批先建的法律责任和罚款幅度",
        "GB 18599 一般工业固体废物贮存的标准要求",
        "河北省大气污染防治条例对工业污染如何规定",
        "中央生态环境保护督察通报了哪些典型案例",
        "危险废物鉴别的国家标准是什么",
        "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
        "二噁英的排放限值是多少？",
        "济宁市生活垃圾焚烧发电二期改扩建项目的主要环境问题是什么？",
    ]
    for q in queries:
        print(f"\n{'=' * 80}\nQ: {q}   [依据保底 {auth_need(q)} 条]")
        for i, c in enumerate(r.retrieve(q, top_k_final=5), 1):
            rr = c.get("rerank_score")
            print(f"  [{i}] type={c.get('type'):<12} {'依据' if is_authority(c) else '案例'} "
                  f"rerank={rr if rr is None else round(rr, 4)}")
            print(f"      {c.get('source')}")
