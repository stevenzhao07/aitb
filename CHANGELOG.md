# Changelog

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本遵循语义化版本。

## [0.1.0] — 2026-11-23

首次把内部试真台整理成可分发形态。这一版的目标只有一个：**别人能装上、能跑、能看到它红。**

### Added
- `aitb` 包与 `aitb` 命令行（`run / list / validate / doctor / version`），零运行时依赖。
- 内置预设 `selftest`（证明它会红）与 `doctrine`（T1–T5 五条不变量机检）。
- 四类适配器：`cmd` / `files` / `http` / `pyver`；第三方适配器可用 entry point 注册。
- 机器可读输出：JUnit XML（CI 面板）、SARIF v2.1.0（GitHub Code Scanning）、JSON。
- 原因码目录（`codes.py`）：配置层 `E0xx`、判定层 `Vxxx`，脚本可按码分流。
- `preset` 的 JSON Schema（`schema/preset.schema.json`）与语义校验 `aitb validate`。
- 证据包五件套（`run.json / verdicts.json / report.md / snapshot.html / manifest.json`）。

### Changed（相对内部版的关键结构修复）
- **包内不再出现任何本机绝对路径**：相对路径一律相对项目根（`AITB_ROOT`），预设只允许 `${VAR}`。
- **缺变量从"静默放行"改为硬失败**（退出码 3）：旧行为会把未展开的 `${X}` 传到下游，
  最后以"文件不存在"的名义失败，排查方向全错。
- 退出码明确化为四档：`0` 全过 / `1` 有 FAIL / `2` strict 下有 SKIP 或 BLOCKED / `3` 配置错误。
- 判定附原因码；负控失效单独记 `V107`，不再与普通失败混在一起。
- 渲染器拆出 `reports.py`，md/html/junit/sarif 四路同源，避免各写一套。

### Fixed（首发前由 CI 抓到的两个真缺陷）
- **Windows 上中文判据会让整次运行崩掉**：控制台默认 cp1252，`UnicodeEncodeError` 在打印判定原因时抛出，
  退出码变成 1 且没有证据包。CLI 与独立探针都改成把 stdout/stderr 重设为 UTF-8（`errors="replace"`）。
  本机（中文代码页）跑不出来，是 windows-latest 抓到的。
- 负控步骤的 shell 断言写成 `aitb selftest | tee`，`pipefail` 把"按设计失败"的退出码 1 直接算作 step 失败。

### Known limits
- 单维护者项目：bus factor = 1，达不到 OpenSSF gold 的"两位无关联贡献者"。
- `pyver` 适配器在无解释器的机器上只能给 SKIP，不能证明代码在别的解释器上跑得通。
- 未做签名发布；下载校验目前只有 `manifest.json` 的哈希。
