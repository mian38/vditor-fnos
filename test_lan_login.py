#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：Bug#1 局域网 HTTP 登录 + v4.0.8 HTTP 登录守卫。
场景：SECURE_COOKIE=1 + TRUST_PROXY=1 时：
  A) 局域网私有网段（无 XFF，客户端 127.0.0.1）访问 -> Set-Cookie 不带 Secure，且 HTTP 会话可正常建立（登录成功）。
  B) 外网公网 IP（X-Forwarded-For: 8.8.8.8）纯 HTTP 访问 -> 安全策略要求 HTTPS，直接禁止登录/设置（403 + 明确提示）。
  C) 默认（SECURE_COOKIE 关闭）-> 不带 Secure（原有行为不被破坏）。
"""
import os, sys, json, time, tempfile, subprocess, urllib.request, urllib.error, urllib.parse, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

def start_server(env_extra):
    tmp = tempfile.mkdtemp(prefix="lanlogin_")
    docs = os.path.join(tmp, "docs"); os.makedirs(docs, exist_ok=True)
    port = 9200 + (hash(os.urandom(2)) % 500)
    env = dict(os.environ)
    env.update({
        "VDITOR_CONFIG": tmp, "VDITOR_PORT": str(port), "VDITOR_HOST": "127.0.0.1",
        "VDITOR_DOC_DIR": docs, "VDITOR_DOC_NAME": "docs",
        "VDITOR_UPLOAD_DIR": os.path.join(tmp, "uploads"),
    })
    env.update(env_extra)
    proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    return proc, port, tmp

def post(port, path, body, headers=None, cookie=None):
    h = {"Content-Type": "application/json"}
    if headers: h.update(headers)
    if cookie: h["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data, headers=h, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read().decode() or "{}"), resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}"), e.headers.get("Set-Cookie")

def get(port, path, headers=None, cookie=None):
    h = {}
    if headers: h.update(headers)
    if cookie: h["Cookie"] = cookie
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), headers=h, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

passed = 0; failed = 0
def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("  PASS", name)
    else: failed += 1; print("  FAIL", name, extra)

# 场景 A：局域网私有网段（无 XFF），SECURE_COOKIE=1
proc, port, tmp = start_server({"VDITOR_TRUST_PROXY": "1", "VDITOR_SECURE_COOKIE": "1"})
try:
    st, d, ck = post(port, "/api/setup", {"password": "secret123"})
    check("A setup ok", st == 200 and d.get("ok"), str(d))
    check("A Set-Cookie 不含 Secure", ck is not None and "Secure" not in ck, repr(ck))
    check("A Set-Cookie 含 vditor_sid", ck is not None and "vditor_sid=" in ck)
    # 后续请求复用 cookie（同样无 XFF -> 客户端 127.0.0.1 私有），应已登录
    st2, d2 = get(port, "/api/auth/check", cookie=ck)
    check("A HTTP 会话登录成功 (authenticated=true)", st2 == 200 and d2.get("authenticated") is True, str(d2))
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

# 场景 B（v4.0.8 起）：外网公网 IP（XFF=8.8.8.8）+ SECURE_COOKIE=1，纯 HTTP 访问
#     -> 安全策略要求 HTTPS，直接禁止登录/设置，返回 403 与明确提示
#        （修复旧行为：HTTP 下“登录成功”却因 Secure Cookie 无法落地，导致后续操作全 401）。
proc, port, tmp = start_server({"VDITOR_TRUST_PROXY": "1", "VDITOR_SECURE_COOKIE": "1"})
try:
    st, d, ck = post(port, "/api/setup", {"password": "secret123"}, headers={"X-Forwarded-For": "8.8.8.8"})
    check("B 外网 HTTP 设置被禁止(403)", st == 403, str((st, d)))
    check("B 提示需 HTTPS", "HTTPS" in (d.get("error") or ""), str(d))
    st2, d2, _ = post(port, "/api/login", {"password": "secret123"}, headers={"X-Forwarded-For": "8.8.8.8"})
    check("B 外网 HTTP 登录被禁止(403)", st2 == 403, str((st2, d2)))
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

# 场景 C：默认（SECURE_COOKIE 关闭）
proc, port, tmp = start_server({})
try:
    st, d, ck = post(port, "/api/setup", {"password": "secret123"})
    check("C 默认 setup ok", st == 200 and d.get("ok"), str(d))
    check("C 默认 Set-Cookie 不含 Secure", ck is not None and "Secure" not in ck, repr(ck))
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nRESULT: passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
