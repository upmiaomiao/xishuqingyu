#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把线上改动同步回仓库 —— 一条命令搞定「比对 → 取回 → 落地 → 提交」。

背景：仓库里的 `server/` 是线上代码的镜像（保持绝对路径结构），`ops/` 对应线上平铺在
/home/test 的脚本。线上改完代码后，用它把差异搬回仓库，**不用手工 cp**。

用法：
    python tools/同步线上到仓库.py                    # 只报告差异（默认，不动任何文件）
    python tools/同步线上到仓库.py --apply            # 取回并落地（改动的旧文件移到 _同步/已删除备份/）
    python tools/同步线上到仓库.py --apply --commit    # 落地并 git commit（不推送）
    python tools/同步线上到仓库.py --apply --commit --push
    python tools/同步线上到仓库.py --manifest 某个清单.txt   # 离线比对（不连服务器）

判定口径：
    · 内容不同 → 更新；线上新增 → 取回；线上没了 → 从仓库删掉（先备份到 _同步/已删除备份/）
    · `ops/` 里「服务器上没有同名文件」的脚本视为**仓库独有**（我写的本地工具），不删、只提示
    · 只有 `server/**` 与 `ops/<单文件>` 参与同步；`tests/`、`tools/`、`ops/历史脚本/`、
      `ops/工作区脚本/` 与仓库根文件都是仓库独有，永不参与
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SERVER_SCRIPT = os.path.join(HERE, "_服务器侧_清单与md5.py")
WORK = os.path.join(REPO, "_同步")                 # 工作目录（已 gitignore）


# ---------------------------------------------------------------- 基础工具

def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kw)


def git(*args: str) -> subprocess.CompletedProcess:
    return run(["git", "-C", REPO, *args])


def server_to_repo(rel: str) -> str:
    """线上相对路径 → 仓库相对路径（与首次入库的口径一致）。"""
    parts = rel.split("/")
    if (parts[0] == "home" and len(parts) == 3 and parts[1] == "test"
            and parts[2].endswith((".py", ".sh"))):
        return "ops/" + parts[2]
    return "server/" + rel


def repo_to_server(rel: str):
    """仓库相对路径 → 线上相对路径；None = 仓库独有，不参与同步。"""
    parts = rel.split("/")
    if parts[0] == "server" and len(parts) > 1:
        return "/".join(parts[1:])
    if parts[0] == "ops" and len(parts) == 2:
        return "home/test/" + parts[1]
    return None


# ---------------------------------------------------------------- 取清单

def fetch_manifest(args) -> dict:
    if args.manifest:
        text = io.open(args.manifest, encoding="utf-8").read()
        print("用离线清单：%s" % args.manifest)
    else:
        put = os.path.join(args.helpers, "put_file.py")
        rcmd = os.path.join(args.helpers, "runcmd.py")
        for p in (put, rcmd):
            if not os.path.isfile(p):
                sys.exit("找不到 SSH helper：%s（用 --helpers 指定 服务器会话 目录）" % p)
        os.makedirs(WORK, exist_ok=True)
        # 放 _导出代码/ 里：那个目录在服务器侧清单的排除名单内，
        # 否则这个工具脚本自己会被当成"线上新增的代码"收进 ops/。
        remote_script = "/home/test/_导出代码/_同步工具_服务器侧.py"
        print("① 上传服务器侧清单工具（每次都用仓库这份，避免线上留旧版本）")
        r = run([sys.executable, put, "--host", args.host, SERVER_SCRIPT, remote_script])
        if r.returncode:
            sys.exit("上传失败：%s%s" % (r.stdout, r.stderr))
        print("② 在服务器上列清单并算 md5 …")
        r = run([sys.executable, rcmd, "--host", args.host, "--timeout", str(args.timeout),
                 "python3 %s list" % remote_script])
        if r.returncode:
            sys.exit("列清单失败：%s%s" % (r.stdout, r.stderr))
        text = r.stdout
        stamp = time.strftime("%Y%m%d_%H%M%S")
        keep = os.path.join(WORK, "清单_%s.txt" % stamp)
        io.open(keep, "w", encoding="utf-8").write(text)
        print("   清单已存本地：%s" % os.path.relpath(keep, REPO))
    man = {}
    for line in text.splitlines():
        line = line.rstrip("\n")
        if not line or line.startswith("!") or "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            man[parts[2].strip()] = (parts[0].strip(), parts[1].strip())
        else:
            man[parts[0].strip()] = (parts[1].strip(), "")       # 兼容两列的老清单
    print("   线上代码文件 %d 个" % len(man))
    return man


# ---------------------------------------------------------------- 比对

def md5_lf(path: str) -> str:
    """本地文件按 LF 归一后的 md5（与服务器侧第二列口径一致）。"""
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.md5(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def diff(man: dict) -> dict:
    tracked = [l.strip() for l in git("ls-files").stdout.splitlines() if l.strip()]
    repo_map = {}                       # 线上相对路径 → 仓库相对路径
    local_only = []
    for rel in tracked:
        srel = repo_to_server(rel)
        if srel is None:
            local_only.append(rel)
        else:
            repo_map[srel] = rel

    modified, added, eol_only, same = [], [], [], 0
    for srel, (digest, digest_lf) in sorted(man.items()):
        rel = repo_map.get(srel)
        if rel is None:
            added.append(srel)
            continue
        p = os.path.join(REPO, rel)
        if not os.path.isfile(p):
            modified.append(srel)
        elif md5(p) == digest:
            same += 1
        elif digest_lf and md5_lf(p) == digest_lf:
            eol_only.append(srel)        # 只差行尾（仓库统一 LF，线上是 CRLF）——不算改
        else:
            modified.append(srel)

    deleted = [srel for srel in repo_map if srel not in man]
    # ops/ 里线上没有同名的 → 仓库独有的本地脚本，不删
    orphan_ops = [s for s in deleted if s.startswith("home/test/") and s.count("/") == 2]
    deleted = [s for s in deleted if s not in orphan_ops]
    return {"modified": modified, "added": added, "deleted": deleted,
            "orphan_ops": orphan_ops, "eol_only": eol_only, "same": same,
            "local_only": local_only, "repo_map": repo_map}


# ---------------------------------------------------------------- 落地

def extract_bytes(tar_path: str, dst: str) -> int:
    """按字节自己写盘。

    注意：**不要用 tarfile.extract()** —— 在本机的文件沙箱下它对部分成员报
    PermissionError（包内是 0444 只读模式），而 open(...,'wb') 手写没问题。
    """
    n = 0
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf.getmembers():
            if not m.isreg():
                continue
            rel = m.name.lstrip("./")
            target = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(target) or dst, exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(tf.extractfile(m).read())
            n += 1
    return n


def apply_changes(args, man: dict, d: dict) -> int:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    todo = d["modified"] + d["added"]
    failed = 0

    if todo:
        os.makedirs(WORK, exist_ok=True)
        list_local = os.path.join(WORK, "待取清单.txt")
        io.open(list_local, "w", encoding="utf-8").write("\n".join(todo) + "\n")
        remote_list = "/home/test/_导出代码/待取清单.txt"
        remote_tar = "/home/test/_导出代码/同步_%s.tar.gz" % stamp
        tar_local = os.path.join(WORK, "下载_%s.tar.gz" % stamp)

        put = os.path.join(args.helpers, "put_file.py")
        get = os.path.join(args.helpers, "get_file.py")
        rcmd = os.path.join(args.helpers, "runcmd.py")
        print("③ 上传待取清单（%d 个文件）" % len(todo))
        r = run([sys.executable, put, "--host", args.host, list_local, remote_list])
        if r.returncode:
            sys.exit("上传清单失败：%s%s" % (r.stdout, r.stderr))
        print("④ 服务器打包")
        r = run([sys.executable, rcmd, "--host", args.host, "--timeout", str(args.timeout),
                 "python3 %s pack %s %s" % (remote_script, remote_list, remote_tar)])
        if r.returncode:
            sys.exit("打包失败：%s%s" % (r.stdout, r.stderr))
        print("   " + r.stdout.strip())
        print("⑤ 下载并解包")
        r = run([sys.executable, get, "--host", args.host, remote_tar, tar_local])
        if r.returncode:
            sys.exit("下载失败：%s%s" % (r.stdout, r.stderr))
        raw = os.path.join(WORK, "解包")
        if os.path.isdir(raw):
            shutil.rmtree(raw, ignore_errors=True)
        n = extract_bytes(tar_local, raw)
        print("   解出 %d 个文件" % n)

        print("⑥ 逐个核对 md5 后落进仓库")
        for srel in todo:
            src = os.path.join(raw, srel)
            rel = server_to_repo(srel)
            dst = os.path.join(REPO, rel)
            if not os.path.isfile(src):
                print("   ❌ 包里没有 %s（跳过）" % srel)
                failed += 1
                continue
            got = md5(src)
            if got != man[srel][0]:
                print("   ❌ %s md5 不符（包内 %s / 清单 %s），不落地"
                      % (rel, got[:8], man[srel][0][:8]))
                failed += 1
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            print("   ✅ %-58s %s" % (rel, "更新" if srel in d["modified"] else "新增"))
        if not args.keep_tar and os.path.isfile(tar_local):
            os.remove(tar_local)
    else:
        print("③ 没有需要取回的文件")

    if d["deleted"]:
        print("⑦ 线上已删除的文件，从仓库移除（先备份）")
        for srel in d["deleted"]:
            rel = server_to_repo(srel)
            src = os.path.join(REPO, rel)
            if not os.path.isfile(src):
                continue
            bak = os.path.join(WORK, "已删除备份", stamp, rel)
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.move(src, bak)
            print("   🗑  %-58s 备份在 _同步/已删除备份/%s/" % (rel, stamp))

    # 复核：改动过的文件本地 md5 是否等于清单
    print("⑧ 复核落盘结果")
    bad = [s for s in todo if os.path.isfile(os.path.join(REPO, server_to_repo(s)))
           and md5(os.path.join(REPO, server_to_repo(s))) != man[s][0]]
    print("   应更新 %d 个，复核不符 %d 个%s"
          % (len(todo), len(bad), "" if not bad else "：" + ", ".join(bad[:5])))
    return failed + len(bad)


def do_commit(args, d: dict) -> None:
    if not (d["modified"] or d["added"] or d["deleted"]):
        print("没有改动，跳过提交")
        return
    # 提交前确认工作区没有"与本次同步无关"的改动，免得把别的改动裹进这个提交
    related = {server_to_repo(s) for s in d["modified"] + d["added"] + d["deleted"]}
    extra = []
    for line in git("status", "--porcelain").stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ")[-1].strip()
        if path and path not in related:
            extra.append(path)
    if extra:
        print("工作区还有 %d 个与本次同步无关的改动，为免混进提交，已跳过自动提交：" % len(extra))
        for x in extra[:15]:
            print("   · %s" % x)
        print("请先处理它们，或手工 git add 指定文件再提交。")
        return
    git("add", "-A")
    lines = ["同步线上改动到仓库：更新 %d、新增 %d、删除 %d"
             % (len(d["modified"]), len(d["added"]), len(d["deleted"]))]
    for srel in (d["modified"] + d["added"])[:40]:
        lines.append("- %s %s" % ("更新" if srel in d["modified"] else "新增",
                                  server_to_repo(srel)))
    for srel in d["deleted"][:20]:
        lines.append("- 删除 %s" % server_to_repo(srel))
    if len(d["modified"]) + len(d["added"]) + len(d["deleted"]) > 60:
        lines.append("…（其余见 git show --stat）")
    msg = "\n".join(lines)
    r = git("commit", "-q", "-m", msg)
    if r.returncode:
        print("提交失败：%s%s" % (r.stdout, r.stderr))
        return
    print("已提交：%s" % git("log", "--oneline", "-1").stdout.strip())
    if args.push:
        r = git("push", "origin", "HEAD")
        print("推送%s：%s" % ("成功" if r.returncode == 0 else "失败",
                             (r.stdout + r.stderr).strip().splitlines()[-1] if
                             (r.stdout + r.stderr).strip() else ""))


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="把线上改动同步回仓库")
    ap.add_argument("--host", default="10.201.31.10")
    ap.add_argument("--helpers", default=os.path.join(os.path.dirname(REPO), "服务器会话"),
                    help="SSH helper 目录（put_file.py/runcmd.py/get_file.py 所在）")
    ap.add_argument("--manifest", help="离线清单文件（给了就不连服务器）")
    ap.add_argument("--apply", action="store_true", help="真正取回并落地（默认只报告）")
    ap.add_argument("--commit", action="store_true", help="落地后 git commit")
    ap.add_argument("--push", action="store_true", help="提交后 git push")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--keep-tar", action="store_true", help="保留下载的 tar 包便于排查")
    args = ap.parse_args()
    if args.push:
        args.commit = True

    if not os.path.isdir(os.path.join(REPO, ".git")):
        sys.exit("这里不是 git 仓库：%s" % REPO)
    print("仓库：%s\n服务器：%s\n" % (REPO, args.host))

    man = fetch_manifest(args)
    d = diff(man)

    print("\n==== 差异 ====")
    print("  一致 %d 个" % d["same"])
    print("  内容不同（更新）%d 个" % len(d["modified"]))
    for s in d["modified"][:20]:
        print("     M %s" % server_to_repo(s))
    print("  线上新增（取回）%d 个" % len(d["added"]))
    for s in d["added"][:20]:
        print("     A %s" % server_to_repo(s))
    print("  线上已删（仓库移除）%d 个" % len(d["deleted"]))
    for s in d["deleted"][:20]:
        print("     D %s" % server_to_repo(s))
    if d["eol_only"]:
        print("  仅行尾不同（仓库统一 LF，忽略）%d 个" % len(d["eol_only"]))
        for s in d["eol_only"][:8]:
            print("     ~ %s" % server_to_repo(s))
    if d["orphan_ops"]:
        print("  ops/ 里线上没有同名的 %d 个（本地工具，保留不动）" % len(d["orphan_ops"]))
        for s in d["orphan_ops"][:8]:
            print("     · %s" % server_to_repo(s))

    changed = len(d["modified"]) + len(d["added"]) + len(d["deleted"])
    if not changed:
        print("\n✅ 仓库与线上一致，无需同步")
        return 0
    if not args.apply:
        print("\n（以上只是报告；加 --apply 才会取回落地）")
        return 1

    print("\n==== 落地 ====")
    bad = apply_changes(args, man, d)
    print("\n%s" % ("✅ 全部落地并复核通过" if not bad else "⚠️ 有 %d 个文件没落地成功" % bad))
    if args.commit:
        do_commit(args, d)
    else:
        print("下一步：git -C %s diff --stat 看改动，然后 git add -A && git commit" % REPO)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
