# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""命令行入口。

    aitb run <preset>           跑一次，产出证据包
    aitb <preset>               同上（兼容简写）
    aitb list                   列出所有可见 preset
    aitb validate <preset|--all> 只校验 preset，不跑
    aitb doctor                 环境自检：变量从哪来、缺哪些、preset 从哪找
    aitb version

退出码：0 全过 / 1 有 FAIL / 2 --strict 下存在 SKIP 或 BLOCKED / 3 配置或用法错误
"""
import argparse
import json
import sys
from pathlib import Path

from . import __version__, adapters, engine, paths, variables

SUBCOMMANDS = ("run", "list", "validate", "doctor", "version", "help")


def _preset_files(d):
    """目录下的 preset 文件；下划线开头的（如 _index.json）是元数据，不算预设。"""
    return [p for p in sorted(d.glob("*.json")) if not p.name.startswith("_")]


def _print_presets():
    seen = {}
    for d in paths.preset_dirs():
        for p in _preset_files(d):
            seen.setdefault(p.stem, p)
    if not seen:
        print("没有找到任何 preset。用 AITB_PRESETS 指到你的预设目录。")
        return
    for name, p in sorted(seen.items()):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            print(f"{name:<24} <非法 JSON>  {p}")
            continue
        print(f"{d.get('name', name):<24} {d.get('title', ''):<34} {p}")


def _cmd_validate(args):
    engine.adapters.discover_plugins()
    targets = []
    if args.all:
        for d in paths.preset_dirs():
            targets += _preset_files(d)
    elif args.preset:
        try:
            targets = [engine.find_preset(args.preset)]
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return engine.EXIT_CONFIG
    else:
        print("给一个 preset 名，或 --all", file=sys.stderr)
        return engine.EXIT_CONFIG
    bad = 0
    for p in targets:
        name = p.stem
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            bad += 1
            print(f"[INVALID] {name}\n    E009 不是合法 JSON（{e}）")
            continue
        errs = engine.validate_preset(raw)
        if errs:
            bad += 1
            print(f"[INVALID] {name}")
            for code, msg in errs:
                print(f"    {code} {msg}")
        else:
            print(f"[ok     ] {name}  ({len(raw.get('checks', []))} checks)")
    return 0 if bad == 0 else engine.EXIT_CONFIG


def _cmd_doctor(args):
    v, src, is_ex = variables.load_vars()
    print(f"aitb            {__version__}")
    print(f"python          {sys.version.split()[0]}")
    print(f"project root    {paths.root()}")
    print(f"runs            {paths.runs_dir()}")
    print(f"variables from  {src or '(无变量文件；只用内置变量)'}" + ("  <- 这是样例文件" if is_ex else ""))
    print(f"builtin vars    {', '.join(sorted(variables.builtin_vars()))}")
    print("preset dirs:")
    for d in paths.preset_dirs():
        n = len(_preset_files(d))
        print(f"  {d}  ({n} 个)")
    adapters.discover_plugins()
    print(f"adapters        {', '.join(sorted(adapters.ADAPTERS))}")
    schema = paths.PKG / "schema" / "preset.schema.json"
    print(f"preset schema   {schema}" + ("" if schema.exists() else "  （缺失）"))
    return 0


def _cmd_run(args):
    try:
        preset, preset_path = engine.load_preset(args.preset, on_warning=lambda m: print(f"[warn] {m}", file=sys.stderr))
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return engine.EXIT_CONFIG
    except variables.MissingVars as e:
        print(f"E006 {e}", file=sys.stderr)
        print("→ 在作业目录建 aitb.config.json：{\"vars\": {\"<名字>\": \"<值>\"}}", file=sys.stderr)
        return engine.EXIT_CONFIG
    except engine.PresetError as e:
        print(f"{e}", file=sys.stderr)
        return engine.EXIT_CONFIG

    errs = engine.validate_preset(preset)
    if errs:
        for code, msg in errs:
            print(f"{code} {msg}", file=sys.stderr)
        return engine.EXIT_CONFIG

    if args.prune:
        _prune(args.prune)

    res = engine.execute(preset, offline=args.offline, strict=args.strict)
    rc = res.rc
    if rc == engine.EXIT_FAIL and args.allow_red and res.by_design:
        rc = engine.EXIT_OK

    fmt = args.format
    if fmt:
        out = {
            "json": lambda: __import__("aitb.reports", fromlist=["x"]).render_json(res.verdicts, preset, res.counts),
            "junit": lambda: __import__("aitb.reports", fromlist=["x"]).render_junit(preset, res.verdicts, res.counts, res.meta),
            "sarif": lambda: __import__("aitb.reports", fromlist=["x"]).render_sarif(
                preset, res.verdicts, res.counts, res.meta, preset_uri=str(preset_path)),
            "md": lambda: (res.rdir / "report.md").read_text(encoding="utf-8"),
        }[fmt]()
        if args.out:
            Path(args.out).write_text(out, encoding="utf-8")
            print(f"written {args.out} ({fmt})")
        else:
            print(out)
    return rc


def _prune(n):
    root = paths.runs_dir()
    if not root.is_dir():
        return
    dirs = sorted([d for d in root.iterdir() if d.is_dir() and not d.is_symlink()],
                  key=lambda d: d.name, reverse=True)
    for d in dirs[n:]:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def build_parser():
    ap = argparse.ArgumentParser(prog="aitb", description="AITB — Assurance Instrument Test Bench（试真台）")
    ap.add_argument("--version", action="store_true", help="打印版本")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="跑一个 preset")
    r.add_argument("preset")
    r.add_argument("--offline", action="store_true", help="跳过 needs_network 的检查（记 SKIP）")
    r.add_argument("--strict", action="store_true", help="SKIP/BLOCKED 也进退出码")
    r.add_argument("--allow-red", action="store_true", help="当全部 FAIL 都来自负控时，退出码按 0")
    r.add_argument("--format", choices=("md", "json", "junit", "sarif"))
    r.add_argument("--out", help="配合 --format 写到文件")
    r.add_argument("--prune", type=int, default=0, metavar="N", help="只保留最近 N 个运行目录")

    sub.add_parser("list", help="列出 preset")
    va = sub.add_parser("validate", help="校验 preset（不执行）")
    va.add_argument("preset", nargs="?")
    va.add_argument("--all", action="store_true")
    sub.add_parser("doctor", help="环境自检")
    sub.add_parser("version", help="打印版本")
    sub.add_parser("help", help="帮助")
    return ap


def _ensure_utf8_streams():
    """Windows 控制台默认 cp1252，中文判定原因一打就 UnicodeEncodeError。

    这不是"显示问题"，它会让整次运行崩掉 —— CI 就是这么抓到它的（windows-latest）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None):
    _ensure_utf8_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["run"] + argv          # 兼容 `aitb selftest --strict` 这种简写
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.version or a.cmd == "version":
        print(f"aitb {__version__}")
        return 0
    if a.cmd in (None, "help"):
        ap.print_help()
        return 0
    if a.cmd == "list":
        _print_presets()
        return 0
    if a.cmd == "validate":
        return _cmd_validate(a)
    if a.cmd == "doctor":
        return _cmd_doctor(a)
    if a.cmd == "run":
        return _cmd_run(a)
    ap.print_help()
    return engine.EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
