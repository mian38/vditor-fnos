#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_frontend.py —— 前端静态一致性检查（防止大文件性能优化被回退）

本文件针对 1.3.0 引入的「纯文本模式 + 大文件性能优化」做静态守卫。
这些优化若被无意回退（例如有人改回 lineNumber:true，或新增了一处
vditor.getValue() 直调），功能上不一定立刻报错，但大文件会重新卡死——
属于典型的「静默失效」，故用静态断言固化。

校验内容：
1. 纯文本模式所需 DOM / 函数 / 样式齐备；
2. 三项高开销渲染特性保持关闭（代码块行号 / 自动空格 / 预览目录）；
3. 内容读写统一走 getContent() / setContent() 访问层——
   若残留新增的 vditor.getValue() / vditor.setValue() 直调，
   纯文本模式下会读到 Vditor 里的旧内容（表现为「编辑后保存丢失」）。

直接运行：python test_frontend.py
"""
import os, sys, io, re

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "vditor-fpk", "app", "index.html")

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


html = io.open(HTML, encoding="utf-8").read()

print("== 前端静态一致性检查 ==")

# ---------- 1) 纯文本模式所需元素齐备 ----------
for token, desc in [
    ('id="raw-editor"', "纯文本编辑区 <textarea id=\"raw-editor\">"),
    ('id="raw-mode-tip"', "纯文本模式提示条"),
    ('id="btn-raw-mode"', "顶栏纯文本/富文本切换按钮"),
    ("#raw-editor", "raw-editor 样式规则"),
    ("body.raw-mode", "raw-mode 下的显隐规则"),
]:
    check("存在 %s" % desc, token in html)

# ---------- 2) 关键函数与阈值 ----------
for token, desc in [
    ("function getContent(", "统一内容读取 getContent()"),
    ("function setContent(", "统一内容写入 setContent()"),
    ("function enterRawMode(", "进入纯文本模式 enterRawMode()"),
    ("function exitRawMode(", "退出纯文本模式 exitRawMode()"),
    ("function toggleRawMode(", "手动切换 toggleRawMode()"),
    ("function stripMarkdown(", "Markdown 语法剥离 stripMarkdown()"),
    # 1.5.0：阈值判定口径由「字符数」改为「UTF-8 字节数」——
    # 中文一字 3 字节，按字符判定会严重高估体积；且「1MB 文件 ≠ 100 万字符」。
    ("RAW_AUTO_BYTES", "自动降级阈值 RAW_AUTO_BYTES（字节口径）"),
    ("function byteLength(", "UTF-8 字节数换算 byteLength()"),
    ("COUNT_FAST_CHARS", "语法剥离上限 COUNT_FAST_CHARS"),
    ("COUNT_SAMPLE_CHARS", "采样统计阈值 COUNT_SAMPLE_CHARS"),
]:
    check("存在 %s" % desc, token in html)

# 1.5.0：旧的字符数口径必须已彻底移除，避免两套阈值并存导致判定打架
check("旧字符数阈值 RAW_AUTO_CHARS 已移除", "RAW_AUTO_CHARS" not in html)
check("旧字符数变量 docBaseLen 已移除", "docBaseLen" not in html)

# ---------- 3) 高开销渲染特性保持关闭 ----------
# 代码块行号：为「每行」生成 DOM，大文件上是主要放大项之一
m = re.search(r"hljs:\s*\{[^}]*lineNumber:\s*(true|false)", html)
check("hljs.lineNumber 保持关闭", bool(m) and m.group(1) == "false",
      m.group(0) if m else "未找到 hljs 配置")

# 自动空格：全文逐字符处理
m = re.search(r"markdown:\s*\{[^}]*autoSpace:\s*(true|false)", html)
check("markdown.autoSpace 保持关闭", bool(m) and m.group(1) == "false",
      m.group(0) if m else "未找到 markdown 配置")

# 预览目录：需遍历全文标题，已有 outline 替代
m = re.search(r"markdown:\s*\{[^}]*toc:\s*(true|false)", html)
check("markdown.toc 保持关闭", bool(m) and m.group(1) == "false",
      m.group(0) if m else "未找到 markdown 配置")

# ---------- 4) 内容读写必须走访问层（防静默失效） ----------
# ⚠️ 统计必须排除注释行：注释里会提到这些 API 名（例如说明旧实现时写的
#    "历史实现曾调用 vditor.getHTML()"），不做排除会误判为「多出一处直调」。
def without_comment_lines(text):
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        out.append(ln)
    return "\n".join(out)


code = without_comment_lines(html)

# 允许的直调：getContent/setContent/exitRawMode 内部各一处，
# 以及 exportDoc 内一处 getHTML（其前已有 rawMode 提前 return 保护）。
getvalue_hits = len(re.findall(r"vditor\.getValue\(\)", code))
setvalue_hits = len(re.findall(r"vditor\.setValue\(", code))
gethtml_hits = len(re.findall(r"vditor\.getHTML\(\)", code))

check("vditor.getValue() 仅出现在访问层(期望 1 处)", getvalue_hits == 1,
      "实际 %d 处" % getvalue_hits)
# 1.4.3：exitRawMode 原本有一处直调 vditor.setValue()，已改为经 setContent() 走访问层
# （直调会绕过 vditorReady 就绪判断，可能在 Vditor 未就绪/已销毁时抛错）。
# 故期望值由 2 降为 1——直调越少越安全。
check("vditor.setValue() 仅出现在访问层(期望 1 处，1.4.3 起 exitRawMode 已改走 setContent)", setvalue_hits == 1,
      "实际 %d 处" % setvalue_hits)
check("vditor.getHTML() 仅出现在导出(期望 1 处)", gethtml_hits == 1,
      "实际 %d 处" % gethtml_hits)

# 导出 HTML 前必须有 rawMode 保护，否则纯文本模式下会导出空白
export_ok = ("rawMode" in html.split("function exportDoc(")[1].split("function ")[0]
             if "function exportDoc(" in html else False)
check("exportDoc 含 rawMode 保护（避免导出空白）", export_ok)

# ---------- 5) 后端体积保护常量 ----------
srv = io.open(os.path.join(BASE, "vditor-fpk", "app", "server.py"), encoding="utf-8").read()
check("后端含 VERSION_SKIP_BYTES 体积保护", "VERSION_SKIP_BYTES" in srv)
# 注意：定义形如 `VERSION_SKIP_BYTES = 5 * 1024 * 1024`，不能只捕获首个数字
# （否则会把 5 当成字节数，算出 0.0 MB 而误判）。需取完整算术表达式求值。
m = re.search(r"VERSION_SKIP_BYTES\s*=\s*([0-9\s\*\+\-/]+)", srv)
if m:
    expr = m.group(1).strip()
    try:
        val = eval(expr, {"__builtins__": {}}, {})   # 仅数字与算术运算符
        mb = val / 1024 / 1024
        check("VERSION_SKIP_BYTES 阈值合理(1~50MB)", 1 <= mb <= 50,
              "%.1f MB（表达式 %s）" % (mb, expr))
    except Exception:
        check("VERSION_SKIP_BYTES 可解析", False, expr)
else:
    check("VERSION_SKIP_BYTES 有数值定义", False)

# ---------- 工具栏 overflow 裁剪防护（1.4.4 合并自 check_css_clip.py）----------
# 背景：Vditor 下拉面板 .vditor-panel 以 position:absolute 挂在工具栏按钮内部，
# 包含块位于 .vditor-toolbar 内；工具栏一旦成为裁剪容器（overflow 非 visible），
# 向下弹出的菜单就会被裁掉（表现为「点图标变蓝但无菜单」）。
# 故工具栏的 overflow 覆盖必须限定在窄屏 @media，桌面宽度须保持 Vditor 原生样式。
_CSS_KEY = re.compile(r"overflow-x\s*:\s*(auto|hidden|scroll)"
                      r"|overflow-y\s*:\s*(auto|hidden|scroll)"
                      r"|white-space\s*:\s*nowrap"
                      r"|flex-wrap\s*:\s*nowrap")


def _style_block(src):
    m = re.search(r"<style>(.*?)</style>", src, re.S)
    if not m:
        return ""
    # 剥离 CSS 注释，否则注释里的说明文字会被误判为真实规则（此为初版踩坑）
    return re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)


def _toolbar_overflow_outside_media(src):
    """返回「出现在 @media 之外的 .vditor-toolbar 裁剪性声明」。

    实现说明（两处易错点，勿简化）：
    1. 不能按行匹配——真实规则的选择器与声明分处两行
       （`.vditor-toolbar {` / `    overflow-x: auto !important;`），
       故逐字符扫描并按花括号配对提取声明体。
    2. 不能用正则 `([^{}]*)\\{([^{}]*)\\}` 提取——它无法匹配嵌套块，
       会把 @media 内的规则误判为裸规则（假失败）。
    3. 判定「是否在 @media 内」须比较**嵌套深度**而非「此前是否出现过 @media」，
       否则位于 @media 之后的裸规则会被误判为已受约束（假通过）。
    """
    css = _style_block(src)
    problems = []
    depth = 0
    media_depths = []      # 进入 @media 时的花括号深度
    sel_start = 0          # 当前选择器起始位置
    for i, ch in enumerate(css):
        if ch == "{":
            sel = css[sel_start:i]
            if sel.strip().startswith("@media"):
                media_depths.append(depth)
            elif "vditor-toolbar" in sel:
                # 本块声明体 = 当前 { 到**第一个** } 之间的内容。
                # 声明体内不含嵌套块，故取首个 } 即可（不能用配对扫描：
                # 一旦越过本块就会把后续无关规则的声明算进来，产生假失败）。
                end = css.find("}", i + 1)
                body = css[i + 1:end if end != -1 else len(css)]
                if _CSS_KEY.search(body) and not any(depth > m for m in media_depths):
                    problems.append(" ".join(sel.split())[:70])
            depth += 1
            sel_start = i + 1
        elif ch == "}":
            depth -= 1
            while media_depths and depth <= media_depths[-1]:
                media_depths.pop()
            sel_start = i + 1
    return problems


_clip_problems = _toolbar_overflow_outside_media(html)   # 注意传 html（内容）而非 HTML（路径）
check("工具栏裁剪性声明全部限定在窄屏 @media 内（防下拉菜单被裁剪）",
      not _clip_problems, _clip_problems[:3])

print("\nRESULT(frontend): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
