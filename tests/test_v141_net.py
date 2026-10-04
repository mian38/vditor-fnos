#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""1.4.1 专项测试：IPv6 双栈监听 + 公网 HTTP 访问策略 + 单系统分区 + 渲染模式设置。

只覆盖本轮改动相关逻辑，不执行全量回归。
"""
import os
import re
import sys
import json
import socket
import tempfile
import subprocess

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

sys.path.insert(0, APP)

_pass = 0
_fail = 0


def check(name, cond, extra=""):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  PASS  " + name)
    else:
        _fail += 1
        print("  FAIL  " + name + (("  | " + str(extra)) if extra else ""))


def section(t):
    print("\n== %s ==" % t)


# ============================================================
# 1) IPv6 判定：局域网 IPv6 必须放行，公网 IPv6 必须拒绝
# ============================================================
section("IPv6 网段判定（is_private_ip / ip_version_of）")
import vd_util  # noqa: E402

# 局域网 IPv6：ULA(fd00::/8)、链路本地(fe80::/10, 带 scope)、回环(::1)
check("ULA fd00::1 判为局域网", vd_util.is_private_ip("fd00::1") is True)
check("ULA fc00::1 判为局域网", vd_util.is_private_ip("fc00::1") is True)
check("链路本地 fe80::1 判为局域网", vd_util.is_private_ip("fe80::1") is True)
check("带 scope 的 fe80::1%eth0 判为局域网（1.4.1 修复 scope 剥离）",
      vd_util.is_private_ip("fe80::1%eth0") is True)
check("回环 ::1 判为局域网", vd_util.is_private_ip("::1") is True)
# 公网 IPv6：必须判为非局域网，否则公网访问会被误放行
check("公网 IPv6 240e:3b1::1 判为非局域网",
      vd_util.is_private_ip("240e:3b1:1234::1") is False)
check("公网 IPv6 带 scope 判为非局域网",
      vd_util.is_private_ip("240e:0:1::1%eth0") is False)
# IPv4 行为不回归
check("IPv4 192.168.1.5 判为局域网", vd_util.is_private_ip("192.168.1.5") is True)
check("IPv4 8.8.8.8 判为非局域网", vd_util.is_private_ip("8.8.8.8") is False)
check("IPv4-mapped ::ffff:192.168.1.5 还原为 IPv4 局域网",
      vd_util.is_private_ip("::ffff:192.168.1.5") is True)
# 带方括号的 host:port 形式（URL 里常见）
check("[240e::1]:3838 解析为公网 IPv6",
      vd_util.is_private_ip("[240e::1]:3838") is False)
check("[fd00::1]:3838 解析为局域网 IPv6",
      vd_util.is_private_ip("[fd00::1]:3838") is True)
# 地址族
check("ip_version_of 对公网 IPv6 返回 6", vd_util.ip_version_of("240e::1") == 6)
check("ip_version_of 对 IPv4 返回 4", vd_util.ip_version_of("192.168.1.5") == 4)
check("ip_version_of 对 IPv4-mapped 返回 4", vd_util.ip_version_of("::ffff:1.2.3.4") == 4)
check("ip_version_of 对非法输入返回 0", vd_util.ip_version_of("not-an-ip") == 0)
check("strip_ip_scope 去除 scope 与方括号",
      vd_util.strip_ip_scope("[fe80::1%eth0]:3838") == "fe80::1")

# ============================================================
# 2) 双栈监听：make_server 必须真的监听 IPv6 且接受 IPv4
# ============================================================
section("IPv6 双栈监听（make_server）")
if not socket.has_ipv6:
    print("  SKIP  当前环境无 IPv6 支持")
else:
    tmp = tempfile.mkdtemp(prefix="vd141srv_")
    os.environ["VDITOR_CONFIG"] = tmp
    os.environ["VDITOR_DOC_DIR"] = os.path.join(tmp, "docs")
    os.environ["VDITOR_UPLOAD_DIR"] = os.path.join(tmp, "up")
    os.makedirs(os.environ["VDITOR_DOC_DIR"], exist_ok=True)
    import server as S  # noqa: E402

    check("DualStackServer.address_family == AF_INET6",
          S.DualStackServer.address_family == socket.AF_INET6)
    srv = S.make_server("0.0.0.0", 0, S.Handler)
    try:
        check("make_server 优先返回双栈实例", isinstance(srv, S.DualStackServer))
        host, port = srv.server_address[0], srv.server_address[1]
        check("实际绑定地址为 ::（双栈）", host == "::", host)
        # 真正起服务，分别用 IPv4 / IPv6 回环连一次，验证「同一端口双协议可达」
        import threading
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            import urllib.request
            # IPv4 回环
            ok4 = False
            try:
                ok4 = urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/auth/check" % port, timeout=5).status == 200
            except Exception as e:
                print("       IPv4 访问异常: %s" % e)
            check("IPv4 回环可访问同一端口", ok4)
            # IPv6 回环
            ok6 = False
            try:
                ok6 = urllib.request.urlopen(
                    "http://[::1]:%d/api/auth/check" % port, timeout=5).status == 200
            except Exception as e:
                print("       IPv6 访问异常: %s" % e)
            check("IPv6 回环可访问同一端口（1.4.1 核心）", ok6)
        finally:
            srv.shutdown()
    finally:
        srv.server_close()

# ============================================================
# 3) 公网访问策略：secure_cookie 开启时公网 HTTP 拒绝，关闭时放行
# ============================================================
section("公网 HTTP 访问策略（_https_required_error）")
tmp2 = tempfile.mkdtemp(prefix="vd141http_")
env = dict(os.environ)
env.update({
    "VDITOR_CONFIG": tmp2,
    "VDITOR_DOC_DIR": os.path.join(tmp2, "docs"),
    "VDITOR_UPLOAD_DIR": os.path.join(tmp2, "up"),
    "VDITOR_PORT": "0",
})
os.makedirs(env["VDITOR_DOC_DIR"], exist_ok=True)
os.makedirs(env["VDITOR_UPLOAD_DIR"], exist_ok=True)

probe = r'''
import os, sys, json
sys.path.insert(0, %r)
import server as S

class FakeH:
    """最小 Handler 替身：只提供 _https_required_error / _send_cookie 依赖的属性。"""
    def __init__(self, ip, headers=None):
        self.client_address = (ip, 12345)
        self.headers = headers or {}

def probe():
    out = {}
    for label, ip in [("lan4", "192.168.1.5"), ("lan6_ula", "fd00::1"),
                      ("lan6_ll", "fe80::1%%eth0"), ("pub4", "8.8.8.8"),
                      ("pub6", "240e:3b1::1")]:
        h = FakeH(ip)
        S.SETTINGS["secure_cookie"] = True
        out[label + "_secure_on_reject"] = S.Handler._https_required_error(h) is not None
        out[label + "_lan"] = S.is_private_ip(S.client_ip(h))
        S.SETTINGS["secure_cookie"] = False
        out[label + "_secure_off_reject"] = S.Handler._https_required_error(h) is not None
    print("PROBE_JSON:" + json.dumps(out))
probe()
''' % (APP,)
probe_path = os.path.join(tmp2, "_probe.py")
with open(probe_path, "w", encoding="utf-8") as f:
    f.write(probe)
r = subprocess.run([PY, probe_path], env=env, capture_output=True, text=True)
m = re.search(r"PROBE_JSON:(\{.*\})", r.stdout)
if not m:
    check("策略探针执行成功", False, (r.stdout[-500:], r.stderr[-500:]))
else:
    d = json.loads(m.group(1))
    # secure_cookie 开启：公网拒绝、局域网放行
    check("secure 开启：局域网 IPv4 放行", d["lan4_secure_on_reject"] is False)
    check("secure 开启：局域网 IPv6(ULA) 放行", d["lan6_ula_secure_on_reject"] is False)
    check("secure 开启：局域网 IPv6(链路本地) 放行", d["lan6_ll_secure_on_reject"] is False)
    check("secure 开启：公网 IPv4 拒绝", d["pub4_secure_on_reject"] is True)
    check("secure 开启：公网 IPv6 拒绝（1.4.1 核心）", d["pub6_secure_on_reject"] is True)
    # secure_cookie 关闭：一律放行
    check("secure 关闭：公网 IPv4 放行", d["pub4_secure_off_reject"] is False)
    check("secure 关闭：公网 IPv6 放行（1.4.1 核心）", d["pub6_secure_off_reject"] is False)
    check("secure 关闭：局域网 IPv6 仍放行", d["lan6_ula_secure_off_reject"] is False)
    # 局域网判定本身
    check("公网 IPv6 不被判为局域网", d["pub6_lan"] is False)
    check("局域网 IPv6(ULA) 被判为局域网", d["lan6_ula_lan"] is True)
    check("局域网 IPv6(链路本地) 被判为局域网", d["lan6_ll_lan"] is True)

# ============================================================
# 4) 单系统分区
# ============================================================
section("单系统分区（build_doc_roots）")
sr = open(os.path.join(APP, "server.py"), encoding="utf-8").read()
check("定义唯一系统分区常量 /vol1/@appshare/vditor-docs",
      'SYSTEM_SHARE_DIR = "/vol1/@appshare/vditor-docs"' in sr)
check("build_doc_roots 不再自动并入 collect_share_paths()",
      not re.search(r"for name, path in collect_share_paths\(\)", sr))
check("系统分区仅在已挂载（isdir）时才加入", "if os.path.isdir(SYSTEM_SHARE_DIR)" in sr)
check("VDITOR_DOC_DIR 取代系统分区但不覆盖用户自建分区",
      "roots = [(os.environ.get(\"VDITOR_DOC_NAME\", \"我的文档\"), dd)] + managed" in sr)

# 场景验证
scen = r'''
import os, sys, json, tempfile
sys.path.insert(0, %r)
tmp = tempfile.mkdtemp()
d1 = os.path.join(tmp, "d1"); os.makedirs(d1)
d2 = os.path.join(tmp, "d2"); os.makedirs(d2)
d3 = os.path.join(tmp, "d3"); os.makedirs(d3)
out = {}
def run(**e):
    for k in ("VDITOR_DOC_DIR", "VDITOR_DOC_DIRS", "VDITOR_DOC_NAME"):
        os.environ.pop(k, None)
    os.environ["VDITOR_CONFIG"] = tmp
    os.environ.update(e)
    import server as S
    import importlib; importlib.reload(S)
    return [(r["name"], r["path"]) for r in S.DOC_ROOTS]
out["with_doc_dir"] = run(VDITOR_DOC_DIR=d1, VDITOR_DOC_NAME="我的文档")
out["with_doc_dirs"] = run(VDITOR_DOC_DIRS="甲::" + d2 + ",乙::" + d3)
out["no_override"] = run()
print("SCEN_JSON:" + json.dumps(out))
''' % (APP,)
scen_path = os.path.join(tmp2, "_scen.py")
with open(scen_path, "w", encoding="utf-8") as f:
    f.write(scen)
r = subprocess.run([PY, scen_path], env=env, capture_output=True, text=True)
m = re.search(r"SCEN_JSON:(\{.*\})", r.stdout)
if not m:
    check("分区场景执行成功", False, (r.stdout[-400:], r.stderr[-400:]))
else:
    d = json.loads(m.group(1))
    check("显式 VDITOR_DOC_DIR → 仅该目录一个分区",
          len(d["with_doc_dir"]) == 1 and d["with_doc_dir"][0][1].endswith("d1"),
          d["with_doc_dir"])
    check("显式 VDITOR_DOC_DIRS → 两个指定分区",
          [n for n, _ in d["with_doc_dirs"]] == ["甲", "乙"], d["with_doc_dirs"])
    # 无 override 且系统分区未挂载（Windows 下 /vol1/... 不存在）→ 回退到私有 docs
    check("无 override 且系统分区未挂载 → 回退默认目录",
          len(d["no_override"]) == 1, d["no_override"])

# ============================================================
# 5) 渲染模式设置（后端枚举校验）
# ============================================================
section("渲染模式设置（render_mode）")
check("DEFAULT_SETTINGS 含 render_mode 默认 auto",
      '"render_mode": "auto"' in sr)
check("定义合法取值 RENDER_MODES", 'RENDER_MODES = ("auto", "rich", "raw")' in sr)
check("load_settings 对非法值回落 auto",
      re.search(r'if s\.get\("render_mode"\) not in RENDER_MODES:\s*\n\s*s\["render_mode"\] = "auto"', sr) is not None)
check("_apply_settings 校验 render_mode 枚举",
      "render_mode 必须为 auto / rich / raw 之一" in sr)
check("设置导出包含 render_mode", '"render_mode", "versioning"' in sr)

# 实际接口校验
api = r'''
import os, sys, json
sys.path.insert(0, %r)
import server as S
h = S.Handler.__new__(S.Handler)
out = {}
for v in ("auto", "rich", "raw"):
    S.SETTINGS["render_mode"] = "auto"
    ch, errs = S.Handler._apply_settings(h, {"render_mode": v})
    out[v] = [S.SETTINGS["render_mode"], errs]
S.SETTINGS["render_mode"] = "auto"
ch, errs = S.Handler._apply_settings(h, {"render_mode": "bogus"})
out["bogus"] = [S.SETTINGS["render_mode"], errs]
print("API_JSON:" + json.dumps(out, ensure_ascii=False))
''' % (APP,)
api_path = os.path.join(tmp2, "_api.py")
with open(api_path, "w", encoding="utf-8") as f:
    f.write(api)
r = subprocess.run([PY, api_path], env=env, capture_output=True, text=True)
m = re.search(r"API_JSON:(\{.*\})", r.stdout)
if not m:
    check("render_mode 接口校验执行成功", False, (r.stdout[-400:], r.stderr[-400:]))
else:
    d = json.loads(m.group(1))
    for v in ("auto", "rich", "raw"):
        check("render_mode 接受合法值 %s" % v, d[v][0] == v and not d[v][1], d[v])
    check("render_mode 拒绝非法值并保持 auto",
          d["bogus"][0] == "auto" and d["bogus"][1], d["bogus"])

# ============================================================
# 6) 风险文案与免责（前端 / 安装引导 / manifest）
# ============================================================
section("风险提示与免责文案")
idx = open(os.path.join(APP, "index.html"), encoding="utf-8").read()
wiz = open(os.path.join(BASE, "vditor-fpk", "wizard", "install"), encoding="utf-8").read()
mani = open(os.path.join(BASE, "vditor-fpk", "manifest"), encoding="utf-8").read()

# 二次确认按钮：取消=蓝、确认=白
check("确认框 CSS：取消为主色蓝",
      re.search(r"#confirm-mask #confirm-cancel\s*\{[^}]*background:\s*var\(--c-brand\)", idx) is not None)
check("确认框 CSS：确认为白底",
      re.search(r"#confirm-mask #confirm-ok\s*\{[^}]*background:\s*#fff", idx) is not None)
check("确认框：取消按钮排在确认之前（默认视线落点）",
      idx.index('id="confirm-cancel"') < idx.index('id="confirm-ok"'))
check("确认框正文支持多段落换行", "#confirm-msg { white-space: pre-line" in idx)
check("两个安全开关使用各自风险文案（attachSecurityConfirm 增加第 3 参）",
      "function attachSecurityConfirm(id, name, risk)" in idx)
check("secure_cookie 风险文案含「明文」", "均以明文在网络上传输" in idx)
check("secure_cookie 风险文案含 IPv6 公网场景", "公网 HTTP 连接（包括 IPv4 / IPv6）" in idx)

# 设置页说明
check("设置页：说明公网 HTTP 被拒绝（secure 开启）",
      "将被拒绝访问" in idx and "避免 HTTP 明文在公网中被抓包窃取" in idx)
check("设置页：说明局域网 HTTP 不受影响", "可正常访问，不受影响" in idx)
check("设置页：说明纯 HTTP 不提供 HTTPS", "不提供 HTTPS" in idx and "无法使用" in idx)
check("设置页：说明 HTTPS 须经反向代理", "反向代理 / 内网穿透" in idx)
check("设置页：含 IPv6 访问说明与方括号写法", "http://[局域网IPv6]:3838" in idx)
check("设置页：含风险自负免责", "风险自负" in idx and "数据泄露" in idx and "承担责任" in idx)
check("设置页：说明不提供 HTTPS 与 Cookie Secure 无关",
      "这与是否开启 Cookie Secure 无关" in idx)
# 1.4.2：secure cookie 文案按需求原文重写 + 临时态迁移 + 状态栏合并
check("1.4.2 secure cookie 说明：公网拒绝 / 局域网不受影响",
      "将被拒绝访问" in idx and "局域网 HTTP 连接" in idx and "不受影响" in idx)
check("1.4.2 secure cookie 风险段为独立 ⚠️ 风险自负",
      re.search(r'sub sub-warn"><b>⚠️ 风险自负</b>：关闭「强制 Cookie Secure 标记」后，若使用 HTTP 连接访问', idx) is not None)
check("1.4.2 二次确认含问句「确定要关闭「强制 Cookie Secure 标记」吗？」",
      "确定要关闭「强制 Cookie Secure 标记」吗？" in idx)
check("1.4.2 二次确认含「建议保持开启（取消本次操作）」",
      "建议保持开启（取消本次操作）" in idx)
check("1.4.2 二次确认含「如你不理解此处的说明，请保持开启」",
      "如你不理解此处的说明，请保持开启" in idx)
check("1.4.2 二次确认说明与 https 直连无关",
      "是否开启本选项都不影响「无法用 https://IP:3838 直连访问」" in idx)
# 1.4.2：临时态从设置页迁移至顶栏按钮
check("1.4.2 已删除设置页临时态按钮", "btn-once" not in idx)
check("1.4.2 顶栏按钮初始为 hidden（仅大文档出现）",
      re.search(r'id="btn-raw-mode"[^>]*\bhidden\b', idx) is not None)
check("1.4.2 updateRawModeBtn 按文档大小控制显隐",
      "b.hidden = !(currentPath && len > RAW_AUTO_CHARS);" in idx)
check("1.4.2 顶栏按钮切换即写入临时态 renderModeOnce",
      re.search(r"function toggleRawMode\(\) \{\s*if \(rawMode\) \{\s*renderModeOnce = 'rich';", idx) is not None)
check("1.4.2 已移除 applyRenderModeOnce / clearRenderModeOnce",
      "applyRenderModeOnce" not in idx and "clearRenderModeOnce" not in idx)
# 1.4.2：状态栏监听地址合并为单栏
check("1.4.2 监听地址仅出现一次（已合并）", idx.count("kv(dl, '监听地址'") == 1)
check("1.4.2 监听地址显示 bindHost 与双栈说明",
      "(a.bindHost || a.host || '::')" in idx and "IPv4 / IPv6 双栈" in idx)
check("1.4.2 /api/status 提供 bindHost 与 dualStack",
      '"bindHost": "::" if HOST in ("", "0.0.0.0") else HOST' in sr and '"dualStack":' in sr)
# 1.4.2：使用指南集中修订
check("1.4.2 使用指南新增「纯文本模式与大文档」章节", "纯文本模式与大文档" in idx)
check("1.4.2 使用指南说明临时态只在本次会话有效", "只在本次会话有效" in idx)
check("1.4.2 使用指南说明单系统分区路径", "/vol1/@appshare/vditor-docs" in idx)
check("1.4.2 使用指南修正失效选项卡名（版本与自动保存 → 文件）",
      "设置 → 版本与自动保存" not in idx and "在<b>「设置 → 文件」</b>中配置" in idx)
check("1.4.2 使用指南补充 >5MB 不生成历史版本", "超过 5MB 的文档不再生成历史版本快照" in idx)
check("1.4.2 使用指南补充纯文本不支持导出 HTML", "纯文本模式下不支持「导出 HTML」" in idx)
check("1.4.2 使用指南说明二次确认按钮配色", "「取消」是醒目的蓝色并排在前面" in idx)
check("1.4.2 使用指南章节序号连续（一~九）",
      all(("%s、" % c) in idx for c in "一二三四五六七八九"))

# 安装引导
check("安装引导：说明默认禁止公网访问", "默认禁止" in wiz)
check("安装引导：说明关闭 secure cookie 的后果", "以明文传输" in wiz and "强烈不建议这么做" in wiz)
check("安装引导：说明 IPv6 与方括号", "http://[局域网IPv6]:3838" in wiz)
check("安装引导：说明系统分区路径", "/vol1/@appshare/vditor-docs" in wiz)
check("安装引导：说明旧分区不迁移", "不会被自动迁移" in wiz)

# manifest
check("manifest desc：说明支持 IPv4/IPv6 与方括号", "http://[局域网IPv6]:3838" in mani)
check("manifest desc：说明默认禁止公网访问", "默认禁止" in mani)
check("manifest desc：含明文风险与不建议", "以明文传输" in mani and "强烈不建议这么做" in mani)

# 后端启动横幅
check("启动横幅提示局域网 IPv4/IPv6 均可访问", "局域网可直接访问（IPv4 / IPv6 均可）" in sr)
check("启动横幅按 secure_cookie 状态给出不同风险提示",
      "登录密码与文档内容均为明文传输" in sr and "公网 HTTP 访问会被拒绝" in sr)

# ============================================================
# 1.4.3：重大缺陷回归（初始化中断）——静态守卫
section("1.4.3 回归守卫：Vditor 就绪判断")
idx14 = idx
check("存在 vditorReady 就绪标志", "let vditorReady = false;" in idx14)
check("after() 内置 vditorReady = true", "vditorReady = true;" in idx14)
check("destroyVditor 置 vditorReady = false", "vditorReady = false;" in idx14)
check("after() 先置就绪再 setContent（避免内容被误丢）",
      re.search(r"vditorReady = true;\s*\n\s*setContent\(initial\);", idx14) is not None)
check("getContent 未就绪时返回空串而非抛错",
      re.search(r"if \(!vditor \|\| !vditorReady\) return '';", idx14) is not None)
check("getContent 带 try-catch 兜底",
      re.search(r"try \{ return vditor\.getValue\(\) \|\| ''; \} catch \(e\) \{ return ''; \}", idx14) is not None)
check("setContent 未就绪时静默跳过", "if (!vditor || !vditorReady) return;" in idx14)
check("updateRawModeBtn 整体 try-catch 兜底",
      re.search(r"function updateRawModeBtn\(\) \{[\s\S]*?try \{[\s\S]*?\} catch \(e\) \{", idx14) is not None)
check("updateRawModeBtn 仅在就绪或纯文本时取长度",
      "else if (vditorReady && vditor) len = (getContent() || '').length;" in idx14)
check("exitRawMode 不再直调 vditor.setValue（改走 setContent 守卫）",
      re.search(r"function exitRawMode\(\)[\s\S]*?if \(vditor\) \{ pendingRichText = text; setContent\(text\); \}",
                idx14) is not None)
check("端到端回归测试已内置（探针 14）",
      "1.4.3 端到端：initEditorAndFiles 完整绑定" in
      open(os.path.join(BASE, "tests", "test_rawmode_v14.js"), encoding="utf-8").read())

print("\n结果: %d 通过, %d 失败" % (_pass, _fail))
sys.exit(0 if _fail == 0 else 1)
