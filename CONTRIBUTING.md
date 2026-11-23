# 贡献指南

## 最快的一条贡献路径：提一个 preset，不改代码

工作线是**数据**，不是代码。想加一项验收，提交一个 JSON 就行：

```json
{
  "name": "myline",
  "title": "我的工作线",
  "preset_version": 1,
  "profile": "standard",
  "checks": [
    {"id": "myline.artifacts-present", "type": "files",
     "paths": [{"path": "${MY_PROJECT}/out/report.md", "min_size": 2000}]},
    {"id": "myline.tests-green", "type": "cmd", "cwd": "${MY_PROJECT}",
     "cmd": "python run_all.py", "expect": "RESULT: ALL EXPECTATIONS MET", "timeout": 600}
  ]
}
```

规则（`aitb validate` 会机检，别靠人盯）：

- `name` 与 `id` 全小写，只允许 `a-z0-9._-`；
- **预设里不许出现本机绝对路径**，一律 `${VAR}`，变量写进 `aitb.config.json`（已 gitignore）；
- 每条检查要么给 `expect` 子串，要么给可判的退出码语义 —— 不要写"看起来通过就算过"；
- 想让一条检查"按设计失败"（做负控），写 `"expect_status": "FAIL"`；
- 有边界的写进 `notes`：凡是被后续运行推翻的断言，都是缺陷。

## 改引擎的门槛

1. 先跑 `python -m unittest discover -s tests`，必须全绿；
2. 再加一条新测试覆盖你改的行为 —— 没测试的行为视为没有这个行为；
3. 跑 `aitb doctrine`，五条不变量必须仍然成立（尤其是 T1：弄坏它必须能红）；
4. 任何改动若让 `selftest` 不再产生 FAIL，直接拒收 —— 那是把台子弄瞎了。

## 提交格式

- 提交信息用 `area: what changed and why`；
- 版本号遵循语义化版本：判定语义或退出码语义变化 = 大版本；新增适配器/输出格式 = 小版本；
- 每个源文件首行保留 SPDX 头：`# SPDX-License-Identifier: Apache-2.0`。

## 行为准则

参见 `CODE_OF_CONDUCT.md`。技术争论欢迎，人身攻击不接受。

## 第三方适配器

两类用法都不需要改引擎：

```python
# 用法一：自己项目里注册
from aitb import adapters
adapters.register("mytool", lambda spec, ctx: ("PASS", "V001", "ok", "", 0))
```

```toml
# 用法二：发布成包，靠 entry point 被发现
[project.entry-points."aitb.adapters"]
mytool = "mypkg.adapter:check"
```

适配器契约固定为 `fn(spec, ctx) -> (status, code, why, evidence, ms)`；
`status` 只能取 `PASS/FAIL/SKIP/BLOCKED`，`code` 用 `codes.py` 里已登记的 V 码或自行申请。
**不许把"没判到"写成 PASS** —— 这是本项目唯一不能妥协的一条。
