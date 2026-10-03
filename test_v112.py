#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""v1.1.2 专项测试：定向验证本轮修改。

覆盖：
  #2  上传限制放开 + 可调（默认不限制格式、html 可上传且被沙箱隔离；upload_max_mb / upload_accept 可设）
  #3  网络访问安全两项默认开启（trust_proxy / secure_cookie 默认 True）
  #4  secure_cookie 关闭后公网 HTTP 可正常登录使用（Cookie 不带 Secure、操作不 401）
  #0  源站 304 机制仍生效（条件请求 → 304）
  文案：深色模式改名、网页图标说明、卸载引导文案（静态文件断言）
"""
import os, sys, json, time, tempfile, subprocess, urllib.request, urllib.error, shutil

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
        resp = urllib.request.urlopen(r, timeout=5)
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

PUBLIC_XFF = {"X-Forwarded-For": "8.8.8.8"}
HTTPS_PROTO = {"X-Forwarded-Proto": "https"}
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
        resp = urllib.request.urlopen(r, timeout=5)
        return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}

# ---------- Server A：默认配置（trust_proxy/secure_cookie 默认开启）----------
print("== Server A: defaults (no env override) ==")
tmpA = tempfile.mkdtemp(prefix="vd112a_")
pA = start_server(9341, tmpA)   # secure/trust_proxy 均不传 → 默认 True

st, d, h = req_full(pA, "POST", "/api/setup", {"password": "secret123"}, headers=LAN)
check("A setup via lan ok", st == 200 and d.get("ok"), str((st, d)))
ckA = cookie_of(h)
auth = {**LAN, "Cookie": ckA}

st, d = req(pA, "GET", "/api/settings", headers=auth)
check("A trust_proxy default ON", d.get("settings", {}).get("trust_proxy") is True, str(d))
check("A secure_cookie default ON", d.get("settings", {}).get("secure_cookie") is True, str(d))
check("A upload_max_mb default 256", d.get("settings", {}).get("upload_max_mb") == 256, str(d))
check("A upload_accept legacy field preserved", "upload_accept" in d.get("settings", {}), str(list(d.get("settings", {}).keys())))

# #0 源站 304：先取 ETag，再带条件请求
st1, _, h1 = req_full(pA, "GET", "/index.html", raw=True)
etag = h1.get("ETag") or h1.get("ETag".lower())
check("A index.html 200", st1 == 200, str(st1))
check("A index.html has ETag", bool(etag), str(h1.keys()))
if etag:
    st2, _, _ = req_full(pA, "GET", "/index.html", headers={"If-None-Match": etag}, raw=True)
    check("A conditional request -> 304", st2 == 304, str(st2))
else:
    check("A conditional request -> 304", False, "no ETag")

# 【1.1.3 起语义已变】上传格式由「白名单」反转为「黑名单」：
#   html 现默认在黑名单内 → 被拒绝；upload_accept 白名单不再参与校验。
# 下面按 1.1.3 语义断言，同时保留「即便放行也强制下载 + 沙箱」的纵深防御校验。
st, d = upload_file(pA, "test.html", "<html><body>hi</body></html>", headers=auth)
check("A html denied by default blacklist (1.1.3)", d.get("code") == 0 and "test.html" in d.get("data", {}).get("errFiles", []), str(d))

# 用户把 html 从黑名单移除后即可上传，且仍强制下载 + CSP 沙箱（不因放行而失去隔离）
req(pA, "POST", "/api/settings", {"upload_deny": "exe,dll,js"}, headers=auth)
st, d = upload_file(pA, "test.html", "<html><body>hi</body></html>", headers=auth)
check("A html allowed after removing from blacklist", d.get("code") == 0 and "test.html" in d.get("data", {}).get("succMap", {}), str(d))

store = d.get("data", {}).get("succMap", {}).get("test.html")
if store:
    st3, _, h3 = req_full(pA, "GET", "/" + store, raw=True, headers=auth)
    cd = h3.get("Content-Disposition", "")
    csp = h3.get("Content-Security-Policy", "")
    check("A uploaded html -> attachment+CSP sandbox", "attachment" in cd and "sandbox" in csp, str((cd, csp)))

# 黑名单追加条目后被拒；未命中的类型照常放行
st, d = req(pA, "POST", "/api/settings", {"upload_max_mb": 256, "upload_deny": "exe,dll,js,iso"}, headers=auth)
check("A set upload_deny ok", st == 200 and d.get("ok"), str((st, d)))
st, d = upload_file(pA, "disc.iso", "iso", headers=auth)
check("A iso rejected under blacklist", "disc.iso" in d.get("data", {}).get("errFiles", []), str(d))
st, d = upload_file(pA, "note.txt", "hello", headers=auth)
check("A txt allowed under blacklist", "note.txt" in d.get("data", {}).get("succMap", {}), str(d))
st, d = upload_file(pA, "pic.png", b"\x89PNG", headers=auth)
check("A png accepted under blacklist", "pic.png" in d.get("data", {}).get("succMap", {}), str(d))

# 单文件大小上限生效
st, d = req(pA, "POST", "/api/settings", {"upload_max_mb": 1, "upload_accept": ""}, headers=auth)
check("A set upload_max_mb=1 ok", st == 200 and d.get("ok"), str((st, d)))
big = b"x" * (2 * 1024 * 1024)  # 2MB > 1MB
bst, bd = upload_file(pA, "big.bin", big, headers=auth)
# 超限既可能由请求体守卫直接 413，也可能由 _handle_upload 的逐文件检查放入 errFiles
rejected = (bst == 413) or ("big.bin" in bd.get("data", {}).get("errFiles", []))
check("A oversized file rejected", rejected, str((bst, bd)))

# 恢复默认
req(pA, "POST", "/api/settings", {"upload_max_mb": 256, "upload_accept": ""}, headers=auth)

pA.terminate()
try: pA.wait(timeout=5)
except Exception: pA.kill()

# ---------- Server B：secure_cookie=OFF → 公网 HTTP 可正常登录使用（#4）----------
print("== Server B: secure_cookie=OFF, trust_proxy=ON ==")
tmpB = tempfile.mkdtemp(prefix="vd112b_")
pB = start_server(9342, tmpB, secure=False, trust_proxy=True)

st, d, h = req_full(pB, "POST", "/api/setup", {"password": "secret123"}, headers=PUBLIC_XFF)
check("B setup via public http ok (secure off)", st == 200 and d.get("ok"), str((st, d)))
setcookie = h.get("Set-Cookie", "")
check("B cookie has NO Secure (secure off)", "Secure" not in setcookie, str(setcookie))

st, d, hl = req_full(pB, "POST", "/api/login", {"password": "secret123"}, headers=PUBLIC_XFF)
check("B public http login ok", st == 200 and d.get("ok"), str((st, d)))
cookie = cookie_of(hl)
check("B login cookie has NO Secure", "Secure" not in cookie, str(cookie))
st, d = req(pB, "GET", "/api/settings", headers={**PUBLIC_XFF, "Cookie": cookie})
check("B authed op over public http -> 200 (no 401)", st == 200, str((st, d)))

pB.terminate()
try: pB.wait(timeout=5)
except Exception: pB.kill()

# ---------- Server C：secure_cookie=ON 回归 → 公网 HTTP 仍被拦截 ----------
print("== Server C: secure_cookie=ON, trust_proxy=ON (regression) ==")
tmpC = tempfile.mkdtemp(prefix="vd112c_")
pC = start_server(9343, tmpC, secure=True, trust_proxy=True)
st, d, _ = req_full(pC, "POST", "/api/setup", {"password": "secret123"}, headers=PUBLIC_XFF)
check("C public http setup blocked (403)", st == 403, str((st, d)))
check("C block msg mentions HTTPS", "HTTPS" in (d.get("error") or ""), str(d))

pC.terminate()
try: pC.wait(timeout=5)
except Exception: pC.kill()

# ---------- 静态文案断言（不启服务器）----------
print("== Static copy assertions ==")
idx = open(os.path.join(APP, "index.html"), encoding="utf-8").read()
check("copy 深色模式 label", "深色模式" in idx, "")
check("copy 深色模式 sub", "深色模式选项更改即刻生效" in idx, "")
check("copy 网页图标说明", "此处仅控制前端网页标题与图标" in idx, "")
check("copy 上传设置 section", "单个上传文件大小上限" in idx, "")
wiz = open(os.path.join(BASE, "vditor-fpk", "wizard", "uninstall"), encoding="utf-8").read()
check("copy 卸载引导 markdown 永不删", "Markdown 文档文件无论如何都不会被删除" in wiz, "")
check("copy 卸载引导 引用设置项", "卸载时的应用数据处理" in wiz, "")

for t in (tmpA, tmpB, tmpC):
    shutil.rmtree(t, ignore_errors=True)

print("\nRESULT(1.1.2): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
