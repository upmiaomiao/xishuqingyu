# -*- coding: utf-8 -*-
"""把判定结果 + 填报数据组装成 Word（.docx）草稿。

三条硬规矩：
  ① **只渲染确定的东西**：判定类内容（名录档级、专项评价、保护目标表、设备表…）
     由代码填；填报里没有的，写「需人工补充」并说明缺什么，绝不编一个像样的值。
  ② 输出必须是**草稿**：文末「生成说明」列出判定依据与需人工确认项，
     并明确写"不得直接作为报批件" —— 免得被当成已完成件。
  ③ 同一份填报 → 同一份文件（**字节级**）：docx 内置时间戳固定 + zip 容器时间戳归一化
     （见 `_normalize_zip`），不写"生成时间"，日期栏留给使用者填。
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
import zipfile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Cm

FIXED_TS = datetime.datetime(2026, 1, 1, 0, 0, 0)   # 固定时间戳 → 可复现


def _normalize_zip(path: str) -> None:
    """把 docx 的 zip 容器时间戳全部固定为 FIXED_TS。

    为什么必须做：python-docx 写包时，每个 zip 条目的 date_time 取**生成时的墙上时钟**，
    精度 2 秒 —— 于是"同一份填报生成两次"只在同一个 2 秒窗口内字节相同，
    跨窗口就不同。**之前单测的"字节级一致"是撞窗口撞上的，不是真可复现**
    （单测加了 3 秒间隔后立刻暴露）。这里重写一遍容器，条目顺序与压缩方式保持原样。
    """
    tmp = path + ".norm"
    with zipfile.ZipFile(path) as src, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=FIXED_TS.timetuple()[:6])
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.create_system = 0
            dst.writestr(zi, src.read(info.filename))
    shutil.move(tmp, path)
TODO = "【需人工补充】"

# ---------------------------------------------------------------- 补写与「待补充清单」
# 2026-09-24，用户要求：右侧要能看到"成稿里还缺哪些"、并且**就地补上**再重新生成。
# 两个配套的小机制：
#   ① `data["_补写"]`：{小节名: 用户写的正文}。会话侧存、生成时随 data 带过来，
#      正文里那几处**写死**的占位（规划符合性、三线一单、施工期措施、结论）优先用它。
#      为什么塞进 data 的下划线键：`schema.validate()` 明确跳过下划线开头的键
#      （那是给内部留的口子），于是不用改 build() 的签名就能把它从会话一路带到渲染层。
#   ② `_scan_gaps()`：**渲染完回扫一遍 docx**（正文 + 表格），把所有还写着【需人工补充】的
#      位置逐条记下来。为什么不在这 20 多处渲染时顺手记：那样迟早漏一处；
#      回扫"以产出的文件为准"，一份不漏，也不会记下其实已经填上的项。
_SECTION_KEYS = (
    ("规划及规划环境影响评价符合性分析", "规划符合性分析"),
    ("其他符合性分析", "其他符合性分析"),
    ("施工期环境保护措施", "施工期环境保护措施"),
    ("从环境保护角度", "结论"),
)
# 生成说明里那句"凡标注【需人工补充】的位置…"本身带着这个词，回扫时要跳过，
# 否则每份稿子都会多出一条假缺口。
_GAP_SKIP = ("位置，是填报信息里没有", "本稿**不得直接作为报批件**")


def _fill(data: dict, key: str) -> str:
    """用户在小节里补写的正文（没补写就返回空串，由调用处决定写不写占位）。"""
    return str(((data or {}).get("_补写") or {}).get(key) or "").strip()


def _norm_label(s: str) -> str:
    """把成稿里的标签归一成"能和字段名对上"的形式。

    成稿里的标签常带两样字段名里没有的东西：
      · 编号前缀：「4. 主要工艺流程和产排污环节」→「主要工艺流程和产排污环节」；
      · 末尾单位括号：「用地（用海）面积（m²）」→「用地（用海）面积」、「环保投资（万元）」→「环保投资」。
    只去**末尾**那对括号 —— 字段名本身就带括号（如「用地（用海）面积」），全去掉反而对不上。
    """
    s = re.sub(r"^\s*[0-9]+\s*[.、]\s*", "", str(s or "").strip())
    s = re.sub(r"（[^（）]*）\s*$", "", s).strip()
    return s


def _scan_gaps(doc) -> list:
    """回扫成稿，逐条记下还空着的位置。

    返回 [{位置, 标签, 键, 类型, 片段}]：`键` 是能直接改的东西 ——
    命中了字段就是字段 key（改它 = 填事实表），命中了正文小节就是小节名（改它 = 补写正文）；
    两种都没命中的只有 `标签` 与 `片段`（界面只展示、不给编辑框，免得乱写进不去文档）。
    """
    from gen import schema
    byname = {}
    for f in schema.FIELDS:
        byname[f.name] = f.key
        byname.setdefault(f.key, f.key)
    fields = set(byname.values())

    def match(label: str) -> str:
        raw = str(label or "").strip()
        if raw in byname:
            return byname[raw]
        lab = _norm_label(raw)
        if lab in byname:
            return byname[lab]
        # 包含式兜底：「4. 主要工艺流程和产排污环节」这类带后缀的标签，取**最长**的命中字段名
        # （最短的容易误配：比如「建设地点」会命中「建设地点坐标」这种更长的字段）。
        hits = [n for n in byname if len(n) >= 3 and n in lab]
        return byname[max(hits, key=len)] if hits else ""

    rows = []

    def add(where: str, label: str, text: str):
        # **先认正文小节，再认字段**：`施工期环境保护措施` 会被包含式兜底命中字段「环保措施」
        # （4 个字包含在里面），于是那一处本该"补写正文"的缺口被指成了"去填环保措施表"——
        # 本机自测当场抓到。正文小节是写死的四段，名字精确，优先判定没有歧义。
        key, kind = "", ""
        for pre, k in _SECTION_KEYS:
            if pre in str(label) or pre in str(text):
                key, label, kind = k, pre, "补写"
                break
        if not key:
            key = match(label)
            kind = "字段" if key in fields else ""
        rows.append({"位置": where, "标签": str(label)[:40], "键": key, "类型": kind,
                     "片段": str(text)[:150]})

    for tb in doc.tables:
        for row in tb.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) >= 2 and TODO in cells[1]:
                add("表格", cells[0] or "（无标签）", " | ".join(cells))
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if TODO not in t or any(s in t for s in _GAP_SKIP):
            continue
        add("正文", (t.split("：")[0] if "：" in t else t[:20]), t)
    return rows


def _font(run, name="仿宋", size=12, bold=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def _para(doc, text="", size=12, bold=False, align=None, name="仿宋", space_after=4):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    if text:
        _font(p.add_run(text), name=name, size=size, bold=bold)
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _h(doc, text, size=14):
    return _para(doc, text, size=size, bold=True, name="黑体", space_after=6)


def _kv_table(doc, rows, widths=(4.2, 11.5)):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in rows:
        cells = t.add_row().cells
        _font(cells[0].paragraphs[0].add_run(str(k)), name="黑体", size=10.5)
        _font(cells[1].paragraphs[0].add_run(str(v if v not in (None, "", []) else TODO)),
              name="仿宋", size=10.5)
        cells[0].width, cells[1].width = Cm(widths[0]), Cm(widths[1])
    return t


def _list_table(doc, header, rows):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, h in enumerate(header):
        _font(t.rows[0].cells[i].paragraphs[0].add_run(str(h)), name="黑体", size=10.5)
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            _font(cells[i].paragraphs[0].add_run("" if v is None else str(v)),
                  name="仿宋", size=10.5)
    return t


def _spec_text(dec: dict) -> str:
    """专项评价设置情况：应设的列出并附依据，未定的写明待确认，不设的写「无」。"""
    rows = dec["专项评价"]["要素"]
    yes = [r for r in rows if r.get("set_special") is True]
    unk = [r for r in rows if r.get("status") == "unknown" and r.get("set_special") is not True]
    if yes:
        parts = [f"{r['element']}（{r['reason']}）" for r in yes]
        s = "应设置专项评价：" + "；".join(parts) + "。"
    else:
        s = "无。"
    if unk:
        s += "（以下要素因事实不足未能定论，须人工确认：" + \
             "；".join(f"{r['element']}——{r['reason']}" for r in unk) + "）"
    q = dec["专项评价"]["数量上限"]
    s += f"\n数量核查：已定应设 {q['已定应设']} 项，上限 {q['上限']} 项（{q['依据']}）"
    s += "，未超限。" if not q["超出"] else "，**已超限**，须重新核定。"
    return s


def _cat_text(dec: dict) -> str:
    c = dec["名录"]
    if c.get("decided"):
        return (f"应编制环境影响报告{'书' if c['tier'] == '报告书' else '表'}。"
                f"依据《建设项目环境影响评价分类管理名录》：序号{c.get('名录序号')}"
                f"「{c.get('名录条目')}」——报告书条件：{c.get('报告书条件') or '无'}；"
                f"报告表条件：{c.get('报告表条件') or '无'}。{c.get('理由')}")
    return (f"名录档级**未能自动确定**，倾向「{c.get('倾向档位') or '不确定'}」。"
            f"命中条目：序号{c.get('名录序号')}「{c.get('名录条目')}」。"
            f"原因：{c.get('理由')}。须人工核定后再定稿。")


def _narr(doc, narration, name: str):
    """把某小节的模型叙述（已过出处闸门）写进正文；没有就不写占位（正文里已给【需人工补充】）。"""
    if not narration:
        return
    v = (narration.get("小节") or {}).get(name)
    if not v or not v.get("正文"):
        return
    _para(doc, "　" + v["正文"], size=10.5)


def build(data: dict, dec: dict, path: str, host: str = "", narration: dict = None,
          evidence: dict = None, gaps: list = None) -> str:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "仿宋"
    st.font.size = Pt(12)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "仿宋")
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(3.0)

    # ---------------- 封面 ----------------
    _para(doc, "", size=12)
    _para(doc, "建设项目环境影响报告表", size=22, bold=True, name="黑体",
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)
    _para(doc, "（污染影响类）", size=14, bold=True, name="黑体",
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=40)
    _kv_table(doc, [
        ("项目名称", data.get("项目名称")),
        # 建设单位/编制单位/编制日期：**读真实值**（2026-09-24 改）。
        # 原先这三格是写死的常量，于是"用户在对话里说了编制单位"永远进不了封面 ——
        # 字段表也补上了这三项（见 schema.py），缺了就照旧写【需人工补充】。
        ("建设单位", data.get("建设单位")),
        ("编制单位", data.get("编制单位")),
        # 日期栏**不替用户写今天**（同一份填报要能字节级复现，见文件头规矩③）：
        # 填了就用他填的，没填就留空表格线，和手填的表格一样。
        ("编制日期", data.get("编制日期") or "     年    月"),
    ])
    doc.add_page_break()

    # ---------------- 生成说明（放在最前，避免被误当完成件） ----------------
    _h(doc, "生成说明（请先读，定稿前删除本页）")
    _para(doc, f"本文件由「环评报告生成智能体」依据填报的项目信息自动生成{('，宿主：' + host) if host else ''}。")
    _para(doc, "1. 判定类内容（名录档级、专项评价设置、批次结构）由判据库与代码给出，"
               "依据见文末「判定依据」。")
    _para(doc, "2. 凡标注【需人工补充】的位置，是填报信息里没有、且工具**拒绝编造**的内容 ——"
               "包括监测数据、预测结果、图件、公众参与等，必须由编制人员补齐。")
    _para(doc, "3. 本稿**不得直接作为报批件**；请补齐占位内容、核对判定结论后定稿。")
    if narration:
        n_drop = sum(len(v.get("剔除") or []) for v in narration.get("小节", {}).values())
        _para(doc, f"4. 叙述由模型依据「事实表」生成，并逐句过**出处闸门**："
                   f"含数字的句子必须在所填报的事实中有出处，否则整句剔除；"
                   f"本次共剔除 {n_drop} 句（明细见文末「叙述与剔除记录」）。"
                   f"（提示词版本 {narration.get('PROMPT_VERSION')}）")
    if dec.get("需人工确认"):
        _para(doc, "5. 本次生成中需人工确认的事项：", bold=True)
        for x in dec["需人工确认"]:
            _para(doc, "　- " + str(x), size=10.5)
    if evidence:
        # 对话式采集：把"每条事实是从用户哪句话里抽出来的"写进交付件，便于复核。
        # 这是对话侧出处闸门的落地记录 —— 用户能逐条看到工具凭什么这么填。
        _para(doc, "6. 项目信息的来源（对话采集，逐条给出用户原话依据）：", bold=True)
        rows = [("字段", "用户原话依据")]
        for k, q in evidence.items():
            if q:
                rows.append((k, str(q)[:60]))
        if len(rows) > 1:
            _kv_table(doc, rows[1:])
        _para(doc, "　（依据为空的行是模型未给片段、代码按字面比对通过的项目；"
                   "凡依据对不上的，代码已直接丢弃，未写入本稿。）", size=10.5)
    doc.add_page_break()

    # ---------------- 一、建设项目基本情况 ----------------
    _h(doc, "一、建设项目基本情况")
    _kv_table(doc, [
        ("建设项目名称", data.get("项目名称")),
        ("项目代码", data.get("项目代码") or "无"),
        ("建设地点", data.get("建设地点")),
        ("地理坐标", data.get("地理坐标")),
        ("建设性质", data.get("建设性质")),
        ("国民经济行业类别", data.get("国民经济行业类别")),
        ("建设项目行业类别", data.get("建设项目行业类别")),
        ("是否开工建设", "是" if data.get("是否开工建设") else "否"),
        ("用地（用海）面积（m²）", data.get("用地面积_m2")),
        ("总投资（万元）", data.get("总投资_万元")),
        ("环保投资（万元）", data.get("环保投资_万元")),
    ])
    _para(doc)
    _para(doc, "环评文件类型判定：" + _cat_text(dec), size=10.5)
    _para(doc, "专项评价设置情况：" + _spec_text(dec), size=10.5)
    _para(doc, f"规划情况：{data.get('规划情况') or '无（填报表未填，须核实后填写）'}", size=10.5)
    _para(doc, f"规划环境影响评价情况：{data.get('规划环评情况') or '无（同上）'}", size=10.5)
    _para(doc, "规划及规划环境影响评价符合性分析：" + (_fill(data, "规划符合性分析") or TODO),
          size=10.5)
    _para(doc, "其他符合性分析（三线一单等）：" + (_fill(data, "其他符合性分析") or TODO), size=10.5)

    # ---------------- 二、建设项目工程分析 ----------------
    _h(doc, "二、建设项目工程分析")
    _para(doc, "1. 主要产品及产能", bold=True, size=11)
    prod = data.get("产品及产能") or []
    if prod:
        _list_table(doc, ["名称", "产能", "单位"],
                    [[x.get("名称"), x.get("产能"), x.get("单位")] for x in prod if isinstance(x, dict)])
    else:
        _para(doc, TODO, size=10.5)
    _para(doc, "2. 主要原辅材料及燃料", bold=True, size=11)
    mats = data.get("主要原辅材料") or []
    if mats:
        _list_table(doc, ["名称", "年用量", "单位", "是否危险物质"],
                    [[x.get("名称"), x.get("年用量"), x.get("单位"),
                      "是" if x.get("是否危险物质") else "否"] for x in mats if isinstance(x, dict)])
    else:
        _para(doc, TODO, size=10.5)
    _para(doc, "3. 主要生产设施及参数", bold=True, size=11)
    eq = data.get("主要生产设备") or []
    if eq:
        _list_table(doc, ["名称", "数量", "规格型号"],
                    [[x.get("名称"), x.get("数量"), x.get("规格")] for x in eq if isinstance(x, dict)])
    else:
        _para(doc, TODO, size=10.5)
    _para(doc, "4. 主要工艺流程和产排污环节：" +
               (data.get("工艺流程简述") or TODO), size=10.5)
    _narr(doc, narration, "工艺流程和产排污环节概述")
    pw = data.get("产排污环节") or []
    if pw:
        _list_table(doc, ["产排污环节", "污染物", "排放去向"],
                    [[x.get("环节"), x.get("污染物"), x.get("排放去向")]
                     for x in pw if isinstance(x, dict)])
    else:
        _para(doc, "　产排污环节表：" + TODO, size=10.5)
    _para(doc, "5. 水平衡分析：" + (data.get("水平衡说明") or TODO), size=10.5)
    _para(doc, f"6. 劳动定员及工作制度：{data.get('劳动定员') or TODO}；"
               f"{data.get('工作制度') or TODO}", size=10.5)
    _para(doc, "7. 与项目有关的原有环境污染问题：" +
               (data.get("原有环境污染问题") or TODO), size=10.5)

    # ---------------- 三、区域环境质量现状、环境保护目标及评价标准 ----------------
    _h(doc, "三、区域环境质量现状、环境保护目标及评价标准")
    _para(doc, "1. 区域环境质量现状：" + (data.get("区域环境质量现状") or
               TODO + "（需引用有效监测数据，工具不生成）"), size=10.5)
    _para(doc, "2. 环境保护目标", bold=True, size=11)
    tg = data.get("环境保护目标") or []
    if tg:
        _list_table(doc, ["名称", "方位", "距离（m）", "规模"],
                    [[x.get("名称"), x.get("方位"), x.get("距离_m"), x.get("规模")]
                     for x in tg if isinstance(x, dict)])
    else:
        _para(doc, TODO + "（须现场核实并列表，工具不生成）", size=10.5)
    _para(doc, "3. 污染物排放控制标准（候选，须人工核定）", bold=True, size=11)
    st = dec["标准"]
    _para(doc, "　" + st.get("性质", ""), size=10)
    if st.get("候选"):
        _list_table(doc, ["标准号", "名称", "命中词", "语料引用报告数"],
                    [[c["标准号"], c.get("名称") or "（名称未从语料抽到）",
                      "、".join(c["命中词"]), c["引用报告数"]] for c in st["候选"]])
        _para(doc, "　注：候选依据的是「这些标准在语料里常与上述要素/污染物同时出现」，"
                   "不代表它们对本项目适用；定稿前请逐条核定并补全（含地方标准）。", size=10)
    else:
        _para(doc, "　" + TODO + "（语料共现未给出候选，请人工列全适用标准）", size=10.5)
    _para(doc, "4. 总量控制指标：" + (data.get("总量控制指标") or TODO), size=10.5)

    # 回修项 1：专项评价设置情况表 —— 由判定层结论直接出表。
    # 为什么必须出成**表**：自审（审核引擎）是按"表"读专项评价设置情况的，
    # 只把结论写在正文里它读不到，会报"报告未给出专项评价设置情况表"。
    _para(doc, "表1-2　专项评价设置情况（依据判据库/专项评价设置判据.json）", bold=True, size=11)
    _list_table(doc, ["专项评价类别", "设置情况", "理由"],
                [[r["element"],
                  {True: "设置", False: "不设置", None: "未定，须人工确认"}[r.get("set_special")],
                  (r.get("reason") or "")[:120]] for r in dec["专项评价"]["要素"]])

    # 回修项 2：危险物质清单表 —— 表B.1 对应不上就照实写"须人工核定"，不替它填数。
    if dec.get("危险物质"):
        _para(doc, "表1-3　危险物质清单（临界量取自 HJ 169-2018 表B.1）", bold=True, size=11)
        _list_table(doc, ["危险物质名称", "CAS号", "最大贮存量（t）", "临界量（t）", "核对情况"],
                    [[r["名称"], r.get("cas") or "—", r.get("最大贮存量t"), r.get("临界量t"),
                      r["状态"]] for r in dec["危险物质"]])
        _para(doc, "　注：临界量列为空表示**判据库未能对应**（不代表无风险）；"
                   "填入 CAS 号可提高自动对应率。", size=10)

    # 回修项 3：定档用的补充事实也出成**表**（名称/值/单位）。
    # 自审（审核引擎）是从"物料表"里读名录定档事实的，只写在正文散文里它读不到 ——
    # 这曾经导致"生成侧判报告表、自审说无法确定"的不一致。
    sup = [x for x in (data.get("补充事实") or []) if isinstance(x, dict) and x.get("名称")]
    if sup:
        _para(doc, "表1-4　用于名录定档的补充事实（照名录条件原文填报）", bold=True, size=11)
        _list_table(doc, ["名称", "值", "单位", "说明"],
                    [[x["名称"], ("不适用" if x.get("不适用") is True else x.get("值")),
                      x.get("单位") or "—",
                      "填报者明示本项目不属于该情形" if x.get("不适用") is True
                      else "照名录条件原文填报"] for x in sup])

    # ---------------- 四、主要环境影响和保护措施 ----------------
    _h(doc, "四、主要环境影响和保护措施")
    _para(doc, "1. 施工期环境保护措施：" +
               (_fill(data, "施工期环境保护措施") or TODO + "（施工期措施按施工内容编写，填报未提供）"),
          size=10.5)
    # C9-① 配套（2026-09-23）：判据从"字段在不在"改成"**措施内容有没有字**"。
    # `环保措施` 是必填项，用户交上来的常态是"字段在、行里空着" —— 那种情况原先
    # 既不写【需人工补充】、又渲染一张空表，看起来像"我们故意没写措施"。
    # 注意：只有"要素"填了、措施内容空着，仍旧算**没有措施**（措施=措施内容）。
    ms = [x for x in (data.get("环保措施") or []) if isinstance(x, dict)
          and str(x.get("措施内容") or "").strip()]
    _para(doc, "2. 运营期环境影响和保护措施：" + ("" if ms else TODO), size=10.5)
    _narr(doc, narration, "运营期环境影响和保护措施概述")
    if ms:
        _list_table(doc, ["要素", "环保措施", "排放去向/执行方式"],
                    [[x.get("要素"), x.get("措施内容"), x.get("排放去向")]
                     for x in ms if isinstance(x, dict)])
    else:
        _para(doc, "　" + TODO + "（工具不编措施：请填报『环境保护措施』）", size=10.5)
    _para(doc, "（本节源强核算、预测模式计算与措施可行性论证工具不生成；"
               "请按相应要素导则编制。）", size=10)

    # ---------------- 五、环境保护措施监督检查清单 ----------------
    _h(doc, "五、环境保护措施监督检查清单")
    rows5 = []
    for x in ms:
        if isinstance(x, dict):
            rows5.append([x.get("要素") or "", x.get("排放去向") or "", x.get("措施内容") or "",
                          "（须核定）", "（须核定）"])
    _list_table(doc, ["要素", "排放口/污染源", "环保措施", "执行标准", "监测要求"],
                rows5 or [["废气", "", "", "", ""], ["废水", "", "", "", ""],
                          ["噪声", "", "", "", ""], ["固废", "", "", "", ""],
                          ["地下水及土壤", "", "", "", ""], ["环境风险", "", "", "", ""]])
    _para(doc, "（环保措施由填报数据带出；**执行标准与监测要求须人工核定**后填写 —— "
               "标准清单本工具只给候选。）", size=10)

    # ---------------- 六、结论 ----------------
    _h(doc, "六、结论")
    # 补写过就**整句用他写的**：占位版是"从环境保护角度，本项目建设【需人工补充】（…）"，
    # 把用户写好的整段（如"在落实各项环保措施的前提下…是可行的"）塞进"本项目建设"后面会读不通。
    _concl = _fill(data, "结论")
    if _concl:
        _para(doc, _concl, size=10.5)
    else:
        _para(doc, "从环境保护角度，本项目建设" + TODO +
                   "（可行/不可行需依据预测与措施论证，工具不代替下结论）。", size=10.5)

    # ---------------- 附表 ----------------
    _h(doc, "附表　建设项目污染物排放量汇总表")
    _list_table(doc, ["污染物", "现有工程排放量", "本工程排放量", "总体工程排放量", "增减量"],
                [["废气", "", "", "", ""], ["废水", "", "", "", ""],
                 ["一般固废", "", "", "", ""], ["危险废物", "", "", "", ""]])

    # ---------------- 判定依据 ----------------
    _h(doc, "附：判定依据（机器可核）")
    _para(doc, "1. 名录档级", bold=True, size=11)
    c = dec["名录"]
    _para(doc, f"　查询串匹配条目：序号{c.get('名录序号')}「{c.get('名录条目')}」"
               f"（报告书条件：{c.get('报告书条件') or '无'}；报告表条件：{c.get('报告表条件') or '无'}；"
               f"登记表条件：{c.get('登记表条件') or '无'}）", size=10)
    for x in (c.get("逐条条件") or []):
        _para(doc, f"　[{x['结果']}] {x['条件']} → {x['说明']}", size=10)
    _para(doc, "2. 专项评价设置（指南表1）", bold=True, size=11)
    for r in dec["专项评价"]["要素"]:
        setv = {True: "应设", False: "不设", None: "未定"}[r.get("set_special")]
        _para(doc, f"　{r['element']}：{setv} —— {r['reason']}（判据：{r.get('判据原文')}）", size=10)
    if dec["专项评价"]["冲突"]:
        _para(doc, "3. 填报自相矛盾之处", bold=True, size=11)
        for x in dec["专项评价"]["冲突"]:
            _para(doc, "　- " + x, size=10)
    _para(doc, "4. 章节清单来源", bold=True, size=11)
    _para(doc, "　章节与字段清单由《报告表编制技术指南（污染影响类）试行》机械导出"
               "（判据库/报告表结构.json），并与真实报告表逐节核对一致。", size=10)
    if (dec.get("标准") or {}).get("已排除"):
        _para(doc, "5. 标准候选中被排除的（名称含特定行业，项目未涉及）", bold=True, size=11)
        for x in dec["标准"]["已排除"]:
            _para(doc, f"　- {x['标准号']} {x['名称']} —— {x['原因']}"
                       f"（语料引用 {x['引用报告数']} 份；排除仅供参考，仍须人工核定）", size=10)

    # ---------------- 叙述与剔除记录（出处闸门的凭据） ----------------
    if narration:
        _h(doc, "附：叙述与剔除记录（出处闸门）")
        _para(doc, "叙述由模型依据事实表生成；下表逐条记录**被剔除的句子及原因** —— "
                   "含数字的句子若在所填报的事实里找不到出处，整句剔除。"
                   "少写不算错，编造算错。", size=10)
        rows = []
        for name, v in (narration.get("小节") or {}).items():
            for d in (v.get("剔除") or []):
                rows.append([name, d["句"][:80], d["原因"]])
        if rows:
            _list_table(doc, ["小节", "被剔除的句子", "原因"], rows)
        else:
            _para(doc, "　本次无句子被剔除。", size=10)
        _para(doc, "事实表（模型可见的全部事实，超出这些的内容一律不许写）：", bold=True, size=10.5)
        _list_table(doc, ["编号", "事实", "出处"],
                    [[f["id"], f["text"][:110], f["来源"]] for f in narration.get("事实表") or []])

    doc.core_properties.created = FIXED_TS
    doc.core_properties.modified = FIXED_TS
    doc.core_properties.last_modified_by = "eia-report-gen"
    doc.core_properties.author = "eia-report-gen"
    doc.core_properties.revision = 1
    # 回扫必须在 save 之前——扫的是内存里的这份文档，和即将落盘的是同一份。
    if gaps is not None:
        gaps.extend(_scan_gaps(doc))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    doc.save(path)
    _normalize_zip(path)          # zip 容器时间戳归一化 → 真字节级可复现
    return path