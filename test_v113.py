#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""v1.1.3 专项测试：定向验证本轮修改（版本断言随 1.1.4 升版同步）。

覆盖：
  #0  根因修复：前端 upload.accept 不再使用 '*'（Vditor 无「不限制」状态，'*' 会拦掉一切）→ 上传恢复可用
  #0  配置持久化 / 向后兼容：老 settings.json（无 upload_deny）自动补默认黑名单；
      废弃的 upload_accept 不再参与校验（降级兼容保留）
  #2  白名单反转为黑名单：默认拦截 exe/js/html 等高风险类型，放行 png/txt/iso 等；
      用户可追加、删除条目；非法条目被拒并回显
  #1  界面统一：上传黑名单输入框与同页其它输入控件共用同一套样式（含聚焦态/占位符）
  文案与静态标记
"""
import os, re, sys, json, time, tempfile, subprocess, urllib.request, urllib.error, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


def start_server(port, cfg, secure=None, trust_proxy=None):
    docs = os.path.join(cfg, "docs")
    os.makedirs(docs, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "VDITOR_CONFIG": cfg,
        "VDITOR_PORT": str(port),
        "VDITOR_HOST": "127.0.0.1",
        "VDITOR_DOC_DIR": docs,
        "VDITOR_DOC_NAME": "docs",
    })
    if secure is not None:
        env["VDITOR_SECURE_COOKIE"] = "1" if secure else "0"
    if trust_proxy is not None:
        env["VDITOR_TRUST_PROXY"] = "1" if trust_proxy else "0"
    proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    proc._port = port
    return proc


def req_full(proc, method, path, body=None, headers=None, raw=False):
    URL = "http://127.0.0.1:%d" % proc._port
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=8)
        hdrs = dict(resp.headers.items())
        rawbody = resp.read().decode()
        return resp.status, (rawbody if raw else json.loads(rawbody or "{}")), hdrs
    except urllib.error.HTTPError as e:
        hdrs = dict(e.headers.items())
        rawbody = e.read().decode()
        return e.code, (rawbody if raw else json.loads(rawbody or "{}")), hdrs


def req(proc, method, path, body=None, headers=None):
    st, d, _ = req_full(proc, method, path, body, headers)
    return st, d


def cookie_of(hdrs):
    sc = hdrs.get("Set-Cookie", "")
    return sc.split(";")[0] if sc else ""


LAN = {"X-Forwarded-For": "127.0.0.1"}


def upload_file(proc, fname, content, headers=None):
    b = content if isinstance(content, bytes) else content.encode()
    boundary = "----vdtestboundary"
    parts = []
    parts.append(("--%s\r\n" % boundary).encode())
    parts.append(b'Content-Disposition: form-data; name="root"\r\n\r\n')
    parts.append(b"\r\n")
    parts.append(("--%s\r\n" % boundary).encode())
    parts.append(b'Content-Disposition: form-data; name="path"\r\n\r\n')
    parts.append(b"\r\n")
    parts.append(("--%s\r\n" % boundary).encode())
    parts.append(('Content-Disposition: form-data; name="file[]"; filename="%s"\r\n' % fname).encode())
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(b)
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    body = b"".join(parts)
    h = {"Content-Type": "multipart/form-data; boundary=%s" % boundary}
    if headers:
        h.update(headers)
    URL = "http://127.0.0.1:%d/api/upload" % proc._port
    r = urllib.request.Request(URL, data=body, headers=h, method="POST")
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


_UPLOAD_HDR = {}          # 由各 Server 段设置为该实例的鉴权头（含 Cookie）


def uploaded(fname, content="x", headers=None):
    """返回 (是否成功落库, errFiles 列表)。默认带上当前实例的鉴权 Cookie。"""
    h = dict(_UPLOAD_HDR)
    if headers:
        h.update(headers)
    st, d = upload_file(globals()["_p"], fname, content, h)
    err = (d.get("data") or {}).get("errFiles") or []
    if st != 200:
        return False, ["<http %d>" % st]
    return fname not in err, err


# ============ Server A：默认配置（黑名单默认生效） ============
print("== Server A: default blacklist ==")
tmpA = tempfile.mkdtemp(prefix="vd113a_")
pA = start_server(9341, tmpA)
globals()["_p"] = pA

st, d, h = req_full(pA, "POST", "/api/setup", {"password": "secret123"}, headers=LAN)
check("A setup ok", st == 200 and d.get("ok"), str((st, d)))
auth = {**LAN, "Cookie": cookie_of(h)}
globals()["_UPLOAD_HDR"] = auth

st, d = req(pA, "GET", "/api/settings", headers=auth)
S = d.get("settings", {})
deny = S.get("upload_deny", "")
check("A upload_deny present & non-empty", bool(deny), repr(deny))
check("A upload_deny contains exe", "exe" in deny.split(","), repr(deny[:80]))
check("A upload_deny normalized (no dot/space/upper)", all(
    x == x.lower() and "." not in x and x.strip() == x and x for x in deny.split(",")), repr(deny))
check("A upload_deny has no dup", len(deny.split(",")) == len(set(deny.split(","))), repr(deny))
check("A legacy upload_accept still present (downgrade compat)", "upload_accept" in S, str(list(S.keys())))

# 默认黑名单：拦截高风险、放行普通
ok, err = uploaded("evil.exe")
check("A default denies .exe", (not ok) and "evil.exe" in err, str(err))
ok, err = uploaded("script.js")
check("A default denies .js", (not ok) and "script.js" in err, str(err))
ok, err = uploaded("page.html")
check("A default denies .html", (not ok) and "page.html" in err, str(err))
ok, err = uploaded("EVIL.EXE")
check("A blacklist case-insensitive (.EXE)", (not ok) and "EVIL.EXE" in err, str(err))
ok, err = uploaded("pic.png")
check("A allows .png", ok, str(err))
ok, err = uploaded("notes.txt")
check("A allows .txt", ok, str(err))
ok, err = uploaded("disc.iso")
check("A allows .iso (白名单时代被误拦的典型)", ok, str(err))
ok, err = uploaded("archive.tar.gz")
check("A allows .tar.gz", ok, str(err))
ok, err = uploaded("noext")
check("A allows file without extension", ok, str(err))

# 用户删除条目后 → 放行
st, d = req(pA, "POST", "/api/settings", {"upload_deny": "exe,dll"}, headers=auth)
check("A set upload_deny=exe,dll ok", st == 200 and d.get("ok"), str((st, d)))
ok, err = uploaded("page.html")
check("A after removal allows .html", ok, str(err))
ok, err = uploaded("script.js")
check("A after removal allows .js", ok, str(err))
ok, err = uploaded("evil.dll")
check("A still denies remaining .dll", (not ok) and "evil.dll" in err, str(err))

# 用户追加条目 → 拦截
st, d = req(pA, "POST", "/api/settings", {"upload_deny": "exe,dll,iso"}, headers=auth)
check("A append iso ok", st == 200 and d.get("ok"), str((st, d)))
ok, err = uploaded("disc.iso")
check("A appended entry denies .iso", (not ok) and "disc.iso" in err, str(err))

# 清空白名单 → 全部放行
st, d = req(pA, "POST", "/api/settings", {"upload_deny": ""}, headers=auth)
check("A clear blacklist ok", st == 200 and d.get("ok"), str((st, d)))
check("A cleared blacklist persisted as empty", d.get("settings", {}).get("upload_deny") == "", repr(d.get("settings", {}).get("upload_deny")))
ok, err = uploaded("evil.exe")
check("A empty blacklist allows .exe", ok, str(err))
ok, err = uploaded("script.js")
check("A empty blacklist allows .js", ok, str(err))

# 非法条目 → 拒绝并回显
st, d = req(pA, "POST", "/api/settings", {"upload_deny": "exe,../bad,waytoolongnamehere"}, headers=auth)
check("A invalid ext rejected", st == 200 and not d.get("ok"), str((st, d)))
check("A invalid ext message names offender", "waytoolongnamehere" in str(d.get("error", "")), str(d.get("error")))

# 大小上限仍生效
req(pA, "POST", "/api/settings", {"upload_max_mb": 1}, headers=auth)
ok, err = uploaded("small.txt", "a")
check("A small file ok under 1MB", ok, str(err))
bst, berr = upload_file(pA, "big.bin", b"x" * (2 * 1024 * 1024), auth)
check("A oversized rejected (413 or errFiles)",
      bst == 413 or "big.bin" in ((berr.get("data") or {}).get("errFiles") or []), str((bst, berr)))
req(pA, "POST", "/api/settings", {"upload_max_mb": 256}, headers=auth)

# 废弃的 upload_accept 不再参与校验（白名单时代遗留值也不应误拦）
st, d = req(pA, "POST", "/api/settings", {"upload_accept": "png", "upload_deny": "exe"}, headers=auth)
check("A legacy accept accepted (downgrade compat)", st == 200 and d.get("ok"), str((st, d)))
ok, err = uploaded("notes.txt")
check("A legacy accept does NOT restrict (.txt allowed)", ok, str(err))

# 导出含 upload_deny
st, body, _ = req_full(pA, "GET", "/api/settings/export", headers=auth, raw=True)
check("A export includes upload_deny", '"upload_deny"' in str(body), str(st))

# ============ Server B：向后兼容迁移（老 settings.json 无 upload_deny） ============
print("== Server B: legacy settings migration ==")
tmpB = tempfile.mkdtemp(prefix="vd113b_")
os.makedirs(os.path.join(tmpB, "docs"), exist_ok=True)
# 模拟 1.1.2 及更早的 settings.json：有 upload_accept，无 upload_deny
with open(os.path.join(tmpB, "settings.json"), "w", encoding="utf-8") as f:
    json.dump({"upload_max_mb": 128, "upload_accept": "png,jpg",
               "page_title": "legacy", "versioning": True}, f)
pB = start_server(9342, tmpB)
st, d, h = req_full(pB, "POST", "/api/setup", {"password": "secret123"}, headers=LAN)
check("B setup ok (legacy cfg)", st == 200 and d.get("ok"), str((st, d)))
authB = {**LAN, "Cookie": cookie_of(h)}
st, d = req(pB, "GET", "/api/settings", headers=authB)
SB = d.get("settings", {})
check("B legacy cfg gets default blacklist", "exe" in SB.get("upload_deny", ""), repr(SB.get("upload_deny"))[:80])
check("B legacy upload_max_mb preserved (128)", SB.get("upload_max_mb") == 128, str(SB.get("upload_max_mb")))
check("B legacy upload_accept preserved", SB.get("upload_accept") == "png,jpg", str(SB.get("upload_accept")))
globals()["_p"] = pB
globals()["_UPLOAD_HDR"] = authB
ok, err = uploaded("evil.exe")
check("B legacy install now denies .exe", (not ok) and "evil.exe" in err, str(err))
ok, err = uploaded("disc.iso")
check("B legacy install allows .iso (was blocked by old whitelist)", ok, str(err))

# ============ Server C：重启后黑名单仍按用户配置生效（配置持久化） ============
print("== Server C: persistence across restart ==")
tmpC = tempfile.mkdtemp(prefix="vd113c_")
pC = start_server(9343, tmpC)
st, d, h = req_full(pC, "POST", "/api/setup", {"password": "secret123"}, headers=LAN)
authC = {**LAN, "Cookie": cookie_of(h)}
req(pC, "POST", "/api/settings", {"upload_deny": "foo,bar", "upload_max_mb": 77}, headers=authC)
pC.terminate(); pC.wait(timeout=10)
pC = start_server(9344, tmpC)                      # 同一配置目录重启
st, d, h2 = req_full(pC, "POST", "/api/login", {"password": "secret123"}, headers=LAN)
check("C re-login ok after restart", st == 200 and d.get("ok"), str((st, d)))
authC = {**LAN, "Cookie": cookie_of(h2)}
globals()["_p"] = pC
globals()["_UPLOAD_HDR"] = authC
st, d = req(pC, "GET", "/api/settings", headers=authC)
check("C custom blacklist survives restart", d.get("settings", {}).get("upload_deny") == "foo,bar",
      repr(d.get("settings", {}).get("upload_deny")))
check("C upload_max_mb survives restart", d.get("settings", {}).get("upload_max_mb") == 77,
      str(d.get("settings", {}).get("upload_max_mb")))
ok, err = uploaded("x.foo")
check("C user-added entry enforced after restart", (not ok) and "x.foo" in err, str(err))
ok, err = uploaded("evil.exe")
check("C removed default (.exe) stays allowed after restart", ok, str(err))

# 清空后重启，空黑名单不得被默认值还原
req(pC, "POST", "/api/settings", {"upload_deny": ""}, headers=authC)
pC.terminate(); pC.wait(timeout=10)
pC = start_server(9345, tmpC)
st, d, h3 = req_full(pC, "POST", "/api/login", {"password": "secret123"}, headers=LAN)
authC = {**LAN, "Cookie": cookie_of(h3)}
globals()["_p"] = pC
globals()["_UPLOAD_HDR"] = authC
st, d = req(pC, "GET", "/api/settings", headers=authC)
check("C emptied blacklist stays empty after restart", d.get("settings", {}).get("upload_deny") == "",
      repr(d.get("settings", {}).get("upload_deny")))
ok, err = uploaded("evil.exe")
check("C emptied blacklist still allows .exe after restart", ok, str(err))

# ============ 静态断言：前端与样式 ============
print("== Static assertions (frontend + style) ==")
html = io_html = open(os.path.join(APP, "index.html"), encoding="utf-8").read()

# #0 根因修复：不得再出现 accept: '*'（会让 Vditor 拦掉一切上传）
check("no accept:'*' remains", "accept: '*'" not in html and 'accept: "*"' not in html, "found wildcard accept")
check("VDITOR_ACCEPT_ANY defined", "VDITOR_ACCEPT_ANY" in html, "missing pass-through object")
check("upload uses VDITOR_ACCEPT_ANY", "accept: VDITOR_ACCEPT_ANY" in html, "upload option not patched")
check("applyUploadSettings applies it", "vditor.vditor.options.upload.accept = VDITOR_ACCEPT_ANY" in html, "")
check("upload.max still dynamic", "options.upload.max = mb * 1024 * 1024" in html, "")
# #2 黑名单 UI
check("blacklist label present", "不允许上传的文件格式" in html, "")
check("blacklist input id", 'id="set-upload-deny"' in html, "")
check("add button present", 'id="btn-deny-add"' in html, "")
check("reset-default button present", 'id="btn-deny-reset"' in html, "")
check("chip container present", 'id="deny-list"' in html, "")
check("chip class present", "set-ext-chip" in html, "")
check("feedback element present", 'id="upload-deny-err"' in html, "")
check("saves upload_deny", "upload_deny: UPLOAD_DENY_LIST.join(',')" in html, "")
check("default list in UI", "DEFAULT_UPLOAD_DENY_UI" in html, "")
check("old whitelist control removed", "set-upload-accept" not in html, "stale whitelist input")
# #1 样式统一
check("deny input in shared input style", ".set-ext-row input," in html, "")
check("deny input focus state unified", ".set-ext-row input:focus" in html, "")
check("deny input placeholder unified", ".set-ext-row input::placeholder" in html, "")
check("feedback shares error style", "#pw-err, #folders-err, #upload-deny-err" in html, "")

# 后端默认黑名单常量与 UI 默认一致
sys.path.insert(0, APP)
from vd_util import DEFAULT_UPLOAD_DENY, normalize_ext_list, is_denied_upload  # noqa: E402
deny_set = set(normalize_ext_list(DEFAULT_UPLOAD_DENY))
check("backend default blacklist non-trivial", len(deny_set) >= 50, str(len(deny_set)))
for e in ("exe", "dll", "bat", "js", "vbs", "php", "html", "svg", "sh"):
    check("backend default denies ." + e, is_denied_upload("x." + e, DEFAULT_UPLOAD_DENY) == e, e)
check("normalize strips dots/case", normalize_ext_list(" .EXE , dll ") == ["exe", "dll"], str(normalize_ext_list(" .EXE , dll ")))
check("normalize dedupes", normalize_ext_list("exe,exe,EXE") == ["exe"], "")
check("empty blacklist denies nothing", is_denied_upload("x.exe", "") == "", "")

# 版本号：动态断言（三方一致 + 不低于基线），避免每次升版假红
server_py = open(os.path.join(APP, "server.py"), encoding="utf-8").read()
manifest = open(os.path.join(BASE, "vditor-fpk", "manifest"), encoding="utf-8").read()
_mv = re.search(r"(?m)^version\s*=\s*(\S+)\s*$", manifest)
_vdef = _mv.group(1) if _mv else None
_vt = tuple(int(x) for x in _vdef.split(".")) if _vdef else ()
check("manifest version 可解析且 >= 1.2.0", _vt >= (1, 2, 0), str(_vdef))
check("server.py APP_VERSION 与 manifest 一致",
      'APP_VERSION = "%s"' % _vdef in server_py, str(_vdef))

for p in (pA, pB, pC):
    try:
        p.terminate()
    except Exception:
        pass
shutil.rmtree(tmpA, ignore_errors=True)
shutil.rmtree(tmpB, ignore_errors=True)
shutil.rmtree(tmpC, ignore_errors=True)

print("\nRESULT(1.1.3): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)