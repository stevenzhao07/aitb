# Reporting a vulnerability

请**不要**开公开 issue 描述漏洞细节。

- 私下报告：`security@<项目域名>`（或 GitHub Security Advisory 的 "Report a vulnerability"）。
- 我们会 **14 天内回执**、**60 天内**给公开漏洞一个处置（修复或明确不修 + 理由）。
- 版本支持口径：只支持最新 minor。

## 报告里请附

1. 受影响的版本（`aitb version` 输出）与操作系统、Python 版本；
2. 最小复现（一个 preset JSON + 一条命令最好）；
3. 影响：是**引擎误判**（该红的没红 / 不该红的红了），还是**执行面**（命令注入、路径穿越、证据包被篡改）。

## 本项目特别关注的一类漏洞

**闸失明**（silent pass）：本该报 FAIL 的检查被判成 PASS。这类问题优先级最高，
因为整套台子的价值就是"它不会假装通过"。收到此类报告按 7 天处理。
