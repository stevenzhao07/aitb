# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""四个内置适配器 + 插件注册表。

适配器契约（第三方可照此实现）：
    函数签名 fn(spec: dict, ctx: dict) -> (status, code, why, evidence, ms)
      status : "PASS" | "FAIL" | "SKIP" | "BLOCKED"
      code   : 见 codes.py（V 开头）
      why    : 一句话人话依据
      evidence: 可粘进报告的多行文本（stdout 尾部 / 命中明细）
      ms     : 耗时毫秒
注册方式（二选一）：
    1) 代码里 aitb.adapters.register("myname", fn)
    2) 在自己包的 pyproject 里声明 entry_points: [project.entry-points."aitb.adapters"] myname = "pkg.mod:fn"
       —— 引擎启动时自动发现（importlib.metadata），不需要改引擎。
"""
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import paths

ADAPTERS = {}
_PLUGINS_LOADED = False


def register(name, fn, replace=False):
    if name in ADAPTERS and not replace:
        raise ValueError(f"适配器 {name!r} 已存在（如需覆盖请 replace=True）")
    ADAPTERS[name] = fn
    return fn


def discover_plugins():
    """从已安装包的 entry point 发现第三方适配器；失败不影响内置四个。"""
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    _PLUGINS_LOADED = True
    try:
        from importlib.metadata import entry_points
    except Exception:
        return
    try:
        eps = entry_points()
        group = eps.select(group="aitb.adapters") if hasattr(eps, "select") else eps.get("aitb.adapters", [])
    except Exception:
        return
    for ep in group:
        try:
            register(ep.name, ep.load())
        except Exception as e:  # 插件坏了不许拖死引擎
            print(f"[warn] 第三方适配器 {ep.name} 加载失败：{e}", file=sys.stderr)


# ---------------- 执行 ----------------

def run_cmd(cmd, cwd=None, timeout=300, env=None):
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            shell=isinstance(cmd, str), env=env,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or ""), int((time.time() - t0) * 1000)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "")
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return 124, out + f"\n[timeout after {timeout}s]", int((time.time() - t0) * 1000)
    except Exception as e:
        return 125, f"[exception] {e}", int((time.time() - t0) * 1000)


def _tail(text, n=3):
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def a_cmd(spec, ctx):
    """跑一条命令；给了 expect 就按子串判，没给就按退出码判。"""
    cwd = paths.resolve(spec["cwd"]) if spec.get("cwd") else paths.root()
    timeout = spec.get("timeout", 300)
    rc, out, ms = run_cmd(spec["cmd"], cwd=cwd, timeout=timeout)
    expect = spec.get("expect")
    tail = _tail(out)
    if rc == 124:
        return "BLOCKED", "V201", f"超时 {timeout}s", tail, ms
    if expect and expect not in out:
        return "FAIL", "V101", f"未出现期望串：{expect!r}（rc={rc}）", tail, ms
    if not expect and rc != 0:
        return "FAIL", "V102", f"rc={rc}", tail, ms
    return "PASS", "V001", (f"含期望串 {expect!r}" if expect else "rc=0"), tail, ms


def a_files(spec, ctx):
    """核对文件在场与体积下限；base 缺省为项目根。"""
    base = paths.resolve(spec["base"]) if spec.get("base") else paths.root()
    miss, codes = [], []
    for item in spec["paths"]:
        p = Path(item["path"])
        if not p.is_absolute():
            p = base / p
        if not p.exists():
            miss.append(f"缺 {p}")
            codes.append("V103")
        elif p.stat().st_size < item.get("min_size", 1):
            miss.append(f"{p.name} 仅 {p.stat().st_size} B（需 ≥{item.get('min_size', 1)}）")
            codes.append("V104")
    if miss:
        return "FAIL", codes[0], "; ".join(miss), "", 0
    return "PASS", "V001", f"{len(spec['paths'])} 个文件在场", "", 0


def a_http(spec, ctx):
    """HTTP 探测；状态码不符即 FAIL，连不上记 BLOCKED（不折算 PASS）。"""
    rows, ok, blocked = [], True, False
    t0 = time.time()
    for t in spec["targets"]:
        url, want = t["url"], t.get("expect", 200)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "aitb"})
            with urllib.request.urlopen(req, timeout=t.get("timeout", 20)) as r:
                code = r.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            rows.append(f"{url} -> BLOCKED {type(e).__name__}")
            blocked = True
            continue
        if code != want:
            ok = False
            rows.append(f"{url} -> {code}（期望 {want}）")
        else:
            rows.append(f"{url} -> {code} ok")
    ms = int((time.time() - t0) * 1000)
    detail = "; ".join(rows)
    if ok:
        return "PASS", "V001", detail, "", ms
    if blocked and all("ok" not in r for r in rows):
        return "BLOCKED", "V203", detail, "", ms
    return "FAIL", "V105", detail, "", ms


_ABSENT_MARKS = ("not installed", "requested python version", "can't open", "cannot open",
                 "未安装", "no installed", "not found", "no suitable python runtime")


def a_pyver(spec, ctx):
    """环境矩阵：每个可用解释器跑同一条命令；缺席记 SKIP，在场但坏死记 BLOCKED。"""
    cand = spec.get("interpreters") or ["python", "python3", "py -3", "py -3.11", "py -3.12"]
    cwd = paths.resolve(spec["cwd"]) if spec.get("cwd") else paths.root()
    rows, ok, tried, blocked = [], True, 0, 0
    for it in cand:
        rc, out, _ = run_cmd(f'{it} -c "import sys;print(sys.version.split()[0])"', cwd=cwd, timeout=30)
        if rc == 124:
            blocked += 1
            rows.append(f"{it}: BLOCKED（版本探测超时）")
            continue
        if rc != 0:
            looks_absent = any(m.lower() in (out or "").lower() for m in _ABSENT_MARKS)
            exe = it.split()[0]
            if shutil.which(exe) and not looks_absent:
                blocked += 1
                rows.append(f"{it}: BLOCKED（在场但不可执行）")
            else:
                rows.append(f"{it}: 不在场")
            continue
        tried += 1
        ver = out.strip().splitlines()[-1] if out.strip() else "?"
        rc2, out2, _ = run_cmd(f"{it} {spec['script']}", cwd=cwd, timeout=spec.get("timeout", 300))
        if rc2 == 124:
            blocked += 1
            rows.append(f"{it} ({ver}): BLOCKED（执行超时）")
            continue
        good = rc2 == 0 and (spec.get("expect") in out2 if spec.get("expect") else True)
        rows.append(f"{it} ({ver}): {'ok' if good else 'FAIL'}")
        ok = ok and good
    detail = "; ".join(rows)
    if tried == 0 and blocked == 0:
        return "SKIP", "V302", "无任何解释器可用", detail, 0
    if blocked:
        return "BLOCKED", "V202", f"{blocked} 个解释器无法判定（超时或不可执行）", detail, 0
    return ("PASS" if ok else "FAIL"), ("V001" if ok else "V106"), f"{tried} 个解释器跑通", detail, 0


for _n, _f in (("cmd", a_cmd), ("files", a_files), ("http", a_http), ("pyver", a_pyver)):
    register(_n, _f)
