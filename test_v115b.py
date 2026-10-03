#!/usr/bin/env python3
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""v1.1.5 二次整改专项测试：端口引导、选项卡切换、状态与日志折叠、UI 风格、
历史版本按钮迁移、快捷键规范。

本轮修复的问题（1.1.5 首发的回归）：
  1. 安装向导自定义端口不生效（桌面图标仍写死 9000、服务未按新端口重启）
  2. 设置选项卡点击不切换、所有设置项堆叠（根因：1.1.5 新增 CSS 未注入 index.html）
  3. 状态与日志区按钮过多、面板各自独立 display、不能互斥展开
  4. 新增样式与原界面不一致、日志长行会撑出横向滚动
  5. 「历史版本」按钮占用顶栏位置
  6. 快捷键表Ctrl+S 重复、Esc 未覆盖全部对话框

跑法： python test_v115b.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "vditor-fpk", "app")
HTML = os.path.join(APP, "index.html")
CSS = os.path.join(HERE, "ui_style_v414.css")
WIZARD = os.path.join(HERE, "vditor-fpk", "wizard", "install")
INSTALL_CB = os.path.join(HERE, "vditor-fpk", "cmd", "install_callback")
UPGRADE_CB = os.path.join(HERE, "vditor-fpk", "cmd", "upgrade_callback")
MAIN_SH = os.path.join(HERE, "vditor-fpk", "cmd", "main")
MANIFEST = os.path.join(HERE, "vditor-fpk", "manifest")
UI_CONFIG = os.path.join(APP, "ui", "config")

PASSED = 0
FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("  PASS %s" % name)
    else:
        FAILED += 1
        print("  FAIL %s %s" % (name, ("—— " + str(extra)) if extra else ""))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


html = read(HTML)
css = read(CSS)
wizard = read(WIZARD)
install_cb = read(INSTALL_CB)
upgrade_cb = read(UPGRADE_CB)
main_sh = read(MAIN_SH)
manifest = read(MANIFEST)
ui_config = read(UI_CONFIG)

print("\n=== A. 端口引导（自定义端口须真正生效）===")

# A1 ui/config 的默认端口必须与 server 默认值一致（此前硬编码 9000，永不更新）
ui_port = re.search(r'"port"\s*:\s*"(\d+)"', ui_config)
check("A1 ui/config 默认端口为 3838",
      ui_port is not None and ui_port.group(1) == "3838",
      ui_port.group(1) if ui_port else "未找到 port 字段")
check("A2 ui/config 中无 9000 残留", '"9000"' not in ui_config)

# A2 manifest service_port 与 ui/config 一致（桌面图标跳转依据）
svc = re.search(r'(?m)^service_port\s*=\s*(\d+)', manifest)
check("A3 manifest service_port=3838", svc is not None and svc.group(1) == "3838",
      svc.group(1) if svc else "未找到")

# A3 向导 initValue 与默认端口一致
init = re.search(r'"field"\s*:\s*"app_port".*?"initValue"\s*:\s*"(\d+)"', wizard, re.S)
check("A4 向导端口 initValue=3838", init is not None and init.group(1) == "3838",
      init.group(1) if init else "未找到")

# A4 install_callback 必须同步桌面图标端口，且**两处路径都尝试**
check("A5 install_callback 同步 ui/config 端口", 'ui/config' in install_cb)
check("A6 install_callback 兼容 app/ui/config 路径",
      'TRIM_APPDEST}/app/ui/config' in install_cb)
check("A7 install_callback 校验端口合法性",
      'grep -Eq' in install_cb and '65535' in install_cb)
# 关键修复：写盘后必须重启，否则服务仍监听旧端口
check("A8 install_callback 写盘后重启服务（关键修复）",
      'cmd/main" start' in install_cb and 'cmd/main" stop' in install_cb)
check("A9 install_callback 落盘端口到 PKGETC/port",
      re.search(r'echo\s+"\$PORT"\s*>\s*"\$\{TRIM_PKGETC\}/port"', install_cb) is not None)
check("A10 install_callback 有端口占用提示", 'ss -ltn' in install_cb)

# A5 upgrade_callback 同样两处路径
check("A11 upgrade_callback 兼容两处 ui 路径",
      'TRIM_APPDEST}/app/ui/config' in upgrade_cb and 'TRIM_APPDEST}/ui/config' in upgrade_cb)

# A6 cmd/main 端口占用时给出可执行提示
check("A12 cmd/main 端口占用有专门报错", 'ss -ltn' in main_sh and '已被其它进程占用' in main_sh)
check("A13 cmd/main 默认端口 3838", 'echo 3838' in main_sh)
check("A14 cmd/main 无 9000 残留", '9000' not in main_sh)

# A7 server.py 默认端口
srv = read(os.path.join(APP, "server.py"))
check("A15 server.py 默认端口 3838", '"PORT": "3838"' in srv)
check("A16 server.py 无 9000 残留", '9000' not in srv)

print("\n=== B. 设置选项卡（仅显示选中页）===")

# B1 内联 style 必须真的含 .set-page 规则（1.1.5 首发漏注入 → 全部堆叠）
check("B1 index.html 内联样式含 .set-page 默认隐藏",
      ".set-page { display: none; }" in html,
      "缺失将导致所有设置项堆叠显示")
check("B2 index.html 内联样式含 .set-page.on 显示",
      ".set-page.on { display: block; }" in html)
check("B3 index.html 内联样式含 .set-tabs 选中态", ".set-tabs button.on" in html)
# 源样式同样要有
check("B4 样式源含 .set-page 默认隐藏", ".set-page { display: none; }" in css)
check("B5 样式源含 .set-page.on 显示", ".set-page.on { display: block; }" in css)

# B2 七个顶级选项卡 + 三个子选项卡
tabs = re.findall(r'data-page="(pg-[a-z]+)"', html)
check("B6 顶级选项卡 7 个", len(tabs) == 7, tabs)
check("B7 首项为 pg-folders（默认选中「文件夹设置」）", tabs and tabs[0] == "pg-folders")
check("B8 含 pg-about 关于与帮助", "pg-about" in tabs)

# B3 JS：显式写 style.display，不单靠 CSS 类
check("B9 selectSetPage 显式写 style.display",
      re.search(r"p\.style\.display\s*=\s*on\s*\?\s*'block'\s*:\s*'none'", html) is not None)
check("B10 selectSetPage 已定义", "function selectSetPage(pageId)" in html)
check("B11 打开设置时重置到首个选项卡", "selectSetPage('pg-folders')" in html)
# 每个 pg-* 页都有对应容器
pages = re.findall(r'class="set-page[^"]*" id="(pg-[a-z]+)"', html)
check("B12 七个选项卡均有对应面板容器", sorted(pages) == sorted(tabs), (pages, tabs))
# 默认只有首个面板带 on
check("B13 默认仅首个面板带 on 类",
      len(re.findall(r'class="set-page on"', html)) == 1
      and 'class="set-page on" id="pg-folders"' in html)

print("\n=== C. 状态与日志（四按钮 + 互斥折叠）===")

# C1 四个按钮
for bid, label in [("btn-refresh-status", "应用状态"),
                   ("btn-view-app-log", "查看应用日志"),
                   ("btn-view-log", "查看登录日志"),
                   ("btn-refresh-current", "刷新")]:
    check("C1 存在按钮 %s（%s）" % (bid, label), ('id="%s"' % bid) in html)
check("C2 「应用状态」为主样式、其余为 ghost",
      html.count('class="action" id="btn-refresh-status"') == 1
      and html.count('class="ghost action" id="btn-view-app-log"') == 1
      and html.count('class="ghost action" id="btn-view-log"') == 1
      and html.count('class="ghost action" id="btn-refresh-current"') == 1)

# C2 data-logpanel 标记三个可展开面板（刷新按钮不标记）
panels_attr = re.findall(r'data-logpanel="(\w+)"', html)
check("C3 三个可展开面板标记", sorted(panels_attr) == ["applog", "loginlog", "status"], panels_attr)
check("C4 刷新按钮无 data-logpanel", 'id="btn-refresh-current"' in html
      and not re.search(r'id="btn-refresh-current"[^>]*data-logpanel', html))

# C3 三个折叠面板容器
for pid in ("status-panel", "app-log-panel", "login-log-panel"):
    check("C5 存在面板容器 %s" % pid, ('id="%s"' % pid) in html)

# C4 折叠逻辑
check("C6 定义 toggleLogPanel", "function toggleLogPanel(name)" in html)
check("C7 定义 closeLogPanels", "function closeLogPanels()" in html)
check("C8 再次点击收回（currentLogPanel === name 则关闭）",
      re.search(r"if\s*\(currentLogPanel\s*===\s*name\)\s*\{\s*closeLogPanels\(\);\s*return;", html) is not None)
check("C9 打开新面板前先收回旧的", re.search(r"closeLogPanels\(\);\s*//", html) is not None)
check("C10 刷新作用于当前展开面板", "function refreshCurrentPanel()" in html)
check("C11 刷新未展开时默认展开状态", "!currentLogPanel" in html)
check("C12 离开维护页时收回面板", "pageId !== 'pg-maint'" in html)
# 旧的直接绑定须已移除（否则会与折叠逻辑打架）
check("C13 旧的 btn-view-log 直接绑定已移除",
      "getElementById('btn-view-log').addEventListener" not in html)
check("C14 viewLog 不再自行 display（由面板容器控制）",
      re.search(r"function viewLog\(\)\s*\{\s*const box[^;]*;\s*box\.innerHTML", html) is not None)
check("C15 viewAppLog 不再自行 display",
      re.search(r"function viewAppLog\(\)\s*\{\s*const box[^;]*;\s*box\.innerHTML", html) is not None)

print("\n=== D. UI 风格统一（沿用登录日志 + 防溢出）===")

check("D1 样式源含 .log-box（沿用登录日志外观）", ".log-box {" in css)
check("D2 index.html 已注入 .log-box", ".log-box {" in html)
check("D3 日志正文换行防溢出（pre-wrap + break-all）",
      "white-space: pre-wrap" in css and "word-break: break-all" in css)
check("D4 日志面板限制最大高度并纵向滚动", "max-height" in css and "overflow-y: auto" in css)
check("D5 日志面板禁止横向溢出", "overflow-x: hidden" in css)
check("D6 深色模式适配 log-box", 'html[data-theme="dark"] .log-box' in css)
check("D7 状态/日志按钮选中态与选项卡同风格",
      ".set-pw button.action.on" in css and ".set-pw button.action.on" in html)
check("D8 快捷键表样式已注入", ".kb-list kbd" in html)
check("D9 状态键值表样式已注入", ".kv-list {" in html)
# 状态面板须用 log-panel 包一层（与登录日志同级观感）
check("D10 状态面板有 log-panel 包裹", 'class="log-panel" id="status-panel"' in html)
check("D11 登录日志用 log-box 包裹", 'class="log-box" id="log-box"' in html)

print("\n=== E. 历史版本按钮迁移 ===")

topbar = re.search(r'<div class="top-actions">(.*?)</div>', html, re.S)
topbar_html = topbar.group(1) if topbar else ""
check("E1 顶栏已无 btn-history", "btn-history" not in topbar_html)
check("E2 顶栏仍有 btn-doc-info", "btn-doc-info" in topbar_html)
info_card = re.search(r'id="doc-info-card".*?</div>\s*</div>', html, re.S)
info_html = info_card.group(0) if info_card else ""
check("E3 信息对话框内含 btn-history", 'id="btn-history"' in info_html)
check("E4 历史版本按钮紧邻删除文档按钮",
      re.search(r'id="btn-history".{0,200}id="doc-info-delete"', html, re.S) is not None)
check("E5 打开历史版本前先关闭信息对话框",
      re.search(r"getElementById\('btn-history'\)\.addEventListener\('click', function \(\) \{\s*closeDocInfo\(\);\s*openHistory\(\);", html) is not None)
check("E6 使用指南已更新为「信息 → 历史版本」",
      "「信息」按钮" in html and "历史版本" in html)

print("\n=== F. 快捷键规范 ===")

kb = re.search(r'<table class="kb-list">.*?</table>', html, re.S)
kb_html = kb.group(0) if kb else ""
check("F1 快捷键表存在", bool(kb_html))
check("F2 全部按键使用 <kbd> 包裹", kb_html.count("<kbd>") == kb_html.count("</kbd>")
      and kb_html.count("<kbd>") > 20, kb_html.count("<kbd>"))
rows = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", kb_html)
check("F3 快捷键行数 >= 12", len(rows) >= 12, len(rows))
# Ctrl+S 只应出现一次。
# 注意：不能用子串 'Ctrl</kbd>+<kbd>S' 匹配——「Ctrl+Shift+Z」也含此前缀（Ctrl + S…），
# 会把重做行误计为 Ctrl+S。必须确认其后紧跟 </td>，即该行按键列恰好是 Ctrl+S。
ctrl_s_rows = [r for r in rows
               if re.match(r"^<kbd>Ctrl</kbd>\+<kbd>S</kbd>$", r[1].strip())]
check("F4 Ctrl+S 仅列一次（已删重复）", len(ctrl_s_rows) == 1, len(ctrl_s_rows))
check("F4b Ctrl+Shift+Z（重做）不误判为 Ctrl+S",
      len([r for r in rows if "Shift" in r[1]]) == 1)
check("F5 Ctrl+S 标注为全局生效", "任意位置" in ctrl_s_rows[0][2] if ctrl_s_rows else False)
# Ctrl+Enter 场景说明
ctrl_e = [r for r in rows if "Ctrl</kbd>+<kbd>Enter" in r[1]]
check("F6 Ctrl+Enter 已列出", len(ctrl_e) == 1)
check("F7 Ctrl+Enter 说明适用场景（登录页）", "登录页" in ctrl_e[0][2] if ctrl_e else False)
check("F8 Ctrl+Enter 说明编辑器内不生效", "不生效" in ctrl_e[0][2] if ctrl_e else False)
# Esc 覆盖范围
esc_rows = [r for r in rows if "<kbd>Esc</kbd>" in r[1]]
check("F9 Esc 已列出", len(esc_rows) == 1)
check("F10 Esc 说明覆盖全部弹窗", "效果等同" in esc_rows[0][2] if esc_rows else False)
for kw in ("设置", "信息", "历史版本", "使用指南", "确认"):
    check("F11 Esc 说明含「%s」" % kw, kw in esc_rows[0][2] if esc_rows else False)
check("F12 含 macOS Cmd 提示", "macOS" in html and "Cmd" in html)

# Esc 实现须覆盖全部 5 个可关弹窗
esc_block = re.search(r"if\s*\(e\.key\s*===\s*'Escape'\)\s*\{(.*?)\n        \}", html, re.S)
esc_code = esc_block.group(1) if esc_block else ""
for m in ("confirm-mask", "doc-info-mask", "history-mask", "word-help-mask", "settings-mask"):
    check("F13 Esc 覆盖 %s" % m, m in esc_code)
check("F14 Esc 按栈序关闭最上层", "for (const L of layers)" in esc_code)
# 登录页 Enter / Ctrl+Enter
check("F15 登录框绑定 Enter", "getElementById('login-pw').addEventListener('keydown'" in html)
check("F16 确认框绑定 Enter", "getElementById('setup-pw2').addEventListener('keydown'" in html)
# Ctrl+S 全局拦截仍在
check("F17 Ctrl+S 全局拦截保留",
      "e.key === 's' || e.key === 'S'" in html and "saveToNas(false)" in html)

print("\n=== G. 标签配平与结构 ===")
for tag in ("div", "section", "dl", "table", "tbody", "thead", "button"):
    o = len(re.findall(r"<%s[ >]" % tag, html))
    c = len(re.findall(r"</%s>" % tag, html))
    check("G-%s 标签配平（%d/%d）" % (tag, o, c), o == c)

check("G8 无 console/debugger 残留",
      not re.search(r"\bconsole\.(log|debug)\b|\bdebugger\b", html))
check("G9 版本号未变（1.1.5）", 'APP_VERSION = "1.1.5"' in srv)
check("G10 manifest 版本号未变", re.search(r"(?m)^version\s*=\s*1\.1\.5", manifest) is not None)

print("\n=== H. 派生副本一致性 ===")
nas_index = read(os.path.join(HERE, "vditor-nas", "index.html"))
check("H1 vditor-nas/index.html 已同步选项卡样式", ".set-page { display: none; }" in nas_index)
check("H2 vditor-nas/index.html 已同步 log-box 样式", ".log-box {" in nas_index)
check("H3 vditor-nas/index.html 已同步四按钮", 'id="btn-refresh-current"' in nas_index)
nas_server = read(os.path.join(HERE, "vditor-nas", "server.py"))
check("H4 vditor-nas/server.py 版本一致", 'APP_VERSION = "1.1.5"' in nas_server)
nas_cfg = read(os.path.join(HERE, "vditor-nas", "config.env"))
check("H5 config.env 默认端口 3838", re.search(r"(?m)^PORT=3838\s*$", nas_cfg) is not None)

print("\n" + "=" * 56)
if FAILED == 0:
    print("RESULT(v1.1.5b): passed=%d failed=0  —— 全部通过" % PASSED)
else:
    print("RESULT(v1.1.5b): passed=%d failed=%d" % (PASSED, FAILED))
sys.exit(1 if FAILED else 0)
