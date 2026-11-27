# AITB — Assurance Instrument Test Bench

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/stevenzhao07/aitb/HEAD)

[![ci](https://github.com/stevenzhao07/aitb/actions/workflows/ci.yml/badge.svg)](https://github.com/stevenzhao07/aitb/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

A preset-driven acceptance bench. One run = one evidence package + one exit code.
Anyone can re-run it and get the same verdict, because the checks are data, not code.

**It is built to go red.** A bench that cannot fail is a rubber stamp; this one ships a
`selftest` preset whose job is to fail, so you can verify the instrument before you trust it.

```bash
pip install .
aitb selftest            # exit 1 — three checks fail by design
aitb selftest --allow-red # exit 0 — every FAIL is a negative control
aitb doctrine            # five invariants of the bench itself must hold
```

## What it does

- **Preset in, evidence out.** `presets/*.json` → per-check verdicts → a five-file run
  directory (`run.json`, `verdicts.json`, `report.md`, `snapshot.html`, `manifest.json`),
  the last of which records a SHA-256 for each of the other four.
- **Four states, never confused.** `PASS` / `FAIL` (judged, and bad) / `BLOCKED` (not judged:
  timeout, broken tool, unreachable environment) / `SKIP` (deliberately not run). Only `PASS`
  is a pass.
- **Exit codes carry the verdict.** `0` all pass · `1` any FAIL · `2` `--strict` and some
  SKIP/BLOCKED remain · `3` config or usage error.
- **Machine-readable for CI.** JUnit XML for CI dashboards, SARIF v2.1.0 for GitHub Code
  Scanning, JSON for anything else.
- **Reason codes.** `E0xx` for preset/config problems caught before the run, `Vxxx` for
  verdicts, so a pipeline can branch on the cause instead of grepping prose.
- **Zero runtime dependencies.** Standard library only. It runs where Python runs.

## Why the states are separate

Most harnesses have pass/fail and quietly collapse "we couldn't judge it" into one of them.
That is how a benchmark reports 70% when a third of its cases never ran. Here `BLOCKED` and
`SKIP` are first-class, they are counted, and under `--strict` they fail the gate.

## Install & configure

```bash
pip install .
aitb doctor        # where variables come from, where presets are found, adapters registered
```

Local paths never live in presets. Put them in `aitb.config.json` (gitignored) and reference
them as `${NAME}`; a missing variable is a hard failure (exit 3), not a silent `${NAME}`
leaking into a file check.

```json
{"vars": {"MY_PROJECT": "C:/path/to/project"}}
```

## Writing a preset

```json
{
  "name": "myline",
  "title": "My line of work",
  "preset_version": 1,
  "checks": [
    {"id": "myline.report-exists", "type": "files",
     "paths": [{"path": "${MY_PROJECT}/out/report.md", "min_size": 2000}]},
    {"id": "myline.tests-green", "type": "cmd", "cwd": "${MY_PROJECT}",
     "cmd": "python run_all.py", "expect": "RESULT: ALL EXPECTATIONS MET", "timeout": 600},
    {"id": "myline.must-fail", "type": "cmd", "cmd": "python -c \"print('nope')\"",
     "expect": "gone", "expect_status": "FAIL"}
  ]
}
```

`aitb validate myline` checks it mechanically (unique ids, known adapter, required fields).
See `docs/QUICKSTART.md` for CI wiring and `src/aitb/schema/preset.schema.json` for editor
completion (it ships inside the wheel, so `aitb preset-schema --print` style lookups are not needed
— editors can point at the installed path shown by `aitb doctor`).

## Bundled presets

| preset | what it is for |
|---|---|
| `selftest` | proves the bench can go red; use `--allow-red` as a health check |
| `doctrine` | the five invariants of the instrument itself: can-red, exit-code, evidence, follow-through, identity |

## What this is not

- **Not a certification.** It produces verdicts about the thing it was pointed at. There is no
  accreditation body behind it, and no trademark. Do not describe a passing run as "certified".
- **Not a benchmark leaderboard.** Coverage is whatever your presets cover; a green run says
  "these checks pass", not "this is good".
- **Not maintained by a team.** Bus factor is 1 (`CHANGELOG.md` says so plainly). OpenSSF gold
  is out of reach by construction; passing is the realistic target.

## Contributing

A new line of work is a JSON file, not a code change — see `CONTRIBUTING.md`. Third-party
adapters register through the `aitb.adapters` entry point and need no fork.
Security reports: `SECURITY.md` (silent-pass bugs get 7-day handling).

---

# 中文

**AITB（Assurance Instrument Test Bench · 试真台）**：清单驱动的验收台。一次运行 = 一个证据包 + 一个退出码；
检查是数据不是代码，所以任何人复跑都应得到同一结论。

它**被造来会红**：`selftest` 的三条检查按设计失败，用来先验证仪器、再相信结论。

```bash
pip install .
aitb selftest             # 退出码 1，三条按设计失败
aitb selftest --allow-red # 退出码 0，FAIL 全部来自负控
aitb doctrine             # 仪器自身五条不变量
```

四态：`PASS` 通过 / `FAIL` 判到了且不合格 / `BLOCKED` **没判到** / `SKIP` 主动跳过。
后两种在任何统计里都不许折算成通过；`--strict` 下它们进退出码（`2`）。

预设里**不允许出现本机绝对路径**：路径走 `aitb.config.json` 的 `${VAR}`，缺变量是硬失败（退出码 3）。
这条是"别人能用"的前提，不是洁癖。

对外全称：**Assurance Instrument Test Bench（试真台）**，不裸写缩写。
