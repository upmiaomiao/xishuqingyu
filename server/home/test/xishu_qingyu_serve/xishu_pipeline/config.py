"""服务端配置与限制常量。

（P1 由 website_split.py 从单文件服务端机械切分；P3 起在此集中管理密钥来源与前端路径。）
"""
from __future__ import annotations

import os
from pathlib import Path

# 服务根目录 = xishu_pipeline 的上一级（原单文件里 __file__ 就在服务根，抽包后必须回退一级，
# 否则 KG_PATH 会指向 xishu_pipeline/kg_data 而找不到图谱）
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """把服务根目录的 .env 读进环境变量（已存在的环境变量优先，不覆盖）。

    为什么在 Python 侧读、而不是改 launcher：**launcher 保持不变**是本次重构的约束之一；
    而且这样无论谁怎么启动（launcher / systemd / 手工），配置来源都一样。
    极简实现，故意不引第三方依赖。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


# 2026-09-18：v5 生产服务从 .12:8000 迁到本机（.10）GPU 1,2 的 8020。
# 改前备份：config.py.bak_before_move_v5_20260918
# 原值 "http://10.201.31.12:8000/v1/chat/completions"
MODEL_URL = "http://127.0.0.1:8020/v1/chat/completions"

MODEL_NAME = "xishu-qingyu-v5"

DEFAULT_TOP_K = 5

INTENT_ENABLED = True

INTENT_BASE_URL = "https://www.dmxapi.cn/v1"

# ===== 意图识别用的密钥 =====
# 取值：INTENT_API_KEY 环境变量 → OPENAI_API_KEY 环境变量（服务根 .env 会被上面的 _load_dotenv 读进环境）。
# **代码里不再保留任何密钥明文**（P3 收尾：先加兜底灰度上线，确认 .env 生效后再删除兜底）。
# /health 会回报来源（env / missing），不打印密钥本身就能确认线上配置是否正确。
INTENT_API_KEY = (
    os.environ.get("INTENT_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
)
INTENT_KEY_SOURCE = "env" if INTENT_API_KEY else "missing"
if not INTENT_API_KEY:
    print(
        "[警告] 未找到意图识别密钥（INTENT_API_KEY / OPENAI_API_KEY）："
        "意图路由会回落到关键词兜底，专业/科普分流精度下降。"
        f"请把密钥写进 {BASE_DIR / '.env'}（权限 600）。",
        flush=True,
    )

INTENT_MODEL = "deepseek-v4-pro-guan"

INTENT_TIMEOUT = 20

# P0-2 修复（2026-09-18）：原写法漏了 BASE_DIR，指向 xishu_pipeline/kg_data/graph_full.json
# ——该路径不存在，kg.py 对文件缺失静默返回空图，前端只显示"0 个节点 · 0 条关系"且不报错。
# 实际文件在服务根：/home/test/xishu_qingyu_serve/kg_data/graph_full.json（1,884,203 字节）。
# 这正是上面 BASE_DIR 注释里预警过的情形。
KG_PATH = BASE_DIR / "kg_data" / "graph_full.json"

KG_MAX_SUBGRAPH_NODES = 100

MAX_IMAGE_CHARS = 9_000_000          # data URL 字符数上限（≈6.5MB 原始字节）

# 前端已外置（P3）：不再内嵌在 routes.py 的字符串里
FRONTEND_PATH = BASE_DIR / "frontend" / "index.html"

# 原文 PDF 的存放根目录（引用卡片「查看原文 PDF」从这里取文件）。
# 放 /data 而不是服务目录：.10 的 / 分区只剩几 GB，/data 有几百 GB。
# 目录结构与索引里的 source 一一对应（source 的 .md 换成 .pdf）。
PDF_ROOT = Path(os.environ.get("PDF_ROOT", "/data/fagui_pdf"))

# 索引里 .md 全文所在目录（source 就是相对这里的路径）。
#
# 为什么要单独有它：不是每一类资料都有配套 PDF。**环评报告**这一类
# 索引里有 592 条 .md（共 225 MB 全文），但 /data/fagui_pdf/环评报告/ 下
# 一个 PDF 都没有 —— 原始 PDF 从来没有上传过，服务器上也找不到、也没有解压工具。
# 于是这 592 条引用的「查看原文」全部 404（就是一直记着的 [009] 死链）。
# 有了 MD_ROOT，PDF 缺失时可以退回显示**文本版全文**，用户照样读得到原文，
# 而不是看到一个"找不到文件"。
MD_ROOT = Path(os.environ.get("MD_ROOT", "/data/fagui_rag/okf_bundles"))

# 文本回退时单次返回的上限（字符）。最大的 .md 有 1.9 MB，
# 一次性丢给浏览器会卡；超出部分截断并明确告知用户。
MD_PREVIEW_MAX = int(os.environ.get("MD_PREVIEW_MAX", "400000"))
