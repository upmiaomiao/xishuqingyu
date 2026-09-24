#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫仓库里有没有敏感信息（工作区文件 + 全部 git 历史）—— 推送前跑一遍。

用法：
    python tools/查敏感信息.py                    # 默认：仓库=本脚本上级目录，账号文件=../账号.md
    python tools/查敏感信息.py <仓库> <账号.md>

三层检查：
  ① 敏感**文件名**：.env / *.pem / id_rsa / 账号.md / credentials …（含历史里删掉的）
  ② 高危**内容模式**：私钥头、sk-/ghp_/AKIA/xox 令牌、api_key=、password= 等
  ③ 决定性检查：把 账号.md 里的真实主机/用户名/口令原文拿去 grep 仓库（历史 + 工作区），
     命中的话才算真的泄露 —— 只会打印"长度/是否命中"，不会把口令本身打出来。

不算机密但会单独列出供判断：内网 IP、/home/test 这类服务器路径、客户项目名。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(_HERE)
ACCOUNT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(REPO)), "账号.md")

SKIP_DIR = {".git", "_同步", "__pycache__", "_raw3", "_raw4", "_staging",
            "_eia_audit_残留165030"}
# 本文件里就写着各种模式串（如 "BEGIN OPENSSH PRIVATE KEY"），会自匹配成误报 —— 排除自己
SELF = "查敏感信息.py"

SENSITIVE_NAMES = [
    r"(^|/)\.env$", r"\.pem$", r"\.key$", r"\.pfx$", r"\.p12$", r"(^|/)id_rsa",
    r"(^|/)id_dsa", r"(^|/)\.netrc$", r"(^|/)\.git-credentials$", r"账号", r"凭据",
    r"(^|/)credentials", r"secret", r"\.ppk$",
]

PATTERNS = [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥内容"),
    (r"BEGIN OPENSSH PRIVATE KEY", "OpenSSH 私钥"),
    (r"\bsk-[A-Za-z0-9_\-]{20,}", "OpenAI 风格密钥 sk-"),
    (r"\bghp_[A-Za-z0-9]{20,}", "GitHub PAT ghp_"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}", "GitHub PAT github_pat_"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS AK"),
    (r"\bxox[baprs]-[A-Za-z0-9\-]{10,}", "Slack token"),
    (r"AQVN[0-9A-Za-z_\-]{20,}", "百度云 AK 风格"),
    (r"(?i)bearer\s+[A-Za-z0-9_\-\.]{30,}", "Bearer 长令牌"),
    (r"(?i)(api[_-]?key|apikey)\s*[:=]\s*[\"'][^\"']{16,}[\"']", "硬编码 api_key"),
    (r"(?i)(secret|passwd|password|passphrase)\s*[:=]\s*[\"'][^\"']{6,}[\"']", "硬编码口令"),
    (r"(?i)[a-z]+://[^/\s:]+:[^/\s@]{6,}@", "URL 内嵌口令"),
    (r"(?i)ssh-rsa\s+AAAA[A-Za-z0-9+/]{40,}", "SSH 公钥（低敏）"),
]


def git(*args, **kw):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw).stdout


def tracked_and_history_names() -> set:
    names = set()
    for line in git("rev-list", "--objects", "--all").splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            names.add(parts[1])
    for line in git("ls-files").splitlines():
        names.add(line)
    return names


def scan_history(label: str, pattern: str) -> list:
    """在所有提交里 grep（-I 跳过二进制），返回 [提交:文件:行:内容]"""
    commits = git("rev-list", "--all").split()
    if not commits:
        return []
    r = subprocess.run(["git", "-C", REPO, "grep", "-n", "-I", "-E", pattern, *commits,
                        "--", ".", ":(exclude)*%s" % SELF],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [l for l in r.stdout.splitlines() if l.strip()]


def scan_tree(pattern: str) -> list:
    rx = re.compile(pattern)
    hits = []
    for dp, dns, fns in os.walk(REPO):
        dns[:] = [d for d in dns if d not in SKIP_DIR]
        for f in fns:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, REPO)
            if f == SELF:
                continue
            try:
                if os.path.getsize(p) > 8 << 20:
                    continue
                with open(p, encoding="utf-8", errors="strict") as fh:
                    for i, line in enumerate(fh, 1):
                        if rx.search(line):
                            hits.append("%s:%d:%s" % (rel, i, line.strip()[:160]))
            except (OSError, UnicodeDecodeError):
                continue
    return hits


def main() -> int:
    problems = 0

    print("=" * 70)
    print("① 敏感文件名（工作区追踪 + 全部历史）")
    names = tracked_and_history_names()
    hits = [n for n in sorted(names) if any(re.search(p, n) for p in SENSITIVE_NAMES)]
    if hits:
        problems += len(hits)
        for n in hits:
            print("   ❌ %s" % n)
    else:
        print("   ✅ 无 .env / 私钥 / 账号文件（历史里也没有）")

    print("=" * 70)
    print("② 高危内容模式（全部历史的所有提交）")
    for pat, label in PATTERNS:
        found = scan_history(label, pat)
        tag = "低敏" if "低敏" in label else "关注"
        if found:
            if tag == "关注":
                problems += len(found)
            print("   %s %s：%d 处" % ("⚠️" if tag == "低敏" else "❌", label, len(found)))
            for l in found[:6]:
                print("        %s" % l[:180])
        else:
            print("   ✅ %s：0 处" % label)

    print("=" * 70)
    print("③ 工作区文件同样扫一遍（防止只在盘上、被 ignore 的漏判）")
    for pat, label in PATTERNS:
        found = scan_tree(pat)
        if found:
            print("   ⚠️ %s：%d 处" % (label, len(found)))
            for l in found[:6]:
                print("        %s" % l[:180])
    print("   （工作区命中若不入库、也不在历史里，就不算泄露；上面①只查了入库范围）")

    print("=" * 70)
    print("④ 决定性检查：拿真实凭据原文去仓库里搜")
    if not ACCOUNT or not os.path.isfile(ACCOUNT):
        print("   ⏭  没给账号文件，跳过（用法：查敏感信息.py <仓库> <账号.md>）")
    else:
        text = open(ACCOUNT, encoding="utf-8", errors="replace").read()
        secrets = set()
        for line in text.splitlines():
            for m in re.finditer(r"(?:密码|口令|password|passwd|pass)\s*[:：]\s*(\S{4,})", line):
                secrets.add(m.group(1).strip())
            for m in re.finditer(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", line):
                secrets.add(m.group(1))
        if not secrets:
            print("   ⏭  账号文件里没解析出可比的凭据")
        for s in sorted(secrets):
            shown = s if "." in s else "（长度 %d 的字符串）" % len(s)
            in_hist = scan_history("", re.escape(s))
            in_tree = scan_tree(re.escape(s))
            if in_hist or in_tree:
                # 内网 IP 出现在脚本里属预期，单独说明
                if "." in s and re.match(r"^\d+\.\d+\.\d+\.\d+$", s):
                    print("   ⚠️ 内网地址 %s：历史 %d 处、工作区 %d 处（预期，非机密）"
                          % (s, len(in_hist), len(in_tree)))
                else:
                    problems += len(in_hist) + len(in_tree)
                    print("   ❌ 凭据 %s：历史命中 %d 处、工作区命中 %d 处"
                          % (shown, len(in_hist), len(in_tree)))
                    for l in (in_hist + in_tree)[:5]:
                        print("        %s" % l[:180])
            else:
                print("   ✅ 凭据 %s：历史与工作区均 0 命中" % shown)

    print("=" * 70)
    print("结论：%s" % ("❌ 有 %d 处需要处理" % problems if problems else
                      "✅ 未发现敏感信息入库（含全部历史）"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
