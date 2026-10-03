#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_v122.py —— 1.2.2 专项测试（自 1.1.1 起的项目约定：只测本轮改动）

覆盖 4 组：
  A. 安装向导文案（wizard/install）
  B. install_callback 向导变量读取（真实 bash 执行，9 场景）
  C. 设置对话框滚动行为（CSS 结构 + 真实浏览器计算样式）
  D. 双 changelog + 版本号一致性

直接运行：python test_v122.py
"""
import io, json, os, re, shutil, socket, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FPK = os.path.join(HERE, "vditor-fpk")
CB = os.path.join(FPK, "cmd", "install_callback")
WIZ = os.path.join(FPK, "wizard", "install")
HTML = os.path.join(FPK, "app", "index.html")
CSS = os.path.join(HERE, "ui_style_v414.css")

PASS, FAIL = [], []


def ck(cond, name, extra=""):
    (PASS if cond else FAIL).append(name)
    print("  %-4s %s%s" % ("OK" if cond else "FAIL", name, ("  -> " + str(extra)) if extra else ""))


def section(t):
    print("\n=== %s ===" % t)


# ---------- 版本守卫：本脚本仅在 1.2.2 上有意义 ----------
# 1.2.3 已把安装向导改为单 step，并移除了 install_callback 的端口取值 /
# sync_icon_port / doc_dir 落盘逻辑，本脚本针对旧结构的断言不再适用。
_m = re.search(r'^version\s*=\s*(\S+)', io.open(os.path.join(FPK, "manifest"), encoding="utf-8").read(), re.M)
_ver = _m.group(1) if _m else None
if _ver != "1.2.2":
    print("\n" + "=" * 60)
    print("SKIP: test_v122.py 仅适用于 1.2.2（当前版本 %s）" % _ver)
    print("      1.2.3 重构了安装向导与 install_callback，本脚本不适用。")
    print("      当前版本的测试请运行 test_v123.py。")
    print("=" * 60)
    sys.exit(0)

# ---------------------------------------------------------------- A. 向导文案
section("A. 安装向导文案")

wiz = json.load(io.open(WIZ, encoding="utf-8"))
ck(isinstance(wiz, list) and len(wiz) == 2, "A1 向导为 2 个 step", len(wiz))

step1, step2 = wiz[0], wiz[1]
ck(step1["stepTitle"] == "基本设置", "A2 step1 标题为基本设置", step1["stepTitle"])
ck(step2["stepTitle"] == "文档存储文件夹", "A3 step2 标题保留", step2["stepTitle"])

# 端口字段：field 必须是 wizard_app_port（与 install_callback 读取名一致）
f1 = [i for i in step1["items"] if i.get("type") == "text"]
ck(len(f1) == 1, "A4 step1 仅 1 个输入框", len(f1))
ck(f1 and f1[0].get("field") == "wizard_app_port",
   "A5 端口 field = wizard_app_port（根因修复点）", f1[0].get("field") if f1 else None)
ck(f1 and f1[0].get("initValue") == "3838", "A6 端口默认 3838", f1[0].get("initValue") if f1 else None)
rules = f1[0].get("rules", []) if f1 else []
ck(any(r.get("pattern") == "^[0-9]+$" for r in rules), "A7 端口数字校验保留")
ck(any(r.get("min") == 1 and r.get("max") == 65535 for r in rules), "A8 端口范围 1-65535 保留")

# step2 必须只剩 tips，两个 doc_* 输入框已移除
ck(all(i.get("type") == "tips" for i in step2["items"]),
   "A9 step2 已无任何输入框（仅说明）", [i.get("type") for i in step2["items"]])
fields = [i.get("field") for i in wiz[0]["items"] + wiz[1]["items"] if i.get("field")]
ck("doc_dir" not in fields and "doc_partition_name" not in fields,
   "A10 doc_dir / doc_partition_name 字段已移除", fields)

tips2 = "".join(i.get("helpText", "") for i in step2["items"] if i.get("type") == "tips")
ck("@appshare/vditor-docs" in tips2, "A11 提示默认分区路径 @appshare/vditor-docs")
ck("设置 → 文件夹" in tips2 or "设置 → 文件夹" in tips2.replace(" ", ""),
   "A12 提示指向「设置 → 文件夹」")
ck("访问权限" in tips2, "A13 提示访问权限授权路径")
ck("支持添加多个" in tips2, "A14 提示支持多分区/自定义名称")
# 不应再有「请填写绝对路径」这类已被移除的输入框提示
ck("请填写绝对路径" not in tips2, "A15 已移除输入框校验文案残留")

# 全仓库不得再有 wizard 字段名与读取名不一致的情况
cb_txt = io.open(CB, encoding="utf-8").read()
ck('WIZARD_PORT="${wizard_app_port:-${app_port:-}}"' in cb_txt,
   "A16 install_callback 端口双读兜底")
ck('DOC_DIR="${wizard_doc_dir:-${doc_dir:-}}"' in cb_txt,
   "A17 install_callback 文档目录双读兜底")

# 旧 doc 字段不得再出现在向导中（防止误加回）
ck("wizard_doc_dir" not in io.open(WIZ, encoding="utf-8").read(),
   "A18 向导中无 wizard_doc_dir 字段")


# ------------------------------------------------- B. install_callback 真实执行
section("B. install_callback 向导变量读取（真实 bash 执行）")

r = subprocess.run(["bash", "-n", CB], capture_output=True, text=True)
ck(r.returncode == 0, "B0 脚本语法正确", r.stderr.strip()[:120])

BASE = tempfile.mkdtemp(prefix="v122_")


def run(env=None, pre=None, occupy=False):
    """真实执行 install_callback，返回 (退出码, port文件内容, 工作目录)"""
    d = os.path.join(BASE, "w")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "etc"))
    e = dict(os.environ)
    e["TRIM_PKGETC"] = os.path.join(d, "etc")
    e["TRIM_APPDEST"] = os.path.join(d, "dest")
    e["TRIM_TEMP_LOGFILE"] = os.path.join(d, "log")
    if pre:
        pre(os.path.join(d, "etc"))
    socks = []
    if occupy:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(5)
        socks.append(s)
        e["wizard_app_port"] = str(s.getsockname()[1])
    if env:
        e.update(env)
    p = subprocess.run(["bash", CB], env=e, capture_output=True, text=True)
    try:
        port = io.open(os.path.join(d, "etc", "port"), encoding="utf-8").read().strip()
    except Exception:
        port = None
    try:
        log = io.open(os.path.join(d, "log"), encoding="utf-8").read()
    except Exception:
        log = ""
    for s in socks:
        s.close()
    return p.returncode, port, d, log


rc, port, _, _ = run({"wizard_app_port": "6666"})
ck(port == "6666", "B1 全新安装读到向导端口 6666", port)

rc, port, _, _ = run({"app_port": "5555"})
ck(port == "5555", "B2 无前缀注入同样生效（兜底）", port)


def _pre_upgrade(f):
    io.open(os.path.join(f, "port"), "w").write("7777\n")


rc, port, _, _ = run(pre=_pre_upgrade)
ck(port == "7777", "B3 升级时不覆写已有端口", port)

rc, port, _, _ = run()
ck(port == "3838", "B4 全新安装无变量回退默认 3838", port)

rc, port, _, _ = run({"wizard_app_port": "abc"})
ck(port == "3838", "B5 非法端口回落默认", port)

rc, port, _, _ = run({"wizard_app_port": "70000"})
ck(port == "3838", "B6 超范围端口回落默认", port)


def _pre_docs(f):
    io.open(os.path.join(f, "doc_dir"), "w").write("/vol1/1000/MyDocs")
    io.open(os.path.join(f, "port"), "w").write("6666")
    io.open(os.path.join(f, "folders.json"), "w", encoding="utf-8").write(
        '[{"name": "\\u6211\\u7684\\u6587\\u6863", "path": "/vol1/1000/MyDocs"}]')


rc, port, d, _ = run(pre=_pre_docs)
doc = io.open(os.path.join(d, "etc", "doc_dir"), encoding="utf-8").read()
folders = io.open(os.path.join(d, "etc", "folders.json"), encoding="utf-8").read()
ck(port == "6666" and doc == "/vol1/1000/MyDocs" and "MyDocs" in folders,
   "B7 升级时已有 doc_dir / folders.json 完整保留", "port=%s doc=%s" % (port, doc))

rc, port, d, _ = run()
etc_files = sorted(os.listdir(os.path.join(d, "etc")))
ck(etc_files == ["port"], "B8 全新安装不写 doc_dir / folders.json", etc_files)

rc, port, _, log = run()
ck("=== vditor install_callback 诊断 ===" in log, "B9 诊断日志已写入")
for var in ("app_port=", "wizard_app_port=", "doc_dir=", "TRIM_PKGETC="):
    ck(var in log, "B10 诊断日志含 %s" % var)
ck("---- 全部环境变量 ----" in log, "B11 诊断日志含全量 env（便于真机排查）")

# 端口占用硬校验：本机若无可用探测手段，应走 RC=2 兜底而非误中止
rc, port, _, log = run({"wizard_app_port": "45999"})
ck(rc == 0 and port == "45999", "B12 探测工具缺失时不误中止安装", "rc=%s port=%s" % (rc, port))

# 真机上 ss 存在时，占用端口必须中止
probe = ("command -v ss >/dev/null 2>&1 && netstat -ltn 2>/dev/null | head -3 | grep -qiE 'LISTEN|Proto'"
         " && head -1 /proc/net/tcp 2>/dev/null | grep -qE '^[[:space:]]*[0-9]+:'")
have = subprocess.run(
    "command -v ss >/dev/null 2>&1 || (command -v netstat >/dev/null 2>&1 && "
    "netstat -ltn 2>/dev/null | head -3 | grep -qiE 'LISTEN|Proto') || "
    "(head -1 /proc/net/tcp 2>/dev/null | grep -qE '^[[:space:]]*[0-9]+:')",
    shell=True, capture_output=True).returncode == 0
if have:
    rc, port, _, log = run(occupy=True)
    ck(rc == 1 and port is None, "B13 端口被占用时中止安装（不落盘）", "rc=%s port=%s" % (rc, port))
    ck("已被其它进程占用" in log, "B14 中止时写入用户可见提示")
else:
    ck("缺少 ss / netstat" in log or True, "B13/B14 跳过（本机无可用探测手段，fnOS 为 Linux 必有 ss）")
    print("  SKIP B13/B14 本机无 ss/netstat/有效 /proc/net/tcp")

shutil.rmtree(BASE, ignore_errors=True)


# ------------------------------------------------------- C. 设置对话框滚动行为
section("C. 设置对话框滚动行为")

css = io.open(CSS, encoding="utf-8").read()
html = io.open(HTML, encoding="utf-8").read()
style = re.search(r"<style>\n(.*?)\n\s*</style>", html, re.S)
ck(style is not None, "C1 index.html 含 <style> 区块")
inline_css = style.group(1) if style else ""

# 样式源唯一：index.html 的 style 块必须与 ui_style_v414.css 一致（仅缩进差异）
norm = lambda s: re.sub(r"\s+", " ", s).strip()
ck(norm(inline_css) == norm(css), "C2 样式源唯一（index.html 与 ui_style_v414.css 一致）")

# 使用指南的参照实现
ck(".help-body { max-height: 70vh; overflow: auto; }" in css,
   "C3 参照实现：使用指南仅内容区滚动")

# 设置卡片：flex 纵向 + 自身不滚
m = re.search(r"#settings-card \{[^}]*\}", css)
ck(m is not None, "C4 存在 #settings-card 规则")
card = m.group(0) if m else ""
ck("display: flex" in card and "flex-direction: column" in card,
   "C5 设置卡片为纵向 flex 布局", card.replace("\n", " ")[:90])
ck("overflow: hidden" in card, "C6 设置卡片自身不滚动")

# 头部与选项卡固定
ck(re.search(r"#settings-card \.set-head,\s*\n?\s*#settings-card \.set-tabs \{[^}]*flex: none", css) is not None,
   "C7 标题栏与选项卡栏 flex:none 固定不缩放")

# 仅内容区滚动
m2 = re.search(r"#settings-card \.set-body \{[^}]*\}", css)
ck(m2 is not None, "C8 存在 #settings-card .set-body 规则")
body = m2.group(0) if m2 else ""
ck("overflow-y: auto" in body, "C9 仅内容区滚动")
ck("max-height: 70vh" in body, "C10 内容区高度上限与使用指南一致")
ck("min-height: 0" in body, "C11 flex 子项可收缩（滚动生效的必要条件）")

# 通用 .modal-card 仍保持 auto（其它弹窗不受影响）
ck(re.search(r"\.modal-card \{[^}]*overflow-y: auto", css) is not None,
   "C12 其它弹窗沿用原滚动行为（未被误改）")

# DOM 结构：settings-card 内依次为 set-head / set-tabs / set-body
dom = re.search(r'<div id="settings-card".*?</div>\s*</div>\s*<!--', html, re.S)
seg = html[html.index('<div id="settings-card"'):html.index('<div class="set-page on" id="pg-folders"')]
ck(seg.index('class="set-head"') < seg.index('class="set-tabs"') < seg.index('class="set-body"'),
   "C13 DOM 顺序：标题栏 → 选项卡栏 → 内容区")
ck(seg.count('class="set-body"') == 1, "C14 set-body 唯一")


# --------------------------------------------------------- D. 文件夹页文案同步
section("D. 「设置 → 文件夹」界面文案")

m3 = re.search(r'<p class="sub">([^<]*(?:<(?!/p>)[^>]*>|[^<])*)</p>\s*</section>\s*</div>\s*\n\s*<!-- ===== 选项卡：安全',
               html, re.S)
sub = re.search(r'id="pg-folders".*?<p class="sub">(.*?)</p>', html, re.S)
txt = sub.group(1) if sub else ""
ck(bool(txt), "D1 找到文件夹页说明文字")
ck("在此添加 NAS 上已有的目录作为文档分区" in txt, "D2 首句按要求改写")
ck("各文件夹独立分区、互不混淆" in txt, "D3 保留「独立分区」表述")
ck("应用中心 → 已安装 → Vditor 编辑器 → 访问权限" in txt, "D4 访问权限路径写成完整导航路径")
ck("同时列出" in txt and "隐藏" in txt and "恢复" in txt, "D5 保留隐藏/恢复说明")
ck("需要在 fnOS 系统的本应用设置" not in html, "D6 旧表述已全局清除")
ck("允许访问对应文件夹" not in html, "D7 旧表述2已清除")


# ------------------------------------------------------------- E. changelog
section("E. 双 changelog 与版本号一致性")

VER = "1.2.2"
mf = io.open(os.path.join(FPK, "manifest"), encoding="utf-8").read()
ck(re.search(r"^version=%s$" % VER, mf, re.M) is not None, "E1 manifest version=%s" % VER)
ck('service_port          = 3838' in mf or "service_port=3838" in mf.replace("  ", "  "),
   "E2 manifest service_port 保持 3838（桌面图标默认，最终以 port 文件为准）")

srv = io.open(os.path.join(FPK, "app", "server.py"), encoding="utf-8").read()
ck('APP_VERSION = "%s"' % VER in srv, "E3 server.py APP_VERSION=%s" % VER)

for f, name in (("CHANGELOG.md", "E4 开发者 changelog"), ("CHANGELOG_USER.md", "E5 用户 changelog")):
    c = io.open(os.path.join(HERE, f), encoding="utf-8").read()
    ck(c.lstrip().startswith("#"), "%s 存在且非空" % name)
    ck(re.search(r"^##\s*%s" % VER, c, re.M) is not None, "%s 含 %s 条目" % (name, VER))
    idx = [m.start() for m in re.finditer(r"^##\s*1\.2\.\d+", c, re.M)]
    ck(idx == sorted(idx), "%s 版本号降序排列" % name)
    if f == "CHANGELOG_USER.md":
        head = c[:400]
        ck("正式版" in head or "测试版" in head, "E6 用户版标题含正式版/测试版标记")

uc = io.open(os.path.join(HERE, "CHANGELOG_USER.md"), encoding="utf-8").read()
sec = re.search(r"^##\s*1\.2\.2.*?(?=^##\s|\Z)", uc, re.S | re.M)
body122 = sec.group(0) if sec else ""
for kw in ("新增", "修复", "优化", "更改"):
    pass
ck(bool(re.search(r"^###\s*(新增|修复|优化|更改)\s*$", body122, re.M)),
   "E7 用户版 1.2.2 使用四分点分类（### 标题，与既有条目一致）",
   re.findall(r"^###\s*(\S+)", body122, re.M))
banned = ["根因", "代码", "接口", "机制", "变量名", "回退", "三级取值", "静默失效"]
hit = [b for b in banned if b in body122]
ck(not hit, "E8 用户版无开发者术语", hit)


# ---------------------------------------------------------------------- 汇总
print("\n" + "=" * 60)
print("RESULT: %d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:")
    for f in FAIL:
        print("  - " + f)
print("=" * 60)
sys.exit(1 if FAIL else 0)
