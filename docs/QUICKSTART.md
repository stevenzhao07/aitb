# Quickstart（10 分钟，从零到第一条自己写的检查）

## 1 装

```bash
pip install .            # 在仓库根目录；发布后是 pip install aitb
aitb doctor              # 看清：变量从哪来、预设从哪找、注册了哪些适配器
```

## 2 先看它红

```bash
aitb selftest            # 退出码 1：三条检查按设计失败
aitb selftest --allow-red  # 退出码 0：FAIL 全部来自负控
```

一个永远绿的台子没有意义。**先确认它会红，再信它的绿。**

## 3 写你自己的第一条检查

在作业目录建 `presets/myline.json`：

```json
{
  "name": "myline",
  "title": "我的工作线",
  "preset_version": 1,
  "checks": [
    {"id": "myline.report-exists", "type": "files",
     "paths": [{"path": "out/report.md", "min_size": 2000}]},
    {"id": "myline.tests-green", "type": "cmd",
     "cmd": "python -m unittest discover -s tests", "timeout": 600}
  ]
}
```

```bash
aitb validate myline     # 先校验，不跑
aitb run myline          # 跑；证据包在 .aitb/runs/<时间>_myline/
```

注意 `out/report.md` 是**相对路径**，基准是当前目录（项目根）。要指到别处，
在 `aitb.config.json` 里写变量，预设里用 `${MY_PROJECT}/out/report.md`。

## 4 接进 CI

```yaml
- run: pip install .
- run: aitb run myline --strict --format junit --out junit.xml
- run: aitb run myline --strict --format sarif --out out.sarif
- uses: github/codeql-action/upload-sarif@v3
  if: always()
  with: { sarif_file: out.sarif }
```

`--strict` 是门禁场合的必选项：它让 SKIP 和 BLOCKED 也进退出码。
不加它，一个因环境缺失而"没测到"的项会被当成没事。

## 5 三种状态别搞混

- **FAIL**：判到了，被测对象不合格。
- **BLOCKED**：**没判到**（超时、工具坏了、环境不可达）。它不等于失败，也绝不等于通过。
- **SKIP**：按配置主动跳过（如 `--offline`）。它同样不等于通过。

CI 面板里 FAIL 记 `failure`、BLOCKED 记 `error`、SKIP 记 `skipped` —— 三种分开统计，
否则算出来的"通过率"是假的。
