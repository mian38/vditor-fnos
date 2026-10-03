## 变更描述

<!-- 说明本次 PR 做了什么，以及为什么。关联 issue 请写 Closes #123 -->

## 变更类型

- [ ] 缺陷修复（`fix:`）
- [ ] 新功能（`feat:`）
- [ ] 文档（`docs:`）
- [ ] 重构（`refactor:`）
- [ ] 构建 / 工具（`chore:`）
- [ ] 代码审计整改（`audit:`）

## 是否改动 `vditor-fpk/app/`

- [ ] 否
- [ ] 是 —— 本项目**仅发布 fpk**，通用 Linux 部署直接以 `vditor-fpk/app/` 源码运行，无需同步其它目录

## 测试

- [ ] 已运行本轮改动对应的定向测试
- [ ] 若改动了 `vditor-fpk/app/`，已运行 `python test_pkg.py && python test_core.py`

测试命令与结果：

```
<!-- 例：python test_core.py → passed=26 failed=0 -->
```

- [ ] 若改动 `server.py` / `vd_util.py`，已确认未新增裸写`int(self.headers.get("Content-Length"))` 或 `self.rfile.read()`

> 请求体读取只允许走 `_content_length(handler)` 与 `_read_body(handler, limit)`，
> 裸写会在请求长度异常时抛未捕获异常并断开连接。详见 `CONTRIBUTING.md`。

## 是否需要同步文档

- [ ] 无需
- [ ] `CHANGELOG.md`（开发者版：技术细节 / 根因 / 包体）
- [ ] `CHANGELOG_USER.md`（用户版：只讲「发生了什么变化」）
- [ ] `README.md` / `CONTRIBUTING.md` / `SECURITY.md`
- [ ] `THIRD_PARTY_NOTICES.md`（引入了第三方代码或资源时**必须**）

## 检查清单

- [ ] 提交信息采用 `类型: 描述` 格式
- [ ] 未提交密码、哈希、Token、内网地址等敏感信息
- [ ] 未引入任何 pip 第三方依赖（本项目硬性约束为**零依赖**）
- [ ] 打包前已清理 `vditor-fpk/app/__pycache__`
