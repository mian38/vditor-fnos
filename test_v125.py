#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_v125.py —— 1.2.5 专项测试

本轮改动：
  ① 公网访问引导文案补充（安装向导 / manifest / 安全设置 / 使用指南 / README / SECURITY.md）
     + 修正 SECURITY.md 默认值写反；
  ② 信息对话框三个按钮统一白底 + 窄屏可左右滑动；
  ③ 二次确认统一为自定义 showConfirm（设置安全开关不再用原生 confirm）；
  ④ 信息对话框排版改为 kv-list 键值列表；
  ⑤ 新建文档默认文件名 未命名文档.md → 未命名文档。

直接运行：python test_v125.py
（版本号动态读取，不写死）
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FPK = os.path.join(HERE, "vditor-fpk")
HTML = os.path.join(FPK, "app", "index.html")
CSS = os.path.join(HERE, "ui_style_v414.css")
WIZ = os.path.join(FPK, "wizard", "install")
MF = os.path.join(FPK, "manifest")
SRV = os.path.join(FPK, "app", "server.py")
SEC = os.path.join(HERE, "SECURITY.md")
README = os.path.join(HERE, "README.md")

PASS, FAIL = [], []


def ck(cond, name, extra=""):
    (PASS if cond else FAIL).append(name)
    print("  %-4s %s%s" % ("OK" if cond else "FAIL", name, ("  -> " + str(extra)) if extra else ""))


def section(t):
    print("\n=== %s ===" % t)


html = io.open(HTML, encoding="utf-8").read()
css = io.open(CSS, encoding="utf-8").read()
wiz = io.open(WIZ, encoding="utf-8").read()
mf = io.open(MF, encoding="utf-8").read()
srv = io.open(SRV, encoding="utf-8").read()
sec = io.open(SEC, encoding="utf-8").read()
readme = io.open(README, encoding="utf-8").read()

# ---------------------------------------------------------------- A. 版本一致性（动态）
section("A. 版本一致性")
mver = ""
for ln in mf.split("\n"):
    if ln.startswith("version="):
        mver = ln.split("=", 1)[1].strip()
        break
sm = re.search(r'APP_VERSION = "([^"]+)"', srv)
sver = sm.group(1) if sm else ""
ck(bool(mver), "A1 manifest version 可解析", mver)
ck(sver == mver, "A2 manifest 与 server.py 版本一致", (sver, mver))
ck(re.match(r"^\d+\.\d+\.\d+$", mver) and tuple(map(int, mver.split('.'))) >= (1, 2, 5),
   "A3 版本不低于 1.2.5", mver)
nas_srv = os.path.join(HERE, "vditor-nas", "server.py")
if os.path.isfile(nas_srv):
    nsm = re.search(r'APP_VERSION = "([^"]+)"', io.open(nas_srv, encoding="utf-8").read())
    nsver = nsm.group(1) if nsm else ""
    ck(re.match(r"^\d+\.\d+\.\d+$", nsver), "A4 NAS 版本为合法正式版号（按约定不同步升版）", nsver)

# ------------------------------------------------------ B. 公网访问引导文案
section("B. 公网访问引导文案")
KW = ["反向代理", "内网穿透", "纯 HTTP", "公网"]


def miss(text, kws):
    return [k for k in kws if k not in text]


ck(not miss(wiz, KW), "B1 安装向导含公网访问引导", miss(wiz, KW))
ck(not miss(mf, KW), "B2 manifest 访问方式段含引导", miss(mf, KW))
ck(not miss(html, KW), "B3 应用内（安全/使用指南）含引导", miss(html, KW))
ck("暂不支持" in html and "3838" in html, "B4 应用内明确「暂不支持公网直连 3838」")
ck(not miss(sec, KW), "B5 SECURITY.md 含引导", miss(sec, KW))
ck(not miss(readme, KW), "B6 README 含引导", miss(readme, KW))

# ------------------------------------------------------ C. SECURITY.md 默认值修正
section("C. SECURITY.md 默认值修正")
for name in ("trust_proxy", "secure_cookie"):
    m = re.search(r'\| `%s` \| ([^|]+)' % re.escape(name), sec)
    line = m.group(1).strip() if m else ""
    ck("默认**开启**" in line, "C1 %s 默认值标注为「开启」" % name, line)
ck("默认**关闭**" not in sec, "C2 无残留「默认关闭」误标")

# ---------------------------------------------- D. 信息对话框按钮配色统一
section("D. 信息对话框按钮配色统一")
start = html.find('id="doc-info-mask"')
end = html.find('id="word-help-mask"')
block = html[start:end]
btn_tags = re.findall(r'<button\b[^>]*>', block)
info_btns = {}
for tag in btn_tags:
    idm = re.search(r'\bid="([^"]+)"', tag)
    cm = re.search(r'\bclass="([^"]+)"', tag)
    if idm and cm and idm.group(1) in ("btn-history", "doc-info-delete", "doc-info-close2"):
        info_btns[idm.group(1)] = cm.group(1)
ck(set(info_btns) == {"btn-history", "doc-info-delete", "doc-info-close2"},
   "D1 三个按钮齐备（历史版本/删除/关闭）", set(info_btns))
ck(all("ghost" in c for c in info_btns.values()), "D2 三个按钮均为 ghost 白底", info_btns)
ck(all("danger" not in c for c in info_btns.values()), "D3 无 danger 红底残留", info_btns)

# ---------------------------------------------- E. 信息对话框排版统一（kv-list）
section("E. 信息对话框排版统一（kv-list）")
ck('id="doc-info-list"' in block and 'class="kv-list"' in block, "E1 使用 dl.kv-list 键值列表")
for did in ("doc-info-path", "doc-info-abs", "doc-info-size", "doc-info-mtime", "doc-info-versions"):
    ck('id="%s"' % did in block, "E2 含字段 %s" % did)
ck(all(t in block for t in ("相对路径", "绝对路径", "大小", "修改时间", "历史版本数")), "E3 dt 标签齐全")
ck("doc-info-meta" not in block, "E4 旧单行拼接 doc-info-meta 已移除")
ck("document.getElementById('doc-info-size')" in html, "E5 openDocInfo 填充 大小")
ck("document.getElementById('doc-info-mtime')" in html, "E6 openDocInfo 填充 修改时间")
ck("document.getElementById('doc-info-versions')" in html, "E7 openDocInfo 填充 历史版本数")
ck("'相对路径：'" not in html and "'绝对路径：'" not in html, "E8 旧拼接文本已移除")

# ---------------------------------------------- F. 二次确认统一为自定义 showConfirm
section("F. 二次确认统一")
att = re.search(r'function attachSecurityConfirm\(id, name\) \{.*?\n        \}', html, re.S)
att = att.group(0) if att else ""
ck("showConfirm(" in att, "F1 安全开关确认使用 showConfirm", att[:60].replace("\n", " "))
ck("_confirmCancel" in html, "F2 showConfirm 支持 onCancel 回调")
ck("function () { const cc = _confirmCancel; hideConfirm(); if (cc) cc(); }" in html,
   "F3 Esc 关闭触发 onCancel")
ck("const cc = _confirmCancel; hideConfirm(); if (cc) cc();" in html, "F4 取消按钮触发 onCancel")
# 原生 confirm() 为小写 confirm(；showConfirm/hideConfirm 均为大写 C，不计入
native_count = html.count("confirm(")
ck(native_count == 0, "F5 全站无原生 confirm() 调用", native_count)

# ---------------------------------------------- G. 移动端按钮行滑动
section("G. 信息对话框窄屏可左右滑动")
ck("#doc-info-card .set-foot" in css, "G1 源 CSS 含 #doc-info-card .set-foot 作用域")
ck(bool(re.search(r"@media[^{]*\{[^}]*#doc-info-card", css)), "G2 窄屏 media query 限定到信息对话框")
ck("#doc-info-card .set-foot" in html, "G3 内联样式已同步（apply_style_v414 已跑）")

# ---------------------------------------------- H. 新建文档默认文件名
section("H. 新建文档默认文件名")
ck("'未命名文档'" in html, "H1 默认文件名已改为「未命名文档」")
ck("'未命名文档.md'" not in html, "H2 无残留「未命名文档.md」默认名")

# ---------------------------------------------- I. 源码可解析
section("I. 源码语法")
try:
    compile(srv, SRV, "exec")
    ck(True, "I1 server.py 语法正确")
except SyntaxError as e:
    ck(False, "I1 server.py 语法正确", e)

print("\n==============================")
print("PASS=%d  FAIL=%d" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:")
    for f in FAIL:
        print("  - " + f)
    sys.exit(1)
print("ALL GREEN")
sys.exit(0)
