# 第一条检查：把你自己的一条命令接进来（约 5 分钟）

这个目录是 "外人能跑" 的最小样板：不写一行 Python，只写一个 JSON，就能让
AITB（Assurance Instrument Test Bench · 试真台）审你自己的工具，并留下可复跑的证据包。

```bash
pip install git+https://github.com/stevenzhao07/aitb.git   # 或者 pip install . （在本仓根目录）
cd examples/first-check
aitb doctor                 # 先看环境与预设目录是否就位
aitb run preset.json --allow-red   # 跑这一套；这里有一条按设计变红的负控
```

## 这里面四条检查各证明什么

| 检查 | 类型 | 判什么 |
| --- | --- | --- |
| `my-tool.runs-and-prints` | `cmd` | 命令能跑起来，且输出里有你要的口径字样 |
| `my-tool.writes-report` | `cmd` | 工具确实落了产物文件 |
| `my-tool.report-not-empty` | `files` | 产物在场、体积不低于门槛（防空壳） |
| `my-tool.broken-must-fail` | `cmd` + `expect_status: "FAIL"` | **闸本身是活的**：故意让它失败，它必须判 FAIL |

最后一条是关键：没有负控的判据会随时间烂掉而不自知（永远绿）。`expect_status: "FAIL"`
就是负控声明 —— 这条只有"按设计判 FAIL"才算正常；一旦它意外变绿，引擎记
`V107`（负控失效），`--allow-red` 也不会放行。

因此这个样板单独跑会 **rc=1**（那一条故意红），加 `--allow-red` 才是 **rc=0**：
"红是红的，但红得对"。CI 里两个方向都断言。

## 换成你的工具

1. 把 `my-tool.runs-and-prints` 的 `cmd` 改成你的真命令（例如 `["node","check.js"]`、
   `["${AITB_PYTHON}","-m","mytool","verify"]`）。**别写裸 `python`**：CI 的 macOS runner
   上常常没有这个名字，会把真通过判成假红。
2. `expect` 填你真正在意的那句话（口径、版本号、结论），不要填 "Done" 这种到处都有的词。
3. 产物检查把 `report.json` 换成你的真实产物路径与体积门槛。
4. 至少留一条负控。

## 每条插件的写权限边界

AITB 只读不写你的项目：所有命令默认在项目根（`AITB_ROOT`，缺省为当前目录）执行，
证据写到 `.aitb/runs/<时间戳>_<preset>/`。要换目录用 `params.cwd`，要注入变量用
`aitb.config.json` 里的 `vars`（缺变量会硬失败 `E006`，不会静默传下 `${X}` 给你的命令）。

跑完看两样东西：

- `.aitb/runs/*/report.md` —— 人读；
- `.aitb/runs/*/junit.xml` / `sarif.json` —— 机器读，直接喂 CI。

四种状态别折算：`PASS` / `FAIL` / `BLOCKED`（环境不可达或缺前置）/ `SKIP`（按设计不做）。
`BLOCKED` 永远不等于通过。
