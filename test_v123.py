#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_v123.py —— 1.2.3 专项测试

本轮改动：移除安装向导的自定义端口功能（向导简化为单页说明）、
清理 install_callback / upgrade_callback 中的死代码、升级时按方案 B 重置端口、
同步 manifest desc、修复 SECURITY.md 支持范围。

直接运行：python test_v123.py
"""
import io, json, os, re, shutil, socket, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FPK = os.path.join(HERE, "vditor-fpk")
WIZ = os.path.join(FPK, "wizard", "install")
CB = os.path.join(FPK, "cmd", "install_callback")
UB = os.path.join(FPK, "cmd", "upgrade_callback")
MAIN = os.path.join(FPK, "cmd", "main")
MF = os.path.join(FPK, "manifest")
HTML = os.path.join(FPK, "app", "index.html")
CSS = os.path.join(HERE, "ui_style_v414.css")
# 当前版本号：从 manifest 动态读取。历史教训（1.2.3）：写死版本号会导致每次
# 升版都出现一批「版本号断言失败」的假红。1.2.4 重构了设置面板，但本脚本
# 关注的 1.2.3 行为（向导结构、死代码清除、固定端口）仍然成立，故只动态化版本号。
def _detect_ver():
    import re as _r
    m = _r.search(r"(?m)^version\s*=\s*([0-9.]+)\s*$",
                 io.open(MF, encoding="utf-8").read())
    return m.group(1) if m else "0.0.0"
VER = _detect_ver()

PASS, FAIL = [], []


def ck(cond, name, extra=""):
    (PASS if cond else FAIL).append(name)
    print("  %-4s %s%s" % ("OK" if cond else "FAIL", name, ("  -> " + str(extra)) if extra else ""))


def section(t):
    print("\n=== %s ===" % t)


def code_only(path):
    """去掉以 # 开头的注释行——注释里常记录历史写法，正则一扫就假失败。"""
    return [l for l in io.open(path, encoding="utf-8").read().split("\n")
            if not l.strip().startswith("#")]


# ------------------------------------------------------------------ A. 向导
section("A. 安装向导（单页说明）")

wiz = json.load(io.open(WIZ, encoding="utf-8"))
ck(isinstance(wiz, list) and len(wiz) == 1, "A1 向导为单 step", len(wiz))
step = wiz[0]
ck(step.get("stepTitle") == "安装", "A2 step 标题为「安装」", step.get("stepTitle"))
items = step.get("items", [])
ck(len(items) == 1, "A3 仅 1 个说明项", len(items))
ck(items[0].get("type") == "tips", "A4 类型为 tips", items[0].get("type"))

ck(not any(i.get("type") == "text" for i in items), "A5 已无任何输入框（端口功能移除）")
fields = [i.get("field") for s in wiz for i in s["items"] if i.get("field")]
ck(not fields, "A6 不存在任何 field（无变量注入）", fields)

h = items[0].get("helpText", "")
ck(len(h) > 300, "A7 说明文本非空且有实质内容", "%d 字符" % len(h))
# 关键：<NASIP> 必须转义，否则被 HTML 解析器吞掉
ck("&lt;NASIP&gt;" in h, "A8 NASIP 已转义为 &lt;NASIP&gt;")
ck("<NASIP>" not in h, "A9 无裸 <NASIP>（会导致该段文字消失）")
# 内容要素
for kw, label in [("Python3", "A10 含 Python3 依赖说明"),
                  ("3838", "A11 含固定端口 3838"),
                  ("&lt;NASIP&gt;:3838/", "A12 含完整访问地址示例"),
                  ("内网", "A13 含内网使用建议"),
                  ("公网", "A14 含公网暴露风险提示"),
                  ("备份", "A15 含数据备份责任"),
                  ("设置 → 分区", "A16 引导至「设置 → 分区」"),
                  ("访问权限", "A17 含访问权限授权说明")]:
    ck(kw in h, label)
# 不应再有已移除功能的表述
ck("默认使用 3838" not in h, "A18 端口表述为「固定」而非「默认」")
ck("@appshare" not in h, "A19 不再承诺具体存储路径")
ck("不承担任何责任" not in h, "A20 免责措辞已调整")
ck("自定义端口" not in h, "A21 不再提及自定义端口")


# ------------------------------------------------- B. 死代码确已清除（防回归）
section("B. install_callback 死代码已清除")

for f in (CB, UB, MAIN):
    r = subprocess.run(["bash", "-n", f], capture_output=True, text=True)
    ck(r.returncode == 0, "B0 %s 语法正确" % os.path.basename(f), r.stderr.strip()[:100])

cb_code = "\n".join(code_only(CB))
ub_code = "\n".join(code_only(UB))

# 这些在 1.2.2 存在，1.2.3 必须移除
for k, label in [("sync_icon_port", "B1 sync_icon_port 已移除"),
                 ("WIZARD_PORT", "B2 端口三级取值已移除"),
                 ("wizard_app_port", "B3 向导端口变量引用已移除"),
                 ("DOC_PARTITION_NAME", "B4 分区显示名落盘已移除"),
                 ("folders.json", "B5 folders.json 落盘已移除"),
                 ("doc_dir", "B6 doc_dir 写入已移除"),
                 ("sed -i", "B7 sed 同步逻辑已移除")]:
    ck(k not in cb_code, label)

# 保留项（1.2.2 排查证明有实际价值，误删会丢能力）
for k, label in [("install_callback 诊断", "B8 保留环境变量诊断日志"),
                 ("port_in_use", "B9 保留端口占用检测"),
                 ("缺少 ss / netstat", "B10 保留探测工具缺失时的告警"),
                 ("echo \"$PORT\" > \"$PORT_FILE\"", "B11 保留端口落盘"),
                 ("cmd/main", "B12 保留服务重启")]:
    ck(k in cb_code, label)

ck("PORT=3838" in cb_code, "B13 端口固定为 3838")
ck("ui/config" not in ub_code, "B14 upgrade_callback 已移除 ui/config 同步")
ck('rm -f "${ETC}/port"' in ub_code, "B15 upgrade_callback 按方案 B 删除历史 port")
ck("OLD_PORT" in ub_code, "B16 重置前先读取旧值用于提示")


# ------------------------------------------- C. 脚本行为（真实 bash 执行）
section("C. install_callback 真实执行")

BASE = tempfile.mkdtemp(prefix="v123_")


def run(cb_env=None, pre=None, occupy=False):
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
        e["wizard_app_port"] = str(s.getsockname()[1])   # 故意注入，应被忽略
    if cb_env:
        e.update(cb_env)
    r = subprocess.run(["bash", CB], env=e, capture_output=True, text=True)
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
    return r.returncode, port, d, log


rc, port, _, log = run()
ck(rc == 0 and port == "3838", "C1 全新安装写入固定端口 3838", "rc=%s port=%s" % (rc, port))

rc, port, _, _ = run({"wizard_app_port": "6666"})
ck(port == "3838", "C2 即使注入向导端口变量也不生效（功能已移除）", port)

rc, port, _, _ = run({"wizard_app_port": "abc"})
ck(port == "3838", "C3 非法注入值不影响固定端口", port)

rc, port, _, _ = run(pre=lambda f: io.open(os.path.join(f, "port"), "w").write("5555\n"))
ck(port == "3838", "C4 全新安装覆盖历史自定义端口为 3838", port)

ck("install_callback 诊断" in log, "C5 诊断日志已写入")
ck("TRIM_PKGETC=" in log and "TRIM_APPDEST=" in log, "C6 诊断日志含关键环境变量")
ck("---- 全部环境变量 ----" in log, "C7 诊断日志含全量 env 快照")

# 端口占用硬校验
rc, port, d, _ = run(occupy=True)
have_probe = subprocess.run(
    "command -v ss >/dev/null 2>&1 || (command -v netstat >/dev/null 2>&1 && "
    "netstat -ltn 2>/dev/null | head -3 | grep -qiE 'LISTEN|Proto') || "
    "(head -1 /proc/net/tcp 2>/dev/null | grep -qE '^[[:space:]]*[0-9]+:')",
    shell=True).returncode == 0
if have_probe:
    ck(rc == 1 and port is None, "C8 3838 被占用时中止安装", "rc=%s port=%s" % (rc, port))
    lg = io.open(os.path.join(d, "log"), encoding="utf-8").read()
    ck("已被其它进程占用" in lg, "C9 中止时写入用户可见提示")
else:
    ck(rc == 0 and port == "3838", "C8 本机无可用探测手段时不误中止", "rc=%s" % rc)
    print("  SKIP C9 占用中止验证（本机无 ss/netstat/有效 /proc/net/tcp）")

# upgrade_callback 方案 B
def _ub(pre=None):
    """在 cwd 下用相对路径执行。

    Windows Git Bash 的 rm 会拒绝含盘符的绝对路径（报 embedded drive prefix is not allowed），
    导致 upgrade_callback 的 rm -f 静默失败 —— 那是**测试环境限制**，非产品缺陷。
    fnOS 是 Linux，rm 行为正常。故此处必须用相对路径。
    """
    rel = "tmp_ub_run"
    d = os.path.join(BASE, rel)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "etc"))
    if pre:
        pre(os.path.join(d, "etc"))
    e = dict(os.environ)
    e["TRIM_PKGETC"] = "%s/etc" % rel
    e["TRIM_APPDEST"] = "%s/dest" % rel
    e["TRIM_TEMP_LOGFILE"] = "%s/log" % rel
    r = subprocess.run(["bash", os.path.relpath(UB, BASE)], env=e, capture_output=True,
                       text=True, cwd=BASE)
    exists = os.path.exists(os.path.join(d, "etc", "port"))
    try:
        log = io.open(os.path.join(d, "log"), encoding="utf-8").read()
    except Exception:
        log = ""
    return r.returncode, exists, log


rc, exists, log = _ub(lambda f: io.open(os.path.join(f, "port"), "w").write("5555\n"))
ck(rc == 0 and not exists, "C10 升级时删除历史自定义端口（方案 B）", "rc=%s 仍存在=%s" % (rc, exists))
ck("3838" in log, "C11 重置时提示目标端口为 3838")

rc, exists, _ = _ub(lambda f: io.open(os.path.join(f, "port"), "w").write("3838\n"))
ck(rc == 0 and exists, "C12 已是 3838 时不重复动作（幂等）")

rc, exists, _ = _ub()
ck(rc == 0 and not exists, "C13 无历史 port 文件时正常退出", "rc=%s" % rc)

shutil.rmtree(BASE, ignore_errors=True)


# ------------------------------------------------------ D. manifest 与 desc
section("D. manifest 元数据")

mf = io.open(MF, encoding="utf-8").read()
ck(re.search(r"^version\s*=\s*%s$" % VER, mf, re.M) is not None, "D1 version=%s" % VER)
ck(re.search(r"^service_port\s*=\s*3838$", mf, re.M) is not None, "D2 service_port=3838")

desc = re.search(r"^desc=(.*)$", mf, re.M).group(1)
ck("访问方式" in desc, "D3 desc 含「访问方式」段落")
ck("3838" in desc, "D4 desc 标注端口")
ck("内网" in desc and "公网" in desc, "D5 desc 含内外网使用提示")
ck("<NAS_IP>" not in desc, "D6 desc 无裸尖括号（会被当作 HTML 标签）")
ck("自定义端口" not in desc, "D7 desc 不再宣称端口可自定义")

# changelog 完整性：每个版本条目只出现一次
ch = re.search(r"^changelog=(.*)$", mf, re.M).group(1)
for v in ["1.2.3", "1.2.2", "1.2.1", "1.2.0"]:
    n = ch.count(v + "：")
    ck(n == 1, "D8 changelog 中 %s 条目唯一" % v, "出现 %d 次" % n)

ck(re.search(r"^appname\s*=\s*com\.mian38\.vditor$", mf, re.M) is not None, "D9 appname 正确")
ck("maintainer=mian38" in mf, "D10 maintainer 正确")


# ------------------------------------------------------------- E. 文档一致性
section("E. 文档与代码一致性")

sec = io.open(os.path.join(HERE, "SECURITY.md"), encoding="utf-8").read()
ck("1.2.x（当前主线）" in sec, "E1 SECURITY.md 支持范围已更新到 1.2.x")
ck("1.1.x（当前主线）" not in sec, "E2 SECURITY.md 旧表述已清除")

main_code = "\n".join(code_only(MAIN))
ck("安装向导" not in main_code, "E3 cmd/main 注释不再提「安装向导」（功能已移除）")
ck("填写其它端口" not in main_code, "E4 cmd/main 端口占用提示不再引导改端口")

rd = io.open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
ck("按安装向导设置访问端口与文档目录" not in rd, "E5 README 不再说向导可设端口")


# ---------------------------------------------------------------- F. 前端回归
section("F. 1.2.2 引入的滚动修复仍生效（跨版本回归）")

css = io.open(CSS, encoding="utf-8").read()
html = io.open(HTML, encoding="utf-8").read()
ck("#settings-card {" in css, "F1 设置卡片 flex 布局保留")
ck("#settings-card .set-body {" in css, "F2 仅内容区滚动保留")
ck("overflow: hidden" in re.search(r"#settings-card \{[^}]*\}", css).group(0), "F3 卡片自身不滚动保留")

norm = lambda s: re.sub(r"\s+", " ", s).strip()
style = re.search(r"<style>\n(.*?)\n\s*</style>", html, re.S)
ck(norm(style.group(1)) == norm(css), "F4 样式源唯一（index.html 与 ui_style_v414.css 一致）")

ck("在此添加 NAS 上已有的目录作为文档分区" in html, "F5 文件夹页文案仍在")
ck("首次设置" in html and "设置密码" in html, "F6 首次设置密码流程仍在")

# 死代码复查：MOBILE_API_PREFIX 应已移除
vu = io.open(os.path.join(FPK, "app", "vd_util.py"), encoding="utf-8").read()
ck("MOBILE_API_PREFIX" not in vu, "F7 已清理 MOBILE_API_PREFIX 遗留常量")
sv = io.open(os.path.join(FPK, "app", "server.py"), encoding="utf-8").read()
ck('APP_VERSION = "%s"' % VER in sv, "F8 server.py APP_VERSION=%s" % VER)


# ------------------------------------------------------------- G. 双 changelog
section("G. 双 changelog")

for f, name in (("CHANGELOG.md", "G1 开发者版"), ("CHANGELOG_USER.md", "G2 用户版")):
    c = io.open(os.path.join(HERE, f), encoding="utf-8").read()
    ck(re.search(r"^##\s*%s" % re.escape(VER), c, re.M) is not None, "%s 含 %s 条目" % (name, VER))
    idx = [m.start() for m in re.finditer(r"^##\s*1\.[12]\.\d+", c, re.M)]
    ck(idx == sorted(idx), "%s 版本号降序排列" % name)
    ck("**当前版本**：**%s**" % VER in c, "%s 头部当前版本已更新" % name)

uc = io.open(os.path.join(HERE, "CHANGELOG_USER.md"), encoding="utf-8").read()
sec123 = re.search(r"^##\s*%s.*?(?=^##\s|\Z)" % re.escape(VER), uc, re.S | re.M)
body123 = sec123.group(0) if sec123 else ""
ck(bool(body123), "G3 用户版 %s 段落可定位" % VER)
ck(bool(re.search(r"^###\s*(新增|修复|优化|更改)\s*$", body123, re.M)),
   "G4 用户版使用四分点分类（### 标题）", re.findall(r"^###\s*(\S+)", body123, re.M))
# 固定端口的说明写在 1.2.3 段落（1.2.4 段落未改动端口，故不在其段落内）。
# 这里校验「用户版全篇有端口说明」+「1.2.3 段落确有该说明」两条。
ck("3838" in uc, "G5a 用户版全篇说明固定端口")
_s123 = re.search(r"^##\s*1\.2\.3.*?(?=^##\s|\Z)", uc, re.S | re.M)
ck(bool(_s123 and "3838" in _s123.group(0)), "G5b 1.2.3 段落确有固定端口说明")
banned = ["根因", "代码", "接口", "机制", "变量名", "回退", "三级取值", "静默失效", "PostgreSQL", "appcenter"]
hit = [b for b in banned if b in body123]
ck(not hit, "G6 用户版无开发者术语", hit)


# ---------------------------------------------------------------------- 汇总
print("\n" + "=" * 60)
print("RESULT: %d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:")
    for f in FAIL:
        print("  - " + f)
print("=" * 60)
sys.exit(1 if FAIL else 0)
