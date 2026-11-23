# SPDX-License-Identifier: Apache-2.0
# -*- coding: utf-8 -*-
"""在 git HTTPS 不可达的环境里，用 GitHub REST 把本仓推到远端。

背景：某些办公网直连 github.com:443 会超时（api.github.com 却是通的）。
此时 `git push` 永远失败，但 REST 可用，于是用 Git Data API 建提交。

用法（先设环境变量 GH_TOKEN，不要把 token 写进任何文件）：

    python tools/push_via_api.py files "<提交信息>" <路径1> <路径2> ...
    python tools/push_via_api.py tree  "<提交信息>"          # 全量按本地工作树对齐
    python tools/push_via_api.py log   <job_id> [关键词]     # 抓某个 CI job 的日志

注意：
  - `tree` 会以远端当前 head 为 parent，把本地**已 git add**的文件全部写进去；
  - 用 REST 推出来的提交与本地 git 历史不同源（内容同源、SHA 不同），
    所以本地 commit 只作记录，不要期望能 `git pull` 对齐；
  - 一旦网络允许 `git push`，请优先用 git，本脚本只作兜底。
"""
import base64
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

OWNER, REPO = "stevenzhao07", "aitb"
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = {"name": "stevenzhao07", "email": "stevenzhao07@users.noreply.github.com"}
TOK = os.environ.get("GH_TOKEN", "")
if not TOK:
    sys.exit("需要 GH_TOKEN 环境变量（不要写入文件）")


def api(method, path, payload=None):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method,
                                 headers={"Authorization": f"Bearer {TOK}", "User-Agent": "aitb-push",
                                          "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode() or "{}")


def _entry(rel):
    raw = open(os.path.join(ROOT, rel), "rb").read()
    try:
        return {"path": rel, "mode": "100644", "type": "blob", "content": raw.decode("utf-8")}
    except UnicodeDecodeError:
        blob = api("POST", "/git/blobs", {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        return {"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]}


def cmd_files(message, files):
    head = api("GET", "/git/ref/heads/main")["object"]["sha"]
    base_tree = api("GET", f"/git/commits/{head}")["tree"]["sha"]
    tree = api("POST", "/git/trees", {"base_tree": base_tree, "tree": [_entry(f) for f in files]})
    commit = api("POST", "/git/commits", {"message": message, "tree": tree["sha"],
                                          "parents": [head], "author": NAME, "committer": NAME})
    api("PATCH", "/git/refs/heads/main", {"sha": commit["sha"], "force": False})
    print(f"{len(files)} files -> {commit['sha']}")


def cmd_tree(message):
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8").stdout.split()
    head = api("GET", "/git/ref/heads/main")
    if head.get("object"):
        head_sha = head["object"]["sha"]
        base_tree = api("GET", f"/git/commits/{head_sha}")["tree"]["sha"]
    else:  # 空仓：先落一个种子提交
        seed = api("PUT", "/contents/.gitkeep", {"message": "chore: seed repository",
                                                 "content": "", "committer": NAME, "author": NAME})
        head_sha, base_tree = seed["commit"]["sha"], seed["commit"]["tree"]["sha"]
        files.append(".gitkeep")
    entries = [_entry(f) for f in files]
    entries.append({"path": ".gitkeep", "mode": "100644", "type": "blob", "sha": None})
    tree = api("POST", "/git/trees", {"base_tree": base_tree, "tree": entries})
    commit = api("POST", "/git/commits", {"message": message, "tree": tree["sha"],
                                          "parents": [head_sha], "author": NAME, "committer": NAME})
    api("PATCH", "/git/refs/heads/main", {"sha": commit["sha"], "force": False})
    print(f"{len(files)} files -> {commit['sha']}")


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """日志端点 302 到 Azure Blob；跨主机必须丢 Authorization，否则 401。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and "api.github.com" not in newurl:
            new.remove_header("Authorization")
        return new


def cmd_log(job_id, keyword=""):
    req = urllib.request.Request(f"{BASE}/actions/jobs/{job_id}/logs",
                                 headers={"Authorization": f"Bearer {TOK}", "User-Agent": "aitb-log",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.build_opener(_DropAuthOnRedirect).open(req, timeout=120) as r:
        data = r.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names, text = zf.namelist(), "\n".join(zf.read(n).decode("utf-8", "replace") for n in zf.namelist())
    except zipfile.BadZipFile:
        names, text = ["<plain>"], data.decode("utf-8", "replace")
    lines = text.splitlines()
    print(f"files={names}")
    if keyword:
        hits = [i for i, l in enumerate(lines) if keyword in l]
        for i in hits[:3]:
            print("\n".join(lines[max(0, i - 14): i + 8]))
        if not hits:
            print("\n".join(lines[-40:]))
    else:
        print("\n".join(lines[-60:]))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    mode = sys.argv[1]
    if mode == "files":
        cmd_files(sys.argv[2], sys.argv[3:])
    elif mode == "tree":
        cmd_tree(sys.argv[2])
    elif mode == "log":
        cmd_log(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    else:
        sys.exit(__doc__)
