#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""静态校验：.vditor-toolbar 的 overflow 规则是否只存在于窄屏 @media 内。

背景：Vditor 下拉面板 .vditor-panel 以 position:absolute 挂在 position:relative 的工具栏按钮内部，
其包含块位于 .vditor-toolbar 之内，因此工具栏一旦成为裁剪容器（overflow 非 visible），
向下弹出的菜单就会被裁掉（点击图标变蓝但无菜单）。
故工具栏的 overflow 覆盖必须限定在窄屏 @media，桌面宽度须保持 Vditor 原生样式。
"""
import io, os, re, sys

# 可直接传入路径校验打包后的产物（先解包 app.tgz 得到 app/index.html）：
#   python3 check_css_clip.py /tmp/x/appx/index.html
DEFAULT_TARGETS = (
    "vditor-fpk/app/index.html",
)
TARGETS = tuple(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TARGETS
# 需要被约束的关键词：工具栏上的 overflow 声明或 flex-wrap/nowrap 布局覆盖
KEY = re.compile(r"overflow-x\s*:\s*auto|overflow-y\s*:\s*hidden|white-space\s*:\s*nowrap\s*!important|flex-wrap\s*:\s*nowrap")


def style_block(src):
    m = re.search(r"<style>(.*?)</style>", src, re.S)
    if not m:
        return ""
    # 剥离 CSS 注释，避免把注释里的说明文字误判为真实规则
    return re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)


def scan(path):
    src = io.open(path, encoding="utf-8").read()
    css = style_block(src)
    depth = 0            # 当前花括号深度
    media_stack = []     # 记录每层 @media 的条件
    problems, findings = [], []
    lines = css.split("\n")
    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        mopen = re.match(r"@media([^{]*)\{", line)
        if mopen:
            media_stack.append((depth, mopen.group(1).strip()))
        if KEY.search(line) and "vditor" not in line.lower() and "toolbar" not in line.lower():
            pass  # 非工具栏相关的 overflow（如 #topbar）不关心
        if "vditor-toolbar" in line or (KEY.search(line) and _within_toolbar_rule(lines, i - 1)):
            inside_media = depth > 0 and media_stack
            cond = media_stack[-1][1] if media_stack else ""
            findings.append((i, line[:70], inside_media, cond))
            if KEY.search(line) and not inside_media:
                problems.append((i, line[:80]))
        depth += line.count("{") - line.count("}")
    return problems, findings


def _within_toolbar_rule(lines, idx):
    """向上回溯到最近的 '{'，判断选择器是否属于 .vditor-toolbar。"""
    buf = ""
    for j in range(idx, max(-1, idx - 6), -1):
        buf = lines[j].strip() + buf
        if "{" in buf:
            return "vditor-toolbar" in buf
    return False


ok = True
for t in TARGETS:
    if not os.path.isfile(t):
        print("SKIP %s（不存在）" % t)
        continue
    problems, findings = scan(t)
    print("=== %s ===" % t)
    for i, line, inside, cond in findings:
        print("  行%-4d %-72s 在@media内=%s %s" % (i, line, inside, ("<%s>" % cond) if cond else ""))
    if problems:
        ok = False
        print("  ✗ 发现未受 @media 约束的工具栏裁剪规则（桌面宽度会挡住下拉菜单）：")
        for i, line in problems:
            print("    行%d %s" % (i, line))
    else:
        print("  ✓ 无未受约束的工具栏 overflow 规则")
print()
print("RESULT:", "OK —— 桌面宽度不会裁剪 Vditor 下拉面板" if ok else "FAIL")
sys.exit(0 if ok else 1)
