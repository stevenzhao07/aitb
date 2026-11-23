# 第三方适配器示例：把"自家工具"接成一条检查

本目录的包**不随 aitb 分发**，是一个最小可用的参考实现，用来证明
"别人扩展不需要 fork 引擎"。

## 文件

- `mytool_adapter/__init__.py` — 适配器实现，签名 `fn(spec, ctx) -> (status, code, why, evidence, ms)`
- `pyproject.toml` — 声明 entry point，装完 aitb 就能自动发现

## 用法

```bash
pip install ./examples/adapter-mytool
aitb doctor        # adapters 一行里应出现 mytool 字样
```

然后在任意 preset 里：

```json
{"id": "myline.mytool-clean", "type": "mytool", "target": "${MY_PROJECT}/out", "expect_level": "none"}
```

## 契约里最要紧的一条

**没判到，不许写成 PASS。** 超时、工具崩了、目录不存在 —— 这些是 `BLOCKED`，
不是"通过"，也不是"失败"。写错这一条，台子就变成了橡皮图章。
