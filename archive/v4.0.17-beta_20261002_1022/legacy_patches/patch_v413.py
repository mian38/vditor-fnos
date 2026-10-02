#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4.0.13：版本升级（manifest + 两处 server.py + 测试断言），并写入 changelog。

复用 v4.0.12 的经验：
- 涉及 server.py 一律走「读-替换-写 + 断言计数」，不用 Edit（历史上曾报成功但未实改）。
- manifest 源码格式为 version=4.0.12 / changelog=4.0.12：...（等号两侧无空格、changelog 单行、
  且不带头尾三引号），打包后 fnpack 才会重新对齐并补上三引号，故按源码格式精确匹配。
- changelog 各版本条目直接拼接在同一行，不可插换行（多行会破坏 manifest 逐行 key=value 解析）。
- sub_once 先判「已是目标值」再计数断言，保证可重复执行。
"""
import io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OLD, NEW = "4.0.12", "4.0.13"

CHANGE = (
    "4.0.13：修复 Vditor 顶栏「渲染模式 / 主题 / 导出」等下拉菜单点击图标变蓝却不弹出的问题。"
    "根因：v4.0.6 为移动端防换行引入的 .vditor-toolbar 横向滚动覆盖被无条件应用到所有宽度，"
    "使工具栏变成裁剪容器；而 Vditor 的下拉面板 .vditor-panel 以 position:absolute 挂在 "
    "position:relative 的工具栏按钮内部（包含块落在工具栏之内），向下弹出时即被裁掉。"
    "现将该组覆盖限定在窄屏 @media screen and (max-width:520px)（与 Vditor 自身移动端断点一致），"
    "桌面宽度恢复原生样式、下拉菜单正常弹出，窄屏仍保留横向滑动不换行。"
)


def sub_once(path, old, new, expect_note=""):
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    if new != old and new in src:
        print("SKIP %s（已是目标值）" % os.path.basename(path))
        return
    cnt = src.count(old)
    if cnt != 1:
        raise SystemExit("FAIL %s: 待替换串出现 %d 次（应为 1）%s" % (path, cnt, expect_note))
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(src.replace(old, new, 1))
    print("OK   %s: %s -> %s" % (os.path.basename(path), old, new))


for p in ("vditor-fpk/app/server.py", "vditor-nas/server.py"):
    sub_once(os.path.join(HERE, p), 'APP_VERSION = "%s"' % OLD, 'APP_VERSION = "%s"' % NEW)

mf = os.path.join(HERE, "vditor-fpk", "manifest")
sub_once(mf, "version=%s" % OLD, "version=%s" % NEW)
sub_once(mf, "changelog=%s：" % OLD, "changelog=%s%s：" % (CHANGE, OLD))

for t in ("test_v406.py", "test_v407.py"):
    tp = os.path.join(HERE, t)
    with io.open(tp, encoding="utf-8") as f:
        s = f.read()
    if OLD in s:
        with io.open(tp, "w", encoding="utf-8", newline="") as f:
            f.write(s.replace(OLD, NEW))
        print("OK   %s: 版本断言 -> %s" % (t, NEW))
    else:
        print("SKIP %s（无 %s 断言）" % (t, OLD))

print("\nv4.0.13 版本升级完成")
sys.exit(0)
