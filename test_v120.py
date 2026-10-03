# -*- coding: utf-8 -*-
"""1.2.0 专项测试：快捷键按钮与对话框。

覆盖本轮唯一改动——把「关于与帮助」里的快捷键表格改为与「使用指南」并列的按钮 + 弹窗。
不跑全量回归（见项目约定：默认只做本轮改动的专项测试）。

分段：
  A. 入口并列性        —— 快捷键按钮与使用指南按钮同容器、同样式类型
  B. 对话框结构        —— 复用 word-help 组件（modal-mask / modal-card / set-head / close / help-body）
  C. 条目迁移完整性    —— 13 组快捷键逐条保留，无删减
  D. 三种关闭方式      —— 关闭按钮 / ESC 栈 / 点击遮罩
  E. 样式与窄屏适配    —— table-layout、三列宽、极窄屏隐藏分类列
  F. 样式同步与防回归  —— apply_style_v414 MUST 断言已含新样式
  G. 结构配平          —— 标签配平、set-sub 合并、样式源唯一性
  H. 派生副本一致性    —— vditor-nas 已同步
  I. 版本号            —— 全项目版本号一致为 1.2.0
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FPK = os.path.join(HERE, "vditor-fpk")
APP = os.path.join(FPK, "app")
CSS = os.path.join(HERE, "ui_style_v414.css")

PASSED = 0
FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("  OK   %s" % name)
    else:
        FAILED += 1
        print("  FAIL %s   %s" % (name, extra))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


html = read(os.path.join(APP, "index.html"))
css = read(CSS)
srv = read(os.path.join(APP, "server.py"))
manifest = read(os.path.join(FPK, "manifest"))
apply_script = read(os.path.join(HERE, "apply_style_v414"))

# 弹窗区块切片（仅取 #kb-help-mask 内部，避免统计到设置页或其它弹窗）
_m = re.search(r'<div id="kb-help-mask".*?\n    </div>\n', html, re.S)
kb_block = _m.group(0) if _m else ""

print("\n=== A. 入口并列性 ===")
check("A1 存在 #btn-kb-help 按钮", 'id="btn-kb-help"' in html)
# 提取帮助与快捷键子区块
_sub = re.search(r'<div class="set-sub">\s*<h4>帮助与快捷键</h4>.*?</div>\s*</div>', html, re.S)
sub_block = _sub.group(0) if _sub else ""
check("A2 「帮助与快捷键」子区块存在", bool(sub_block), sub_block[:120])
check("A3 使用指南按钮仍在此区块内", 'id="btn-word-help"' in sub_block)
check("A4 快捷键按钮与此区块内", 'id="btn-kb-help"' in sub_block)
check("A5 两按钮同容器 .frow（并列，非上下堆叠）",
      re.search(r'<div class="frow">\s*<button id="btn-word-help".*?\n\s*<button id="btn-kb-help".*?</div>', sub_block, re.S) is not None,
      sub_block[:200])
check("A6 两按钮顺序：使用指南在前、快捷键在后",
      sub_block.find('btn-word-help') < sub_block.find('btn-kb-help') and sub_block.find('btn-word-help') != -1)
# 视觉样式：同一套 .action 类（同容器同间距由 .frow 的 gap 提供）
_btns = re.findall(r'<button id="btn-(?:word-help|kb-help)"[^>]*>', sub_block)
check("A7 两个入口按钮均带 action 样式类（视觉一致）",
      len(_btns) == 2 and all('class="action"' in b or 'class="ghost action"' in b for b in _btns), str(_btns))
check("A8 快捷键按钮有 title 提示", 'id="btn-kb-help" class="ghost action" title="' in html)
check("A9 旧的两个 set-sub 已合并（原「帮助（使用指南）」标题不再存在）",
      "<h4>帮助（使用指南）</h4>" not in html)
_tbl_pos = html.find('<table class="kb-list"')
check("A10 设置页内不再有快捷键表格（表格只存在于弹窗内）",
      html.count('<table class="kb-list"') == 1 and _tbl_pos > html.find('id="kb-help-mask"') > 0,
      "表格位置 %d / kb-help-mask 位置 %d" % (_tbl_pos, html.find('id="kb-help-mask"')))

print("\n=== B. 对话框结构（复用使用指南组件）===")
check("B1 #kb-help-mask 弹窗存在", 'id="kb-help-mask"' in html)
check("B2 使用 modal-mask 遮罩类", 'id="kb-help-mask" class="modal-mask"' in html)
check("B3 使用 modal-card 卡片类", 'id="kb-help-card" class="modal-card"' in html)
check("B4 卡片宽度与使用指南一致（600px）",
      re.search(r'id="kb-help-card" class="modal-card" style="width:600px;"', html) is not None)
check("B5 标题栏用 set-head + h2", re.search(r'id="kb-help-card".*?<div class="set-head">\s*<h2>快捷键</h2>', html, re.S) is not None)
check("B6 关闭按钮 class=close 且 id=kb-help-close",
      re.search(r'<button class="close" id="kb-help-close">×</button>', html) is not None)
check("B7 正文区复用 help-body", re.search(r'id="kb-help-card".*?<div class="help-body">', html, re.S) is not None)
check("B8 弹窗插在使用指南弹窗之后", html.find('id="word-help-mask"') < html.find('id="kb-help-mask"'))
check("B9 弹窗位于 toast 之前（DOM 顺序合理）", html.find('id="kb-help-mask"') < html.find('id="toast"'))
check("B10 未引入新第三方依赖（弹窗内无 script src / link href）",
      not re.search(r'<script[^>]+src=', kb_block) and not re.search(r'<link[^>]+href=', kb_block))

print("\n=== C. 快捷键条目迁移完整性 ===")
rows = re.findall(r'<tr><td>(编辑器|本应用)</td><td>(.*?)</td><td>(.*?)</td></tr>', kb_block, re.S)
check("C1 共 13 组条目（编辑器 11 + 本应用 2）",
      len(rows) == 13 and sum(1 for r in rows if r[0] == "编辑器") == 11 and sum(1 for r in rows if r[0] == "本应用") == 2,
      "实际 %d 组：%s" % (len(rows), [r[0] for r in rows]))
check("C2 表头三列完整", re.search(r'<tr><th>分类</th><th>按键</th><th>作用</th></tr>', kb_block) is not None)
# 逐条核对（分类|按键 的精确组合，防前缀误判）
expect = [
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>S</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>Z</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>Shift</kbd>\+<kbd>Z</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>B</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>I</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>K</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>Alt</kbd>\+<kbd>1</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>Alt</kbd>\+<kbd>2</kbd>$"),
    ("编辑器", r"^<kbd>Ctrl</kbd>\+<kbd>Alt</kbd>\+<kbd>0</kbd>$"),
    ("编辑器", r"^<kbd>Tab</kbd>$"),
    ("编辑器", r"^<kbd>Enter</kbd>$"),
    ("本应用", r"^<kbd>Esc</kbd>$"),
    ("本应用", r"^<kbd>Ctrl</kbd>\+<kbd>Enter</kbd>$"),
]
miss = []
for i, (cat, pat) in enumerate(expect):
    if i >= len(rows) or rows[i][0] != cat or not re.match(pat, rows[i][1].strip()):
        miss.append("%d:%s/%s" % (i + 1, cat, pat))
check("C3 13 组按键序列与迁移前完全一致（顺序+内容）", not miss, "不符：%s" % miss)
# 关键说明文字不得丢失
for tag, txt in [
    ("C4 Ctrl+S 说明含「与「保存」按钮一致」", "与「保存」按钮一致"),
    ("C5 Tab 说明含「源码模式下缩进」", "源码模式下缩进"),
    ("C6 Enter 说明含「列表模式下新建同级列表项」", "列表模式下新建同级列表项"),
    ("C7 Esc 说明含全部弹窗名", "关闭当前打开的弹窗"),
    ("C8 Ctrl+Enter 说明含「在编辑器内不生效」", "在编辑器内不生效"),
    ("C9 macOS 提示段落保留", "macOS 上请将"),
    ("C10 焦点前提说明保留", "编辑器或本页面获得焦点"),
]:
    check(tag, txt in kb_block)

print("\n=== D. 三种关闭方式 ===")
check("D1 绑定打开函数 openKbHelp", "function openKbHelp()" in html)
check("D2 绑定关闭函数 closeKbHelp", "function closeKbHelp()" in html)
check("D3 按钮绑定打开", "document.getElementById('btn-kb-help').addEventListener('click', openKbHelp)" in html)
check("D4 关闭按钮绑定关闭", "document.getElementById('kb-help-close').addEventListener('click', closeKbHelp)" in html)
check("D5 遮罩点击绑定", "document.getElementById('kb-help-mask').addEventListener('click'" in html)
check("D6 遮罩点击仅在 target===自身时关闭（不误关卡片内部）", "if (e.target === this) closeKbHelp();" in html)
check("D7 ESC 栈含 kb-help-mask", "{ mask: 'kb-help-mask'," in html)
# ESC 栈顺序：应在 word-help-mask 之后（与 DOM 打开顺序一致，先关最上层）
_esc = re.search(r"const layers = \[(.*?)\];", html, re.S).group(1)
check("D8 ESC 栈中 kb-help-mask 位于 word-help-mask 之后（层序正确）",
      _esc.find("kb-help-mask") > _esc.find("word-help-mask") and _esc.find("kb-help-mask") != -1)
check("D9 ESC 栈共 6 层（新增后）", _esc.count("{ mask:") == 6, "实际 %d" % _esc.count("{ mask:"))
check("D10 快捷键表内 Esc 说明与实现一致（含「快捷键」弹窗名）", "使用指南 / 快捷键 / 确认框" in kb_block)
check("D11 初始状态为隐藏（modal-mask 默认 display:none）",
      re.search(r"\.modal-mask \{[^}]*display: none;", css, re.S) is not None)

print("\n=== E. 样式与窄屏适配 ===")
check("E1 .kb-list 使用 table-layout: fixed",
      re.search(r"\.kb-list \{[^}]*table-layout: fixed;", css, re.S) is not None)
check("E2 三列宽度约束齐全", all(
    ".kb-list th:nth-child(%d)" % i in css for i in (1, 2, 3)))
check("E3 作用列允许长词折行（不横向溢出）",
      re.search(r"\.kb-list th:nth-child\(3\), \.kb-list td:nth-child\(3\) \{[^}]*word-break: break-word;[^}]*overflow-wrap: anywhere;", css, re.S) is not None)
check("E4 按键列不换行且可横向滚动（长组合键不撑破）",
      re.search(r"\.kb-list td:nth-child\(2\) \{[^}]*white-space: nowrap;[^}]*overflow-x: auto;", css, re.S) is not None)
check("E5 ≤520px 隐藏分类列", "#kb-help-mask .kb-list td:nth-child(1) { display: none; }" in css)
check("E6 ≤520px 按键列收窄至 116px", "width: 116px;" in css)
check("E7 弹窗内提示段落有独立样式", "#kb-help-mask .help-body .sub" in css)
check("E8 kbd 样式仍在（保留）", ".kb-list kbd {" in css)
check("E9 .frow 提供按钮间距（gap: 8px）", re.search(r"\.frow \{ display: flex; gap: 8px;", css) is not None)
check("E10 弹窗受 max-width: 92vw 约束（窄屏不出界）", "max-width: 92vw" in css)
check("E11 help-body 有 max-height + overflow（长表格可滚动）", re.search(r"\.help-body \{[^}]*max-height: 70vh;[^}]*overflow: auto;", css) is not None)
check("E12 暗色模式弹窗背景已覆盖（沿用 .modal-card 规则）", 'html[data-theme="dark"] .modal-card button.ghost' in css)

print("\n=== F. 样式同步与防回归 ===")
check("F1 index.html 内联 style 已含 table-layout: fixed", "table-layout: fixed;" in html)
check("F2 index.html 内联 style 已含极窄屏规则", "#kb-help-mask .kb-list td:nth-child(1)" in html)
check("F3 index.html 内联 style 已含弹窗提示段落样式", "#kb-help-mask .help-body .sub" in html)
for token, desc in [
    ("table-layout: fixed; }", "MUST 断言：固定列宽"),
    ("#kb-help-mask .kb-list th:nth-child(1)", "MUST 断言：极窄屏隐藏分类列"),
    ("#kb-help-mask .help-body .sub", "MUST 断言：弹窗提示段落"),
]:
    check("F4 apply_style_v414 含「%s」" % desc, token in apply_script)
check("F5 样式源唯一（kb-list 规则只定义在 ui_style_v414.css）",
      css.count(".kb-list {") == 1)

print("\n=== G. 结构配平 ===")
for tag in ["div", "table", "tbody", "thead", "tr", "td", "th", "button", "section", "p", "dl", "span", "style", "script"]:
    o = len(re.findall(r"<%s[\s>]" % tag, html))
    c = html.count("</%s>" % tag)
    check("G-%s 标签配平（%d/%d）" % (tag, o, c), o == c)
check("G2 无 console/debugger 残留", not re.search(r"\bconsole\.(log|debug)\b|\bdebugger\b", html))
check("G3 使用指南正文已更新描述（提及并列按钮）", "与使用指南并列的「快捷键」按钮" in html)
check("G4 弹窗内不含内联 style.display（由 JS 控制，避免与初始隐藏冲突）",
      'style="display:' not in kb_block)

print("\n=== H. 派生副本一致性 ===")
nas_index_p = os.path.join(HERE, "vditor-nas", "index.html")
if os.path.exists(nas_index_p):
    nas_index = read(nas_index_p)
    check("H1 vditor-nas/index.html 已同步快捷键按钮", 'id="btn-kb-help"' in nas_index)
    check("H2 vditor-nas/index.html 已同步弹窗", 'id="kb-help-mask"' in nas_index)
    check("H3 vditor-nas/index.html 已同步 table-layout", "table-layout: fixed;" in nas_index)
    check("H4 vditor-nas/index.html 已同步 ESC 栈", "{ mask: 'kb-help-mask'," in nas_index)
else:
    print("  SKIP vditor-nas/ 不存在（尚未运行 make_nas.py）")
nas_server_p = os.path.join(HERE, "vditor-nas", "server.py")
if os.path.exists(nas_server_p):
    # NAS 通用版按项目约定不随 fpk 同步升版（只在明确要求时更新），
    # 因此这里只校验「内部自洽」，不要求与 fpk 版本相同。
    _nas_v = re.search(r'APP_VERSION\s*=\s*"([0-9.]+)"', read(nas_server_p))
    check("H5 vditor-nas/server.py 版本号可解析且为正式版号",
          _nas_v is not None and _nas_v.group(1).count(".") == 2,
          _nas_v.group(1) if _nas_v else "未找到")

print("\n=== I. 版本号 ===")
# 版本号断言写成「三方一致 + 不低于 1.2.0」而非硬编码具体版本——
# 升版是正常操作，每轮都硬编码会让这些断言在每次升版后误报为失败。
_mf = re.search(r"(?m)^version\s*=\s*([0-9.]+)\s*$", manifest)
_mf = _mf.group(1) if _mf else "?"
_sv = re.search(r'APP_VERSION\s*=\s*"([0-9.]+)"', srv)
_sv = _sv.group(1) if _sv else "?"


def _vt(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0, 0, 0)


check("I1 manifest 与 server.py 的 APP_VERSION 一致（当前 %s）" % _mf,
      _mf == _sv and _mf != "?", "manifest=%s server=%s" % (_mf, _sv))
check("I2 版本号不低于 1.2.0（历史基线不回退）", _vt(_mf) >= (1, 2, 0), _mf)
check("I3 manifest changelog 以当前版本号开头",
      re.search(r"(?m)^changelog=%s：" % re.escape(_mf), manifest) is not None)
for f in ["CHANGELOG.md", "CHANGELOG_USER.md"]:
    c = read(os.path.join(HERE, f))
    check("I4 %s 含 ## %s 条目" % (f, _mf), re.search(r"(?m)^## %s" % re.escape(_mf), c) is not None)
    check("I5 %s 头部当前版本为 %s" % (f, _mf),
          ("**当前版本**：**%s**" % _mf) in c)
check("I6 归档版本已统一为 1.1.4beta（版本标识中无 1.2.0beta 残留）",
      not any(re.search(r"(^|[^\w`])(##\s*|v|version=)1\.2\.0beta", read(os.path.join(HERE, f)), re.M)
              for f in ["CHANGELOG.md", "CHANGELOG_USER.md", "ARCHIVE.md", "SECURITY.md"]),
      "仍有把 1.2.0beta 当版本标识的用法")

print("\n" + "=" * 60)
if FAILED == 0:
    print("RESULT(v1.2.0): passed=%d failed=0  —— 全部通过" % PASSED)
else:
    print("RESULT(v1.2.0): passed=%d failed=%d" % (PASSED, FAILED))
sys.exit(1 if FAILED else 0)
