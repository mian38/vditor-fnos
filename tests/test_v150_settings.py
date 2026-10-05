#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""1.5.0 专项测试：设置面板文案重组 / 自动保存总开关 / 手动保存快照 / 渲染阈值 1MB /
分区折叠 / 监听状态如实显示 / 对话框交互。

只覆盖本轮改动相关逻辑，不执行全量回归。
"""
import os
import re
import sys
import json
import socket
import shutil
import tempfile
import subprocess
import time
import urllib.request
import urllib.parse
import urllib.error

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
        print("  PASS  %s" % name)
    else:
        _fail += 1
        print("  FAIL  %s%s" % (name, ("  → " + str(extra)) if extra else ""))


def read(p):
    with open(os.path.join(BASE, p), encoding="utf-8") as f:
        return f.read()


idx = read(os.path.join("vditor-fpk", "app", "index.html"))
sr = read(os.path.join("vditor-fpk", "app", "server.py"))
util = read(os.path.join("vditor-fpk", "app", "vd_util.py"))
mani = read(os.path.join("vditor-fpk", "manifest"))

# 取「设置 → 文件」页片段，避免与其它选项卡的同名词互相干扰
FILE_SEC = idx[idx.index('id="pg-file"'):idx.index('id="pg-security"')]
# 取「设置 → 安全」页片段
SEC_SEC = idx[idx.index('id="pg-security"'):idx.index('id="pg-appearance"')]

print("\n[1] #1 设置文案（渲染模式 + 强制 Cookie Secure）")
check("渲染模式标题去掉版本号后缀", "<h3>渲染模式</h3>" in FILE_SEC)
check("渲染模式说明含浏览器性能强相关提示",
      "与使用的设备和浏览器性能强相关" in FILE_SEC)
check("渲染模式说明含性能较弱设备的建议",
      "建议优先选用「自动」或「始终纯文本」模式" in FILE_SEC)
check("渲染模式说明含顶栏切换按钮指引",
      "该按钮仅在打开大文档时出现，切换只在本次会话有效" in FILE_SEC)
check("渲染模式含「⚠️ 风险自负」风险段", "⚠️ 风险自负" in FILE_SEC)
check("风险段含数据损失与损坏免责",
      "数据损失与损坏承担责任" in FILE_SEC)
check("风险段含卡顿后的处置指引",
      "使用顶栏的「纯文本」切换按钮切换回纯文本模式" in FILE_SEC)
check("旧版「关于「始终富文本」」提示已移除", "关于「始终富文本」" not in FILE_SEC)

check("secure cookie 风险段保留「风险自负」", "风险自负" in SEC_SEC)
check("secure cookie 风险段含截获登录密码与文档内容",
      "登录密码与全部文档内容" in SEC_SEC)
check("secure cookie 风险段含「请务必确认所处网络环境可信」",
      "请务必确认所处网络环境可信" in SEC_SEC)
check("secure cookie 风险段含数据泄露免责（定稿措辞）",
      "不对由此产生的任何数据泄露或损失不承担责任" in SEC_SEC)
check("旧版「优先采用反向代理 + HTTPS」措辞已移除",
      "并优先采用<b>反向代理 / 内网穿透 + HTTPS</b> 的方式" not in SEC_SEC)
check("设置 → 安全 已删除冗余的 IPv6 访问说明段",
      "同时监听 IPv4 与 IPv6" not in SEC_SEC and "局域网IPv6" not in SEC_SEC)
check("IPv6 访问说明仍保留在「使用指南」中",
      "同时监听 IPv4 与 IPv6" in idx)

print("\n[2] #3 设置面板重组（自动保存开关 / 间隔 / 历史版本 / 版本数）")
check("存在「启用自动保存」开关", 'id="set-autosave-enabled"' in FILE_SEC)
check("自动保存开关文案为「启用自动保存」", "启用自动保存" in FILE_SEC)
check("自动保存说明保留手动保存途径", "Ctrl / Cmd + S" in FILE_SEC)
check("自动保存说明明确未保存提醒仍保留", "仍会照常提醒" in FILE_SEC)
check("自动保存间隔位于开关之后（开关在前）",
      FILE_SEC.index('id="set-autosave-enabled"') < FILE_SEC.index('id="set-autosave"'))
check("自动保存间隔位于历史版本开关之前",
      FILE_SEC.index('id="set-autosave"') < FILE_SEC.index('id="set-versioning"'))
check("历史版本开关已去掉括号说明", "启用文件历史版本（每次手动/自动保存均生成可回溯版本）" not in FILE_SEC)
check("历史版本说明含「自动保存不生成历史版本」",
      "自动保存不生成历史版本" in FILE_SEC)
check("历史版本说明含「手动保存仍正常生成」",
      "但手动保存仍正常生成历史版本" in FILE_SEC)
check("历史版本说明用「影响性能」而非其它措辞",
      "为避免高频自动保存<b>影响性能</b>" in FILE_SEC)
check("最大版本数控件仍在", 'id="set-max-versions"' in FILE_SEC)
check("最大版本数说明含默认值 50", "默认值为 50" in FILE_SEC)
check("最大版本数说明含独立计数", "每个文档各自独立计数" in FILE_SEC)

print("\n[3] #2 手动保存与自动保存的历史版本区分（服务端）")
check("DEFAULT_SETTINGS 含 autosave_enabled", '"autosave_enabled": True' in sr)
check("load_settings 归一化 autosave_enabled（缺省开启）",
      'bool(s.get("autosave_enabled", True))' in sr)
check("save_file_version 增加 manual 参数", "def save_file_version(root_path, rel, content_bytes, manual=True)" in sr)
check("仅自动保存时按体积跳过快照", "if not manual and len(content_bytes) > VERSION_SKIP_BYTES:" in sr)
check("/api/save 读取 manual 字段", 'manual = bool(data.get("manual", True))' in sr)
check("/api/save 手动保存时不再看体积", "if manual or os.path.getsize(fp) <= VERSION_SKIP_BYTES:" in sr)
check("/api/save 把 manual 传给 save_file_version", "save_file_version(root[\"path\"], rel_stored, prev, manual=manual)" in sr)
check("前端手动保存带 manual:true", "manual: !silent" in idx)
check("前端自动保存不带 manual（silent 时为 false）", "function saveToNas(silent)" in idx)
check("恢复版本时仍按手动处理（不受体积限制）",
      sr.count("save_file_version(root[\"path\"], rel, cur)") == 1)

print("\n[4] #3① 自动保存总开关（前端行为）")
check("声明 autosaveEnabled 变量", "let autosaveEnabled = true;" in idx)
check("loadSettings 读取 autosave_enabled", "autosaveEnabled = SETTINGS_UI.autosave_enabled !== false;" in idx)
check("saveSettings 回读 autosave_enabled", "autosaveEnabled = SETTINGS_UI.autosave_enabled !== false;" in idx)
check("saveSettings 提交 autosave_enabled", "autosave_enabled: document.getElementById('set-autosave-enabled').checked," in idx)
check("定时器受 autosaveEnabled 约束",
      "if (autosaveEnabled && currentRoot && currentPath && dirty) saveToNas(true);" in idx)
check("关闭时把间隔输入框置灰", "inp.disabled = !on;" in idx)
check("间隔输入框绑定 change 事件", "asBox.addEventListener('change', syncAutosaveIntervalEnabled);" in idx)
check("beforeunload 提醒不受开关影响（仍只看 dirty）",
      "window.addEventListener('beforeunload', (e) => {\n            if (currentRoot && currentPath && dirty)"
      in idx.replace("\r\n", "\n"))
check("/api/status 上报 autosaveEnabled", '"autosaveEnabled": bool(SETTINGS.get("autosave_enabled", True))' in sr)
check("应用状态新增「自动保存」行", "kv(dl, '自动保存'," in idx)
check("自动保存关闭时间隔显示为「—」", "—（自动保存未开启）" in idx)

print("\n[5] #4 渲染阈值 500KB（字节口径）+ 判定口径统一")
# 1.5.0 二次调整：阈值口径由「字符数」改为「UTF-8 字节数」，阈值下调至 500KB。
# 起因是用户指出「1MB 的 md 文件并不一定约 100 万字符」——中文一字 3 字节，
# 按字符判定会严重高估体积，故符号与判定入参一并改为字节。
check("阈值改为字节口径 RAW_AUTO_BYTES = 500KB", "const RAW_AUTO_BYTES = 500 * 1024;" in idx)
check("提供 byteLength() 取真实 UTF-8 字节数", "function byteLength(s)" in idx)
check("使用 TextEncoder 而非乘 3 估算", "new TextEncoder().encode(s).length" in idx)
check("三态说明文案改为 500KB 且不再提字符数",
      "超过约 500KB 的文档自动使用纯文本模式" in idx)
# 「100 万字符」只允许出现在**代码注释**里（那里正是在解释为何弃用字符口径），
# 绝不能出现在任何**面向用户**的文案中。逐条检查可见文案即可。
_user_facing = "\n".join(
    ln for ln in idx.splitlines() if not ln.strip().startswith("//"))
check("用户可见文案中不再出现「100 万字符」", "100 万字符" not in _user_facing)
check("使用指南同步为 500KB", "打开体积超过约 <b>500KB</b> 的文档" in idx)
check("引入 docBaseBytes 统一口径", "let docBaseBytes = 0;" in idx)
check("提供 isBigDoc() 统一判据", "const isBigDoc = () => docBaseBytes > RAW_AUTO_BYTES;" in idx)
check("openFile 写入 docBaseBytes（字节）", "docBaseBytes = bytes;" in idx)
check("decideRenderMode 使用同一阈值", "return (bytes > RAW_AUTO_BYTES) ? 'raw' : 'rich';" in idx)
check("按钮显隐改用 isBigDoc()", "b.hidden = !(currentPath && isBigDoc());" in idx)
check("按钮显隐不再取实时内容长度",
      "else if (vditorReady && vditor) len = (getContent() || '').length;" not in idx)
check("旧字符数符号已彻底移除（防两套阈值并存打架）",
      "RAW_AUTO_CHARS" not in idx and "docBaseLen" not in idx)
check("切回富文本的二次确认改用 isBigDoc()", "if (isBigDoc()) {" in idx)
check("enterRawMode 销毁 Vditor 改用 isBigDoc()", "if (isBigDoc() && vditor) {" in idx)

print("\n[6] #5 分区折叠")
check("折叠状态用 localStorage 持久化", "vditor-folded-roots" in idx)
check("折叠态写入 class", "block.classList.add('collapsed')" in idx)
check("折叠时隐藏文件列表", ".root-block.collapsed > ul" in idx)
check("分区头可点击", "head.className = 'root-head clickable';" in idx)
check("新建按钮阻止冒泡（不误触折叠）", "e.stopPropagation(); newFile(r.id, r.name);" in idx)
check("折叠状态持久化函数存在", "function saveFolded(list)" in idx)
check("打开文件时自动展开所在分区", "act.parentNode.parentNode.classList.contains('collapsed')" in idx)

print("\n[7] #6 监听状态如实显示 + IP 归一化")
check("make_server 写入实测监听结果",
      'ACTUAL_BIND = {"host": "::", "dualStack": True' in sr)
check("回退分支写入纯 IPv4", 'ACTUAL_BIND = {"host": "0.0.0.0", "dualStack": False' in sr)
check("声明 ACTUAL_BIND 默认值", 'ACTUAL_BIND = {"host": None, "dualStack": None, "family": None}' in sr)
check("/api/status 读取 ACTUAL_BIND 而非按 HOST 推断",
      '"bindHost": ACTUAL_BIND["host"]' in sr)
check("旧版按 HOST 推断的写法已移除",
      '"bindHost": "::" if HOST in ("", "0.0.0.0") else HOST' not in sr)
check("新增 bindFamily 字段", '"bindFamily": ACTUAL_BIND["family"]' in sr)
check("前端对 dualStack=null 不虚报", "dual === true" in idx and "dual === false" in idx)
check("vd_util 提供 normalize_client_ip", "def normalize_client_ip(ip):" in util)
check("client_ip 应用归一化", "direct = normalize_client_ip(handler.client_address[0])" in sr)
check("XFF 段也归一化", "first = normalize_client_ip(xff.split(\",\")[0].strip())" in sr)
check("normalize_client_ip 保留原生 IPv6（不映射）",
      "return str(addr)" in util)

print("\n[8] #7 / #8 对话框交互")
check("会话弹窗已移除「稍后处理」", 'id="btn-session-close"' not in idx)
check("会话弹窗事件已同步清理", "getElementById('btn-session-close')" not in idx)
check("会话弹窗保留「刷新页面并重新登录」", 'id="btn-session-reload"' in idx)
check("确认框：确认在左、取消在右",
      idx.index('id="confirm-ok"') < idx.index('id="confirm-cancel"'))
check("取消仍为主色蓝（劝退设计不变）",
      re.search(r"#confirm-mask #confirm-cancel\s*\{[^}]*background:\s*var\(--c-brand\)", idx) is not None)
check("使用指南同步按钮位置描述", "「取消」是醒目的蓝色并排在右边" in idx)

print("\n[9] manifest changelog")
check("changelog 以 1.5.0 开头", "changelog=1.5.0：" in mani)
check("changelog 记录手动保存可回溯", "手动保存仍正常生成" in mani)
check("changelog 记录阈值上调", "100 万字符" in mani)
check("changelog 记录监听如实显示", "实测" in mani)
check("changelog 记录分区折叠", "分区可折叠" in mani)
check("changelog 保留 1.4.3 及更早条目", "1.4.3：修复 1.4.2 引入的重大缺陷" in mani)

# ---------------------------------------------------------------------------
# 运行时行为：归一化与判定逻辑（纯函数级，不拉起服务）
# ---------------------------------------------------------------------------
print("\n[10] 运行时行为（纯函数级）")
import vd_util  # noqa: E402

check("normalize_client_ip 还原 IPv4-mapped",
      vd_util.normalize_client_ip("::ffff:192.168.1.5") == "192.168.1.5")
check("normalize_client_ip 保留原生 IPv6",
      vd_util.normalize_client_ip("240e:37c:1b06:700:4899:b437:ca33:a4c2")
      == "240e:37c:1b06:700:4899:b437:ca33:a4c2")
check("normalize_client_ip 剥离 zone 后缀",
      vd_util.normalize_client_ip("fe80::1%eth0") == "fe80::1")
check("normalize_client_ip 去方括号",
      vd_util.normalize_client_ip("[::1]") == "::1")
check("normalize_client_ip 原样返回 IPv4",
      vd_util.normalize_client_ip("192.168.1.5") == "192.168.1.5")
check("normalize_client_ip 对空值安全", vd_util.normalize_client_ip("") == "")
check("归一化后仍判为局域网（IPv4-mapped）",
      vd_util.is_private_ip("::ffff:192.168.1.5") is True)
check("归一化后地址族仍为 IPv4",
      vd_util.ip_version_of("::ffff:192.168.1.5") == 4)

# 升级场景：1.4.x 写下的 settings.json 不含 autosave_enabled，加载后必须为开启
_cfgdir = tempfile.mkdtemp(prefix="vditor150cfg_")
try:
    with open(os.path.join(_cfgdir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"autosave_interval": 90, "versioning": True}, f)
    import importlib
    import server as _srv
    _orig = _srv.SETTINGS_FILE
    _srv.SETTINGS_FILE = os.path.join(_cfgdir, "settings.json")
    try:
        _loaded = _srv.load_settings()
    finally:
        _srv.SETTINGS_FILE = _orig
    check("1.4.x 老配置（无 autosave_enabled 键）加载后为开启",
          _loaded.get("autosave_enabled") is True, _loaded.get("autosave_enabled"))
    check("老配置的其它键仍正确读入", _loaded.get("autosave_interval") == 90,
          _loaded.get("autosave_interval"))
    # 脏值不应把功能关掉
    with open(os.path.join(_cfgdir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"autosave_enabled": "false"}, f)
    _srv.SETTINGS_FILE = os.path.join(_cfgdir, "settings.json")
    try:
        _loaded2 = _srv.load_settings()
    finally:
        _srv.SETTINGS_FILE = _orig
    check("字符串脏值 \"false\" 视为开启（bool 非空即真，不误关功能）",
          _loaded2.get("autosave_enabled") is True, _loaded2.get("autosave_enabled"))
finally:
    shutil.rmtree(_cfgdir, ignore_errors=True)

# ---------------------------------------------------------------------------
# 端到端：自动保存开关是否真的控制保存行为
# ---------------------------------------------------------------------------
print("\n[11] 端到端：自动保存开关的落盘往返")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _req(base, method, path, body=None, cookie=None, timeout=10):
    url = base + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    rq = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), resp.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8")), e.headers.get("Set-Cookie", "")
        except Exception:
            return e.code, {}, ""


tmp = tempfile.mkdtemp(prefix="vditor150_")
docs = os.path.join(tmp, "docs")
ups = os.path.join(tmp, "up")
os.makedirs(docs)
os.makedirs(ups)
port = _free_port()
env = dict(os.environ)
env.update({
    "VDITOR_HOST": "127.0.0.1",
    "VDITOR_PORT": str(port),
    "VDITOR_CONFIG": tmp,
    "VDITOR_DOC_DIR": docs,
    "VDITOR_DOC_NAME": "t150",
    "VDITOR_UPLOAD_DIR": ups,
})
proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    base = "http://127.0.0.1:%d" % port
    ready = False
    for _ in range(80):
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(base + "/index.html", timeout=1):
                ready = True
                break
        except Exception:
            time.sleep(0.15)
    check("服务成功启动", ready)

    if ready:
        st, d, sc = _req(base, "POST", "/api/setup", {"password": "test1234"})
        cookie = ""
        m = re.search(r"vditor_sid=[^;]+", sc or "")
        if m:
            cookie = m.group(0)
        if not cookie:
            st, d, sc = _req(base, "POST", "/api/login", {"password": "test1234"})
            m = re.search(r"vditor_sid=[^;]+", sc or "")
            if m:
                cookie = m.group(0)
        check("首次设置密码并取得会话", bool(cookie), "st=%s" % st)

        st, d, _ = _req(base, "GET", "/api/settings", cookie=cookie)
        check("设置默认 autosave_enabled 为 true",
              st == 200 and d.get("settings", {}).get("autosave_enabled") is True,
              d.get("settings", {}).get("autosave_enabled"))

        st, d, _ = _req(base, "POST", "/api/settings",
                        {"autosave_enabled": False, "autosave_interval": 30}, cookie=cookie)
        check("可保存 autosave_enabled=false",
              st == 200 and d.get("settings", {}).get("autosave_enabled") is False,
              d.get("settings", {}).get("autosave_enabled"))

        st, d, _ = _req(base, "GET", "/api/settings", cookie=cookie)
        check("重新读取仍为 false（已落盘）",
              d.get("settings", {}).get("autosave_enabled") is False)

        st, d, _ = _req(base, "GET", "/api/status", cookie=cookie)
        check("状态接口如实上报 autosaveEnabled=false",
              d.get("security", {}).get("autosaveEnabled") is False,
              d.get("security", {}).get("autosaveEnabled"))
        # 注：本测试以 VDITOR_HOST=127.0.0.1 启动。DualStackServer 的 address_family
        # 固定为 AF_INET6，绑 IPv4 字面量会失败并回退到纯 IPv4 的 0.0.0.0，
        # 故此处期望 dualStack=False——这正是 1.5.0 要「如实显示」的那条路径：
        # 1.4.2 会按 HOST 推断而虚报「双栈」，1.5.0 改为上报实测结果。
        st, d, _ = _req(base, "GET", "/api/status", cookie=cookie)
        check("状态接口如实上报实测监听地址（回退纯 IPv4 时不再虚报双栈）",
              d.get("app", {}).get("bindHost") == "0.0.0.0"
              and d.get("app", {}).get("dualStack") is False,
              "%s / %s" % (d.get("app", {}).get("bindHost"), d.get("app", {}).get("dualStack")))
        check("状态接口提供 bindFamily 供界面显示",
              d.get("app", {}).get("bindFamily") in ("IPv4", "IPv6（双栈）"),
              d.get("app", {}).get("bindFamily"))

        # 老配置兼容：不含 autosave_enabled 键的请求不应改动该设置（保持当前值），
        # 说明服务端按「键存在才改」处理，前端漏传该字段时不会误重置为开启。
        st, d, _ = _req(base, "POST", "/api/settings", {"autosave_interval": 45}, cookie=cookie)
        check("请求不含该键时不改动 autosave_enabled（保持 false）",
              st == 200 and d.get("settings", {}).get("autosave_enabled") is False,
              d.get("settings", {}).get("autosave_enabled"))
        # 显式改回开启
        st, d, _ = _req(base, "POST", "/api/settings", {"autosave_enabled": True}, cookie=cookie)
        check("可显式改回 autosave_enabled=true",
              d.get("settings", {}).get("autosave_enabled") is True,
              d.get("settings", {}).get("autosave_enabled"))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

# =====================================================================
# 实机反馈后的追加修复（并入 1.5.0）
# =====================================================================

print("\n[11] viaProxy 误报：直连被判成经代理")
# 根因：_build_status() 的 direct 未走 normalize_client_ip()，而 c_ip 走了。
# 双栈下 IPv4 客户端 address 是 '::ffff:x'，与归一化后的 'x' 永不相等 → via_proxy 恒真。
check("direct 已归一化（与 client_ip 同一取值口径）",
      "direct = normalize_client_ip(self.client_address[0])" in sr)
check("直连取址不再裸用 client_address[0]",
      "direct = self.client_address[0]" not in sr)
check("保留 via_proxy 比较（归一化后才可靠）", "via_proxy = c_ip != direct" in sr)

print("\n[12] 备份导出：后台任务 + 进度反馈")
check("模块级备份任务状态", "_BACKUP_JOB" in sr)
check("提供进度查询接口", "def _api_backup_status(self" in sr)
check("提供下载接口（与启动分离）", "def _api_backup_file(self" in sr)
check("后台线程执行打包（不阻塞请求）", "threading.Thread(target=work" in sr)
check("先扫描总量供前端算百分比", "job[\"totalBytes\"]" in sr)
check("打包线程异常不静默死（否则前端永久转圈）",
      "job[\"state\"] = \"error\"" in sr)
check("下载用 finally 清理临时文件（修残留泄漏）",
      re.search(r"def _api_backup_file.*?finally:.*?os\.remove\(tmp\)", sr, re.S) is not None)
check("下载后清空 job，防二次取到已删文件", "_BACKUP_JOB = None" in sr)
check("取消时丢弃产物（覆盖 done 态）",
      re.search(r'if qs\.get\("cancel"\) and job:', sr) is not None)
check("三路由均已注册",
      all(x in sr for x in ('path == "/api/backup/status"', 'path == "/api/backup/file"')))
check("前端有进度遮罩", 'id="backup-mask"' in idx)
check("前端轮询进度", "function pollBackup()" in idx)
check("进度条含 indeterminate 态（总量未知时也在动）", "indeterminate" in idx)
check("完成后才触发下载", "a.href = '/api/backup/file'" in idx)

print("\n[13] 超大文档（>10MB）打开门禁")
check("定义 10MB 阈值", "const BIG_DOC_BYTES = 10 * 1024 * 1024;" in idx)
check("强确认：须原样输入文档名", "showBigDocGate" in idx and "checkBigDocInput" in idx)
check("输入一致前按钮禁用", "ok.disabled = !match;" in idx)
check("放行时再做一次防御性校验",
      re.search(r"if \(\(document\.getElementById\('bigdoc-input'\)\.value \|\| ''\) !== _bigDocName\) return;", idx) is not None)
# 1.5.0.4：列表不再常驻显示体积、不再对超大文档做特殊标记，
# 改为鼠标悬停时在 title 中提示；打开 >10MB 仍走强确认。
check("列表已移除体积标签（.fsize）", "className = 'fsize'" not in idx)
check("列表已移除超大文档橙色标记（big-doc）", "classList.add('big-doc')" not in idx)
check("体积改为悬停提示（title 含体积）", "li.title = f.path" in idx)
check("悬停提示对超大文档追加二次确认说明",
      "超大文档，打开需二次确认" in idx)
check("拦截发生在传输正文之前（用列表已知 size）",
      "knownSize > BIG_DOC_BYTES" in idx)
check("未知体积时兜底再拦一次（passed 防重复弹窗）",
      "if (!passed && bytes > BIG_DOC_BYTES)" in idx)
check("已注册进 ESC 栈", "'bigdoc-mask'" in idx)
check("门禁对话框：取消=primary 且在左",
      re.search(r'id="bigdoc-cancel"[^>]*', idx) is not None
      and 'btn--primary" id="bigdoc-cancel"' in idx
      and idx.index('id="bigdoc-cancel"') < idx.index('id="bigdoc-ok"'))
check("门禁对话框：仍然打开=ghost（白底次按钮）",
      'btn--ghost" id="bigdoc-ok"' in idx)
check("门禁输入框复用通用文本框类（.set-input）",
      'id="bigdoc-input" class="set-input"' in idx)
check("门禁弹窗含风险自负与免责表述",
      "风险自负" in idx and "不承担责任" in idx)

print("\n结果: %d 通过, %d 失败" % (_pass, _fail))
sys.exit(0 if _fail == 0 else 1)
