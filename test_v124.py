#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_v124.py —— 1.2.4 专项测试

本轮改动：设置面板结构重构（选项卡合并/更名/重排/子选项层级整理）、
移动端按钮行溢出修复、按钮配色统一、访问来源判定修正。

直接运行：python test_v124.py
"""
import io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FPK = os.path.join(HERE, "vditor-fpk")
HTML = os.path.join(FPK, "app", "index.html")
CSS = os.path.join(HERE, "ui_style_v414.css")
WIZ = os.path.join(FPK, "wizard", "install")
MF = os.path.join(FPK, "manifest")
SRV = os.path.join(FPK, "app", "server.py")
VER = "1.2.4"

PASS, FAIL = [], []


def ck(cond, name, extra=""):
    (PASS if cond else FAIL).append(name)
    print("  %-4s %s%s" % ("OK" if cond else "FAIL", name, ("  -> " + str(extra)) if extra else ""))


def section(t):
    print("\n=== %s ===" % t)


html = io.open(HTML, encoding="utf-8").read()
css = io.open(CSS, encoding="utf-8").read()
srv = io.open(SRV, encoding="utf-8").read()

# ---------------------------------------------------- A. 选项卡结构与顺序
section("A. 选项卡结构与顺序")

EXPECT_TABS = ["分区", "文件", "安全", "外观", "维护", "关于与帮助"]
EXPECT_PAGES = ["pg-folders", "pg-file", "pg-security", "pg-appearance", "pg-maint", "pg-about"]

tabs = re.findall(r'<button type="button"[^>]*data-page="(pg-[a-z]+)">([^<]+)</button>', html)
ck([p for p, _ in tabs] == EXPECT_PAGES, "A1 标签页 data-page 顺序正确",
   [p for p, _ in tabs])
ck([n.strip() for _, n in tabs] == EXPECT_TABS, "A2 标签页名称与顺序正确",
   [n.strip() for _, n in tabs])

pages = re.findall(r'class="set-page[^"]*" id="(pg-[a-z]+)"', html)
ck(pages == EXPECT_PAGES, "A3 面板 id 与顺序一致", pages)
ck(set(p for p, _ in tabs) == set(pages), "A4 标签页与面板一一对应")
ck('data-page="pg-version"' not in html and 'data-page="pg-upload"' not in html,
   "A5 旧选项卡 pg-version / pg-upload 已移除")
ck('id="pg-version"' not in html and 'id="pg-upload"' not in html,
   "A6 旧面板 id 已移除")

# ------------------------------------------------------ B. 子选项层级整理
section("B. 子选项层级（只应一层）")

# 顶层 h3（与选项卡同名的冗余标题）应已全部删除
top_h3 = re.findall(r'<section class="set-sec">\s*<h3>([^<]+)</h3>', html)
ck(not top_h3, "B1 无「section > h3」冗余首层标题", top_h3)
ck("<h4" not in html, "B2 无 h4 残留（子选项应升级为 h3）",
   len(re.findall(r"<h4", html)))

EXPECT_SUBS = {
    "pg-folders": ["现有分区管理", "添加分区"],
    "pg-file": ["文件版本与自动保存", "附件上传"],
    "pg-security": ["网络访问安全", "修改登录密码"],
    "pg-appearance": ["外观设置"],
    "pg-maint": ["备份与恢复", "状态与日志", "卸载时的应用数据处理"],
    "pg-about": ["帮助与快捷键", "关于本应用", "开源协议与法律声明"],
}
for pid, want in EXPECT_SUBS.items():
    # 从该面板的 set-page 起始处截取，到下一个 set-page（或 set-foot）为止
    i = html.index('<div class="set-page%s" id="%s">' % (" on" if pid == "pg-folders" else "", pid))
    k = html.find('<div class="set-page', i + 10)
    if k < 0:
        k = html.index('<div class="set-foot">', i)
    seg = html[i:k]
    got = re.findall(r'<div class="set-sub">\s*<h3>([^<]+)</h3>', seg)
    ck(got == want, "B3 %s 子选项标题正确" % pid, got)

ck(css.count(".set-sub h3 {") == 1, "B4 子选项 h3 样式已定义",
   css.count(".set-sub h3 {"))
def code_without_comments(s):
    """剔除 HTML 与 CSS 两种注释后再检查类名残留。

    注意：index.html 的 <style> 块内是 CSS 注释（/* */），
    只剔 <!-- --> 会漏掉 —— 本项目一贯在注释里记录迁移历史，属正常。
    """
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return s

ck(".set-pw" not in code_without_comments(html), "B5 HTML 中无 set-pw 旧类名（注释外）",
   [l for l in code_without_comments(html).split("\n") if "set-pw" in l])
ck(".set-pw" not in code_without_comments(css), "B6 CSS 中 set-pw 已全部迁移（注释外）",
   [l for l in code_without_comments(css).split("\n") if "set-pw" in l])

# ---------------------------------------------- C. 分区选项卡拆分与文案
section("C. 分区选项卡拆分")

i = html.index('<div class="set-page on" id="pg-folders">')
j = html.find('<div class="set-page', i + 10)
seg = html[i:j]
# 现有分区管理：只含列表与说明，不含添加控件
a_start = seg.index("现有分区管理")
a_end = seg.index("添加分区")
a_blk, b_blk = seg[a_start:a_end], seg[a_end:]
ck('id="folders-list"' in a_blk, "C1 「现有分区管理」含分区列表")
ck('id="folder-add"' not in a_blk, "C2 「现有分区管理」不含添加按钮")
ck('id="folder-path"' not in a_blk, "C3 「现有分区管理」不含路径输入框")
ck('id="folders-err"' not in a_blk, "C4 「现有分区管理」不含错误提示区")
ck('id="folder-name"' in b_blk and 'id="folder-path"' in b_blk,
   "C5 「添加分区」含显示名与路径两个输入框")
ck('id="folder-add"' in b_blk, "C6 「添加分区」含添加按钮")
ck(">添加分区</button>" in b_blk, "C7 按钮文案改为「添加分区」")
ck("访问权限" in b_blk, "C8 「添加分区」含访问权限授权说明")
ck("可对其执行「隐藏」" in a_blk or "隐藏" in a_blk, "C9 「现有分区管理」含隐藏/恢复说明")

# 文件选项卡功能完整（两页合并后元素须都在）
i = html.index('<div class="set-page" id="pg-file">')
j = html.find('<div class="set-page', i + 10)
fseg = html[i:j]
for eid, label in [("set-versioning", "历史版本开关"), ("set-max-versions", "最大版本数"),
                   ("set-autosave", "自动保存间隔"), ("set-upload-max", "上传大小上限"),
                   ("set-upload-deny", "格式黑名单"), ("btn-deny-add", "添加按钮"),
                   ("btn-deny-reset", "恢复默认"), ("deny-list", "黑名单列表"),
                   ("upload-deny-err", "黑名单错误提示")]:
    ck('id="%s"' % eid in fseg, "C10 「文件」含 %s（%s）" % (eid, label))

# 旧 id 未被误删
for eid in ("set-versioning", "set-max-versions", "set-autosave",
            "set-upload-max", "set-upload-deny", "folder-add", "folder-path", "folder-name"):
    ck(html.count('id="%s"' % eid) == 1, "C11 控件 %s 唯一存在" % eid,
       html.count('id="%s"' % eid))

# ------------------------------------------------- D. 移动端溢出与按钮配色
section("D. 移动端溢出与按钮配色")

ck(".frow { display: flex; flex-wrap: wrap;" in css,
   "D1 按钮行允许换行（flex-wrap: wrap）")
m = re.search(r"#settings-card \.set-body \{[^}]*\}", css)
ck(m and "overflow-x: hidden" in m.group(0), "D2 内容区关闭横向滚动")
ck(m and "overflow-y: auto" in m.group(0), "D3 内容区仍保留纵向滚动")
ck("@media screen and (max-width: 560px)" in css, "D4 存在窄屏按钮均分规则")
# .frow 按钮不再用 flex:0 0 auto（会拒绝收缩）
mb = re.search(r"\.frow button \{[^}]*\}", css)
ck(mb and "flex: 0 0 auto" not in mb.group(0), "D5 按钮允许收缩（去掉 flex:0 0 auto）",
   mb.group(0) if mb else None)

# 三个指定按钮应为 ghost（白底）
def btn_class(eid):
    """取按钮的 class —— class 与 id 的先后顺序不固定，两种都试。"""
    m = re.search(r'<button[^>]*\bid="%s"[^>]*>' % re.escape(eid), html)
    if not m:
        return None
    c = re.search(r'class="([^"]+)"', m.group(0))
    return c.group(1) if c else ""

for eid, label in [("btn-refresh-status", "应用状态"), ("btn-backup", "导出备份"),
                   ("btn-word-help", "使用指南")]:
    c = btn_class(eid)
    ck("ghost" in c, "D6 「%s」为 ghost 白底" % label, c or "未找到")

# 并排基准按钮也应为 ghost
for eid in ("btn-view-app-log", "btn-kb-help", "btn-restore-backup"):
    c = btn_class(eid)
    ck("ghost" in c, "D7 基准按钮 %s 为 ghost" % eid, c or "未找到")

# --------------------------------------------- E. 访问来源判定（后端）
section("E. 应用状态访问来源判定")

mb2 = re.search(r"def _build_status\(self\):.*?\n        return \{", srv, re.S)
ck(mb2 is not None, "E1 _build_status 可定位")
blk = mb2.group(0) if mb2 else ""
ck("lan = is_private_ip(c_ip)" in blk,
   "E2 isLan 改用真实客户端 IP 判定（非 direct）")
ck("lan = is_private_ip(direct)" not in blk, "E3 不再用直连来源判定局域网")
net_blk = re.search(r'"network": \{.*?\n            \},', srv, re.S)
nb = net_blk.group(0) if net_blk else ""
ck('"clientIp": c_ip' in nb, "E4 对外 clientIp 为真实客户端 IP")
ck('"viaProxy": via_proxy' in nb, "E5 新增 viaProxy 字段")
ck("via_proxy = c_ip != direct" in blk, "E6 viaProxy 依 XFF 首段与直连来源比对")
# 确认 c_ip 来自 client_ip()
ci = re.search(r"c_ip = client_ip\(self\)", blk)
ck(ci is not None, "E7 c_ip 取自 client_ip()（含 XFF 解析）")
# 前端渲染同步
ck("n.viaProxy" in html, "E8 前端渲染使用 viaProxy")
ck("外部网络（经代理 / 内网穿透）" in html, "E9 前端区分显示经代理的外部网络来源")

# ---------------------------------------------- F. 文案同步（文件夹 → 分区）
section("F. 文案同步")

wiz = json.load(io.open(WIZ, encoding="utf-8"))
h = wiz[0]["items"][0]["helpText"]
ck("设置 → 分区" in h, "F1 安装向导已同步为「设置 → 分区」")
ck("文件夹" not in h, "F2 安装向导无「文件夹」残留")
ck(len(json.load(io.open(WIZ, encoding="utf-8"))) == 1, "F3 向导仍为单 step")
ck("&lt;NASIP&gt;" in h, "F4 NASIP 转义保留")

ck("设置 → 文件夹" not in html, "F5 前端无「设置 → 文件夹」残留")
ck("设置 → 分区" in html, "F6 前端含「设置 → 分区」")
ck("已添加分区" in html, "F7 toast 文案改为「已添加分区」")
ck("已删除分区" in html, "F8 toast 文案改为「已删除分区」")
ck("请填写目录绝对路径" in html, "F9 校验提示改为「目录绝对路径」")

mf = io.open(MF, encoding="utf-8").read()
ck(re.search(r"^version=%s$" % VER, mf, re.M) is not None, "F10 manifest version=%s" % VER)
ck('APP_VERSION = "%s"' % VER in srv, "F11 server.py APP_VERSION=%s" % VER)
ch = re.search(r"^changelog=(.*)$", mf, re.M).group(1)
for v in ["1.2.4", "1.2.3", "1.2.2", "1.2.1"]:
    ck(ch.count(v + "：") == 1, "F12 changelog 中 %s 条目唯一" % v, ch.count(v + "："))

# ------------------------------------------------------- G. 样式源唯一性
section("G. 样式源唯一性")

style = re.search(r"<style>\n(.*?)\n\s*</style>", html, re.S)
ck(style is not None, "G1 index.html 含 <style> 区块")
norm = lambda s: re.sub(r"\s+", " ", s).strip()
ck(norm(style.group(1)) == norm(css), "G2 index.html 与 ui_style_v414.css 完全一致")

# ---------------------------------------------------------------------- 汇总
print("\n" + "=" * 60)
print("RESULT: %d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:")
    for f in FAIL:
        print("  - " + f)
print("=" * 60)
sys.exit(1 if FAIL else 0)
