# CLAUDE.md —— 本项目 Agent 入口（指针 + 关键门禁）

你正在协作开发 **Vditor for fnOS**（`com.mian38.vditor`）。完整、具约束力的约定见 [`AGENTS.md`](AGENTS.md)，**开始改代码前必须通读**。

下面三条是最高优先级的硬门禁，漏掉任何一条都会损害项目信誉：

1. **人在环发版门禁**：实机（fnOS）测试只能由人类（mian38）手动完成。你构建 / 交付的每一个 fpk 一律是
   **测试版 · 未发布**；**你绝不自行创建 GitHub Release、绝不打 release tag、绝不对外宣布发布**。
   只有人类显式说「发布 vX.Y.Z」你才可发布。
2. **版本号规则（x.y.z）**：用户可见功能范围扩大→升 y（z 归零）；修 bug / 细节优化→升 z；架构不兼容→升 x；纯文档不改版本。
3. **测试门禁**：交付任何 fpk 前必须 `rm -rf vditor-fpk/app/__pycache__ && python tests/run_all.py --all` 且 **0 失败**。

技术约束：零第三方依赖；新增 `.py` 加 SPDX 头；可变状态留 `server.py`、纯函数留 `vd_util.py`；只发 fpk、不维护独立部署目录；`releases/` 的 `.fpk` 不删。

不确定时优先问人类，不要猜。详见 `AGENTS.md` / `CONTRIBUTING.md` / `.workbuddy/memory/MEMORY.md`。
