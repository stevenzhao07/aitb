# 维护手册（维护者向）

## 三入口等价

`aitb`（console script）/ `python -m aitb` / 直接调 `aitb.cli:main(argv)` —— 三者必须行为一致，
测试里已覆盖前两个；改 CLI 时顺手验第三个。

## 一、改引擎的固定动作

1. `python -m unittest discover -s tests -v` 全绿；
2. `aitb doctrine` 五条仍成立（T1 尤其：弄坏必须能红）；
3. `aitb selftest` 必须仍产生 FAIL；
4. 新增行为 → 新增测试，否则视为没这个行为；
5. 动判定语义或退出码语义 → 升大版本，并在 `CHANGELOG.md` 里明写"旧结论需重评"。

## 二、加一条工作线的固定动作

1. 预设放**私有目录**，用 `AITB_PRESETS` 指过去；仓库 `presets/` 只放通用可公开的；
2. 预设里不许出现绝对路径，跑 `aitb validate <name>`；
3. 首次接入先跑 `--strict`，看 SKIP/BLOCKED 有多少——那些是"没测到"，不是"通过"；
4. 把边界写进 `notes`；把"这线为什么存在"写进提交信息。

## 三、退役一条线

不要直接删。先把 `notes` 写清替代方案与最后通过日期，保留至少一个大版本之后再删。
理由：别人可能已经拿它做过门禁。

## 四、绝对不能做的事

- ❌ 把含个人机器路径的预设提交进公开仓（`.gitignore` 只挡住了配置，挡不住手滑）；
- ❌ 让任何检查在"没判到"时返回 PASS（这是闸失明，SECURITY.md 里按 7 天处理）；
- ❌ 在没有负控的情况下宣称"这套检查有效"——无法变红的判据无法证伪；
- ❌ 宣称"certified / 已认证"。没有背书机构，这个词一律不写。

## 五、发布清单（每次打 tag 前）

- [ ] 版本号与 `CHANGELOG.md` 一致；
- [ ] `python -m build` 能出 wheel 与 sdist；
- [ ] 在**干净虚拟环境**里 `pip install dist/*.whl` 后 `aitb doctor` / `selftest` / `doctrine` 三条都对；
- [ ] Windows 与 Linux 各一遍（`pyver` 适配器行为差异最大）；
- [ ] 记录 `SHA256SUMS`（签名发布尚未做，见 CHANGELOG 的 Known limits）。

## 六、已知脆弱点（诚实清单）

- `pyver` 适配器靠错误串猜"解释器缺席还是坏死"，不同发行版措辞会变 —— 新增措辞要进 `_ABSENT_MARKS`；
- 证据包 `manifest.json` 只保证**本次运行内自洽**，不保证防篡改（没有签名）；
- `latest` 指针走符号链接，Windows 上可能退化成 `latest.txt`，两者都要读；
- 多进程并发跑同一预设会撞同一时间戳目录名（秒级），CI 里串行跑即可。
