#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4.0.15：版本升级（manifest + 两处 server.py + 测试断言），并写入 changelog。

沿用既有经验：
- server.py 一律走「读-替换-写 + 断言计数」，不用 Edit（历史上曾报成功但未实改）。
- manifest 源码格式为 version=4.0.14 / changelog=4.0.14：...（等号两侧无空格、changelog 单行、
  且不带头尾三引号），打包后 fnpack 才会重新对齐并补上三引号，故按源码格式精确匹配。
- changelog 各版本条目直接拼接在同一行，不可插换行（多行会破坏 manifest 逐行 key=value 解析）。
- sub_once 先判「已是目标值」再计数断言，保证可重复执行。
"""
import io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OLD, NEW = "4.0.14", "4.0.15"

CHANGE = (
    "4.0.15：六项前端 UI 修复与优化（功能与接口均不变）。"
    "① 修复移动端 Vditor 下拉菜单 / 弹出层仍不显示：窄屏工具栏是横向滚动容器，"
    "会裁掉挂在按钮内的 absolute 面板，而 CSS 无法让子元素逃出滚动容器，"
    "故窄屏下改用 JS 将面板设为 position:fixed 并按按钮位置定位（下方空间不足自动向上翻转），"
    "窗口回到桌面宽度自动还原原生行为；② 修复登录页密码输入框左右边距不一致、比「进入」按钮窄"
    "（v4.0.14 重写样式时漏了登录输入框的整行宽度），已补齐使其与按钮等宽对称；"
    "③ 设置界面「分区显示名」与「绝对路径」改为两列栅格（路径列更宽），窄屏自动堆叠，"
    "并精简占位文字避免被截断；④ 设置面板内操作按钮（含「修改密码」与「维护」各按钮）"
    "统一间距（上 10px、右 8px），消除拥挤；⑤「网页标题」输入框改为整行宽度、左右间距一致；"
    "⑥ 新增暗黑模式：外观设置新增开关，存于浏览器本地、未手动设置时跟随系统深色偏好，"
    "切换时同步调用 vditor.setTheme 调整编辑器整体 / 内容 / 代码高亮主题，"
    "并把同一套暗色令牌同步给 Vditor 自身 CSS 变量，使其顶栏与页面整体配色一致。"
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

print("\nv4.0.15 版本升级完成")
sys.exit(0)
