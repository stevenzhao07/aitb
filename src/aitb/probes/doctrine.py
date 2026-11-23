# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""试真法 T1–T5 机检（公开版，不依赖任何本机路径）。

判的是台子自己：它能不能红、跳过会不会落码、空文件能不能糊过去、
文档承诺是否真的有实物、证据包哈希能不能重算。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from aitb import adapters, engine, paths, __version__

# 这个探针是独立进程（不经 aitb.cli），所以自己也要把标准输出设成 UTF-8：
# Windows 默认 cp1252，中文 detail 一打就 UnicodeEncodeError，整条探针被判成 rc=1。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

rows = []


def check(code, name, ok, detail):
    rows.append((code, name, bool(ok), detail))


def _run_engine(preset_file, *extra):
    cmd = [sys.executable, "-m", "aitb", "run", str(preset_file)] + list(extra)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


tmp = Path(tempfile.mkdtemp(prefix="aitb-doctrine-"))

# --- T1 反照：弄坏它，必须红 ---
bad = tmp / "doctrine-broken.json"
bad.write_text(json.dumps({"name": "doctrine-broken", "checks": [
    {"id": "doctrine.broken.expect-missing", "type": "cmd",
     "cmd": f'"{sys.executable}" -c "print(123)"', "expect": "THIS LINE NEVER PRINTS"}]},
    ensure_ascii=False), encoding="utf-8")
p = _run_engine(bad)
check("T1", "反照·弄坏后必须失败", p.returncode == engine.EXIT_FAIL and "FAIL" in (p.stdout or ""),
      f"rc={p.returncode}")

# --- T2 落码：SKIP 必须进退出码 ---
skip = tmp / "doctrine-skip.json"
skip.write_text(json.dumps({"name": "doctrine-skip", "checks": [
    {"id": "doctrine.skip.network", "type": "http", "needs_network": True,
     "targets": [{"url": "https://example.invalid/", "expect": 200}]}]}), encoding="utf-8")
p = _run_engine(skip, "--offline", "--strict")
check("T2", "落码·SKIP 进退出码",
      p.returncode == engine.EXIT_STRICT_INCOMPLETE, f"offline+strict rc={p.returncode}")

# --- T3 审据：空文件配 min_size，必须拒绝 ---
with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
    tiny = Path(f.name)
st, code, why, _, _ = adapters.a_files({"paths": [{"path": str(tiny), "min_size": 100}]}, {})
check("T3", "审据·空文件不算通过", st == "FAIL" and code == "V104", f"{st}/{code} {why}")
tiny.unlink(missing_ok=True)

# --- T4 兑现：内置索引与实物对账；在源码树里再加一层 README 点名 ---
# 装成包之后 README 不随包走（它是仓库文档），所以机检以包内 _index.json 为准；
# 若当前是源码树（README 在场），则额外要求 README 点名每一个内置预设。
idx_file = paths.PKG / "presets" / "_index.json"
idx = json.loads(idx_file.read_text(encoding="utf-8")).get("presets", []) if idx_file.exists() else []
have = sorted(p.stem for p in (paths.PKG / "presets").glob("*.json") if not p.name.startswith("_"))
readme = paths.PKG.parents[1] / "README.md"
readme_text = readme.read_text(encoding="utf-8") if readme.exists() else ""
unmentioned = [n for n in have if readme_text and f"`{n}`" not in readme_text]
check("T4", "兑现·文档承诺对账", sorted(idx) == have and not unmentioned,
      f"索引 {sorted(idx)} / 实物 {have} / README 漏点名 {unmentioned or '无'}")

# --- T5 辨身：证据包哈希可重算，计数自洽 ---
import hashlib
run_dirs = sorted([d for d in paths.runs_dir().iterdir() if d.is_dir()]) if paths.runs_dir().is_dir() else []
bad_hash, checked = [], 0
for d in run_dirs[-3:]:
    mf = d / "manifest.json"
    if not mf.exists():
        continue
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    for name, h in (manifest.get("files") or {}).items():
        f = d / name
        checked += 1
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != h:
            bad_hash.append(f"{d.name}/{name}")
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    verdicts = json.loads((d / "verdicts.json").read_text(encoding="utf-8"))
    if sum((run.get("counts") or {}).values()) != len(verdicts):
        bad_hash.append(f"{d.name}/counts")
check("T5", "辨身·数字可回溯", checked > 0 and not bad_hash, f"核 {checked} 条哈希，异常 {bad_hash or '无'}")

for code, name, ok, detail in rows:
    print(f"[{'ok ' if ok else 'FAIL'}] {code} {name:<18} {detail}")
n = sum(1 for r in rows if r[2])
print(f"\nDOCTRINE: {n}/{len(rows)} invariants hold  (aitb {__version__})")
sys.exit(0 if n == len(rows) else 5)
