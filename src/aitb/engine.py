# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""判定引擎：preset → 逐项判定 → 证据包 → 退出码。

不变量（这套台子存在的原因）：
  T1 反照：它必须有能力变红（selftest 就是这条的常驻证明）
  T2 落码：SKIP / BLOCKED 不是 PASS，--strict 下进退出码
  T3 审据：声明与证据分开，体积下限类判据不能被空文件糊弄
  T4 兑现：文档承诺与仓内实物对账
  T5 辨身：每次运行五件套互相记哈希，数字可回溯
"""
import hashlib
import json
import platform
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import adapters, paths, variables
from .codes import explain

PRESET_VERSION = 1
VERDICTS = ("PASS", "FAIL", "SKIP", "BLOCKED")
CHECK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
REQUIRED = {"cmd": ("cmd",), "files": ("paths",), "http": ("targets",), "pyver": ("script",)}

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_STRICT_INCOMPLETE = 2
EXIT_CONFIG = 3


class PresetError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class RunResult:
    rc: int
    rdir: Path
    verdicts: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    @property
    def by_design(self):
        """红色是否全部"按设计"：每条 FAIL 都是负控，且没有负控失效。"""
        if not self.verdicts:
            return False
        if any(v.get("negctl_broken") for v in self.verdicts):
            return False
        return all(v["status"] != "FAIL" or v.get("negative_control") for v in self.verdicts)


def sha256_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def find_preset(name):
    # 允许直接给文件路径（绝对，或相对项目根），方便 CI 里指向临时生成的预设
    if str(name).endswith(".json"):
        direct = Path(name) if Path(name).is_absolute() else paths.root() / name
        if direct.is_file():
            return direct
    searched = []
    for d in paths.preset_dirs():
        searched.append(d)
        p = d / f"{name}.json"
        if p.exists():
            return p
    raise FileNotFoundError(
        f"找不到 preset {name!r}。已搜索：\n  " + "\n  ".join(str(d) for d in searched)
        + "\n用 AITB_PRESETS 指到你的预设目录，或在项目根建 presets/。")


def load_preset(name, on_warning=None):
    p = find_preset(name)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PresetError("E009", f"{p} 不是合法 JSON（{e}）")
    v, src, is_example = variables.load_vars()
    if is_example and on_warning:
        on_warning(f"用的变量样例文件 {src}：真实路径请放进 aitb.config.json")
    preset = variables.expand(raw, v)
    missing = variables.unresolved(preset)
    if missing:
        raise variables.MissingVars(missing, src)
    preset.setdefault("name", p.stem)
    return preset, p


def validate_preset(preset, adapter_map=None):
    """语义校验。返回 [(code, message)]，空列表 = 合法。

    比 JSON Schema 多做一层"跑得起来吗"的判断：适配器在不在、必填字段有没有、id 冲不冲突。
    """
    errs = []
    amap = adapter_map or adapters.ADAPTERS
    if not isinstance(preset.get("name"), str) or not CHECK_ID.match(str(preset.get("name"))):
        errs.append(("E001", f"name 缺失或不合规：{preset.get('name')!r}"))
    pv = preset.get("preset_version", PRESET_VERSION)
    if pv != PRESET_VERSION:
        errs.append(("E007", f"preset_version={pv}，本引擎支持 {PRESET_VERSION}"))
    checks = preset.get("checks")
    if not isinstance(checks, list) or not checks:
        errs.append(("E001", "checks 缺失或为空"))
        return errs
    seen = set()
    for i, c in enumerate(checks):
        cid = c.get("id")
        where = f"checks[{i}]"
        if not isinstance(cid, str) or not CHECK_ID.match(cid):
            errs.append(("E008", f"{where} id 不合规：{cid!r}"))
        elif cid in seen:
            errs.append(("E002", f"{where} id 重复：{cid}"))
        else:
            seen.add(cid)
        t = c.get("type")
        if t not in amap:
            errs.append(("E003", f"{where} 未知适配器 {t!r}（可用：{', '.join(sorted(amap))}）"))
            continue
        for k in REQUIRED.get(t, ()):
            if not c.get(k):
                errs.append(("E004", f"{where}（{t}）缺少必填字段 {k!r}"))
        if c.get("expect_status", "PASS") not in ("PASS", "FAIL"):
            errs.append(("E005", f"{where} expect_status={c.get('expect_status')!r}（只允许 PASS/FAIL）"))
    return errs


def execute(preset, offline=False, strict=False, runs=None, echo=True):
    adapters.discover_plugins()
    root = Path(runs) if runs else paths.runs_dir()
    run_id = time.strftime("%Y%m%dT%H%M%S")
    rdir = root / f"{run_id}_{preset['name']}"
    rdir.mkdir(parents=True, exist_ok=True)

    ctx = {"offline": offline}
    rows = []
    for spec in preset["checks"]:
        cid = spec.get("id", "?")
        if offline and spec.get("needs_network"):
            rows.append({"id": cid, "type": spec.get("type"), "status": "SKIP", "code": "V301",
                         "why": "离线模式跳过（needs_network）", "evidence": "", "ms": 0,
                         "negative_control": False})
            if echo:
                print(f"[SKIP   ] {cid:<40} 离线模式跳过")
            continue
        fn = adapters.ADAPTERS.get(spec.get("type"))
        if fn is None:
            rows.append({"id": cid, "type": spec.get("type"), "status": "BLOCKED", "code": "E003",
                         "why": f"未知适配器 {spec.get('type')}", "evidence": "", "ms": 0,
                         "negative_control": False})
            if echo:
                print(f"[BLOCKED] {cid:<40} 未知适配器 {spec.get('type')}")
            continue
        t0 = time.time()
        status, code, why, evidence, ms = fn(spec, ctx)
        want = spec.get("expect_status", "PASS")
        neg = want == "FAIL"  # 负控：这条被要求必须失败；它失败才是"按设计变红"
        broken = False
        if neg and status != "FAIL":
            # 负控失效：期望它失败，它却通过了 —— 这台子在这一项上失明了
            broken = True
            code = "V107"
            why = f"负控失效：期望它失败，结果 {status}（{why}）"
            status = "FAIL"
        elif want == "PASS" and status != "PASS":
            # 正常检查没通过：保留它自己的原因（超时/缺文件/没解释器都不一样），不改写
            pass
        rows.append({"id": cid, "type": spec.get("type"), "status": status, "code": code,
                     "why": why, "evidence": evidence, "ms": ms or int((time.time() - t0) * 1000),
                     "negative_control": neg, "negctl_broken": broken})
        if echo:
            tag = "[NEG-CTRL]" if neg else "          "
            print(f"[{status:<7}]{tag} {cid:<40} {why}")

    counts = {k: sum(1 for r in rows if r["status"] == k) for k in VERDICTS}
    meta = {
        "run_id": run_id, "preset": preset["name"], "title": preset.get("title", preset["name"]),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "host": platform.node(),
        "os": platform.platform(), "python": sys.version.split()[0],
        "aitb_version": __import__("aitb").__version__, "counts": counts, "strict": strict,
    }
    (rdir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (rdir / "verdicts.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    from . import reports  # 延迟导入，避免循环
    (rdir / "report.md").write_text(reports.render_markdown(preset, rows, counts), encoding="utf-8")
    (rdir / "snapshot.html").write_text(reports.render_html(preset, rows, counts, meta), encoding="utf-8")

    manifest = {"run_id": run_id, "files": {}}
    for f in sorted(rdir.iterdir()):
        if f.name != "manifest.json":
            manifest["files"][f.name] = sha256_file(f)
    (rdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    _point_latest(root, rdir)

    if echo:
        print(f"\n{counts}  ->  {rdir}")
    rc = EXIT_FAIL if counts["FAIL"] else (
        EXIT_STRICT_INCOMPLETE if strict and (counts["SKIP"] + counts["BLOCKED"]) else EXIT_OK)
    if echo and rc == EXIT_STRICT_INCOMPLETE:
        print("STRICT: SKIP/BLOCKED 视为未过（T2 落码）")
    return RunResult(rc=rc, rdir=rdir, verdicts=rows, counts=counts, meta=meta)


def _point_latest(root, rdir):
    link = Path(root) / "latest"
    try:
        if link.exists() or link.is_symlink():
            try:
                link.unlink()
            except Exception:
                shutil.rmtree(link, ignore_errors=True)
        link.symlink_to(rdir.name, target_is_directory=True)
    except Exception:
        (Path(root) / "latest.txt").write_text(rdir.name, encoding="utf-8")


def check_codes(rows):
    """把出现在本次运行的原因码翻成人话，便于报告附录。"""
    seen = {}
    for r in rows:
        seen.setdefault(r.get("code", "?"), explain(r.get("code", "?")))
    return seen
