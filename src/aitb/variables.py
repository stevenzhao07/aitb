# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""变量展开。

规则：
  - 内置变量 AITB_PKG / AITB_ROOT / AITB_RUNS 永远可用；
  - 用户变量来自 AITB_CONFIG 指定的文件，否则依次找 <root>/aitb.config.json、
    <root>/config.local.json、<root>/config.example.json（后者只是样例，命中它时会给 warning）；
  - **缺变量是硬失败**（raise MissingVars），不静默留 ${X} 到下游 —— 这是 P0 的结构性修复：
    旧版把未展开的串原样传下去，检查会以"文件不存在"的名义失败，排查方向全错。
"""
import json
import os
import re
import sys
from pathlib import Path

from . import paths

PAT = re.compile(r"\${([A-Za-z0-9_]+)}")
PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


class MissingVars(Exception):
    def __init__(self, names, source=None):
        self.names = sorted(set(names))
        self.source = str(source) if source else None
        msg = "变量未解析：" + ", ".join(self.names)
        if source:
            msg += f"（变量文件：{source}）"
        super().__init__(msg)


def builtin_vars() -> dict:
    return {
        "AITB_PKG": str(paths.PKG),
        "AITB_ROOT": str(paths.root()),
        "AITB_RUNS": str(paths.runs_dir()),
        # 当前解释器：预设里用它代替裸 "python"，否则 macOS 上 python 可能不存在
        "AITB_PYTHON": sys.executable,
    }


def config_candidates() -> list:
    env = os.environ.get("AITB_CONFIG")
    if env:
        return [Path(env).expanduser()]
    root = paths.root()
    return [root / "aitb.config.json", root / "config.local.json", root / "config.example.json"]


def load_vars() -> tuple:
    """返回 (vars, source_path_or_None, is_example)。"""
    for p in config_candidates():
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ValueError(f"变量文件不是合法 JSON：{p}（{e}）")
            v = dict(builtin_vars())
            v.update(data.get("vars", {}) or {})
            return v, p, p.name == "config.example.json"
    return dict(builtin_vars()), None, False


def expand(obj, v):
    if isinstance(obj, str):
        return PAT.sub(lambda m: str(v.get(m.group(1), m.group(0))), obj)
    if isinstance(obj, list):
        return [expand(x, v) for x in obj]
    if isinstance(obj, dict):
        # 下划线开头的键是注释（_schema/_comment），不参与展开与缺变量判定
        return {k: (x if k.startswith("_") else expand(x, v)) for k, x in obj.items()}
    return obj


def unresolved(obj) -> list:
    """展开后仍残留的 ${X} 名字（注释键不算）。"""
    found = []
    if isinstance(obj, str):
        found += PLACEHOLDER.findall(obj)
    elif isinstance(obj, list):
        for x in obj:
            found += unresolved(x)
    elif isinstance(obj, dict):
        for k, x in obj.items():
            if not k.startswith("_"):
                found += unresolved(x)
    return found
