#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4.0.14：版本升级（manifest + 两处 server.py + 测试断言），并写入 changelog。

沿用既有经验：
- server.py 一律走「读-替换-写 + 断言计数」，不用 Edit（历史上曾报成功但未实改）。
- manifest 源码格式为 version=4.0.13 / changelog=4.0.13：...（等号两侧无空格、changelog 单行、
  且不带头尾三引号），打包后 fnpack 才会重新对齐并补上三引号，故按源码格式精确匹配。
- changelog 各版本条目直接拼接在同一行，不可插换行（多行会破坏 manifest 逐行 key=value 解析）。
- sub_once 先判「已是目标值」再计数断言，保证可重复执行。
"""
import io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OLD, NEW = "4.0.13", "4.0.14"

CHANGE = (
    "4.0.14：前端整体视觉与文案治理（功能与接口均不变）。"
    "视觉：统一为浅色风格并与 Vditor 官方浅色主题对齐——建立全站设计变量（字号 / 色板 / 圆角 / 阴影），"
    "并把同一套色值同步给 Vditor 自身的 CSS 变量，编辑器与外围 UI 融为一体；顶栏由深色改为浅色、"
    "与 Vditor 工具栏同系；统一全部按钮（主按钮 / 次级描边按钮 / 危险按钮 / 行内小按钮）、"
    "输入框、字段标签与开关控件的尺寸、圆角、间距与聚焦态，设置面板各区块与控件风格拉齐；"
    "清理了多套不统一的红 / 灰 / 圆角取值与 JS 中硬编码的行内颜色。"
    "文案：中文引号统一「」、中文括号统一（）、中英文之间补齐空格、代码统一排版，"
    "并修正欢迎语中与实际按钮名不符的「保存到 NAS」（v4.0.7 起按钮已改名为「保存」）。"
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

print("\nv4.0.14 版本升级完成")
sys.exit(0)
