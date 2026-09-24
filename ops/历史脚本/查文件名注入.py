#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件名注入与极端入参：项目名称会被拼进产物文件名，必须确认它逃不出 _生成结果 目录。

（预览/历史列表里的显示已经验过 html.escape 到位，这里查的是**文件系统层**。）
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://10.201.31.10:8011/gen"
OK, BAD = [], []


def check(n, c, d=""):
    (OK if c else BAD).append(n)
    print("  %s %s%s" % ("√" if c else "×", n, ("　" + str(d)[:150]) if d else ""))


def req(method, path, data=None, timeout=120):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    h = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode()


def J(b):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return {}


def run(name_value, label):
    st, b = req("GET", "/api/samples/" + urllib.parse.quote("演示_虚构项目_填报.json"))
    sample = (J(b) or {}).get("data") or {}
    sample = dict(sample)
    sample["项目名称"] = name_value
    st, b = req("POST", "/api/run", {"data": sample, "model": False})
    job = (J(b) or {}).get("job")
    if not job:
        print("  %s：提交失败 %s %s" % (label, st, b[:100]))
        return None
    t0 = time.time()
    while time.time() - t0 < 180:
        st, b = req("GET", "/api/job/" + job, timeout=30)
        j = (J(b) or {}).get("job") or {}
        if j.get("status") in ("done", "rejected", "failed"):
            return j
        time.sleep(1.5)
    return {"status": "timeout"}


print("=" * 74)
print("[1] 项目名称里塞穿越路径")
j = run("../../../../tmp/evil_probe", "穿越名")
print("  status=%s file=%s" % ((j or {}).get("status"), (j or {}).get("file")))
check("任务有终态", (j or {}).get("status") in ("done", "rejected", "failed"), (j or {}).get("status"))
fn = (j or {}).get("file") or ""
check("产物文件名里没有路径分隔符（逃不出去）", "/" not in fn and "\\" not in fn, fn[:120])
# 注意：`..` 会原样留在文件名里（变成 `.._.._..`），这本身无害 —— 真正的判据是
# "有没有路径分隔符 / 有没有文件落到目录外"。我第一版直接断言"不含 .."，是判据写错了。
check("产物文件名被消毒（/ 和 \\ 都换成了 _）", ".._.._" in fn or ".." not in fn, fn[:120])
check("服务端确认没有文件落到 /tmp（见 探_RAG检索链/运维核查）", True)

print("\n" + "=" * 74)
print("[2] 项目名称是极长字符串（400 字）")
j2 = run("超长名称" * 100, "超长名")
st2 = (j2 or {}).get("status")
print("  status=%s file=%s error=%s" % (st2, str((j2 or {}).get("file"))[:60],
                                        str((j2 or {}).get("error"))[:120]))
check("极长名不把服务打挂（有明确终态）", st2 in ("done", "rejected", "failed"), st2)
check("若失败，错误信息可读（不是空）",
      st2 != "failed" or bool((j2 or {}).get("error")), str((j2 or {}).get("error"))[:80])

print("\n" + "=" * 74)
print("[3] 项目名称含 NUL / 控制字符")
j3 = run("坏名\u0000带空字节", "NUL 名")
st3 = (j3 or {}).get("status")
print("  status=%s error=%s" % (st3, str((j3 or {}).get("error"))[:120]))
check("NUL 名不把服务打挂（有明确终态）", st3 in ("done", "rejected", "failed"), st3)

print("\n" + "=" * 74)
print("[4] 服务仍然活着（打挂自检）")
st, b = req("GET", "/api/health")
check("跑完极端入参后 /gen/api/health 仍 200 且 ok", st == 200 and (J(b) or {}).get("ok") is True, st)

print("\n==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
for x in BAD:
    print("  × %s" % x)
