# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""路径与目录约定。

设计原则（这是"能给别人用"的技术前提）：包内不存任何本机绝对路径。
  - 内置预设随包分发，里面只允许 ${VAR} 与相对路径；
  - 相对路径一律相对"项目根"（AITB_ROOT，默认当前工作目录），不相对包目录；
  - 运行产物默认写到 <root>/.aitb/runs，绝不写进 site-packages。
"""
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent


def root() -> Path:
    """项目根：AITB_ROOT > 当前工作目录。"""
    env = os.environ.get("AITB_ROOT")
    return Path(env).expanduser().resolve() if env else Path.cwd().resolve()


def runs_dir() -> Path:
    """证据包目录：AITB_RUNS > <root>/.aitb/runs。"""
    env = os.environ.get("AITB_RUNS")
    if env:
        return Path(env).expanduser()
    return root() / ".aitb" / "runs"


def preset_dirs() -> list:
    """预设搜索路径：内置 → AITB_PRESETS（可多个，用 os.pathsep 分隔）→ <root>/presets。

    三者是**并存**关系，不是替换：内置的 selftest / doctrine 永远可用。
    """
    dirs = [PKG / "presets"]
    env = os.environ.get("AITB_PRESETS")
    if env:
        for part in env.split(os.pathsep):
            p = Path(part).expanduser()
            if p.is_dir():
                dirs.append(p)
    local = root() / "presets"
    if local.is_dir() and local not in dirs:
        dirs.append(local)
    return dirs


def resolve(path_like) -> Path:
    """把 preset 里的路径解析成绝对路径：绝对路径原样，相对路径相对项目根。"""
    p = Path(str(path_like)).expanduser()
    return p if p.is_absolute() else (root() / p)
