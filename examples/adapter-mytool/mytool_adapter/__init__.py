# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""示例第三方适配器：把"某个目录里的告警数"当成一条检查。

真实项目里把它换成你自己工具的调用即可；契约不变。
"""
from pathlib import Path

from aitb import paths

LEVELS = {"none": 0, "low": 1, "medium": 2, "high": 3}


def check(spec, ctx):
    target = paths.resolve(spec.get("target", "."))
    p = Path(target)
    if not p.exists():
        # 没判到 —— 不是 FAIL，更不是 PASS
        return "BLOCKED", "V203", f"目标不存在：{p}", "", 0
    report = p / "findings.json"
    if not report.exists():
        return "BLOCKED", "V203", f"缺 findings.json：{report}", "", 0
    import json
    data = json.loads(report.read_text(encoding="utf-8"))
    worst = max((LEVELS.get(f.get("level", "low"), 1) for f in data.get("findings", [])), default=0)
    want = LEVELS.get(spec.get("expect_level", "none"), 0)
    detail = f"最深等级={worst}（阈值 {want}）"
    if worst > want:
        return "FAIL", "V101", f"超出阈值：{detail}", detail, 0
    return "PASS", "V001", detail, detail, 0
