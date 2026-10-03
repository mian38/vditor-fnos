#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""v4.0.8 专项测试：HTTP 登录守卫。

验证 _https_required_error 在「安全策略强制 HTTPS(Secure Cookie) 且当前为 HTTP 连接」时
禁止登录 / 设置，返回 403 与明确 HTTPS 提示；并验证局域网直连 / X-Forwarded-Proto: https
等放行路径不受影响。
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

def start_server(port, cfg, secure, trust_proxy):
    docs = os.path.join(cfg, "docs")
    uploads = os.path.join(cfg, "uploads")
    os.makedirs(docs, exist_ok=True)
    os.makedirs(uploads, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "VDITOR_CONFIG": cfg,
        "VDITOR_PORT": str(port),
        "VDITOR_HOST": "127.0.0.1",
        "VDITOR_DOC_DIR": docs,
        "VDITOR_DOC_NAME": "docs",
        "VDITOR_UPLOAD_DIR": uploads,
        "VDITOR_SECURE_COOKIE": "1" if secure else "",
        "VDITOR_TRUST_PROXY": "1" if trust_proxy else "",
    })
    proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    return proc

def req(proc, method, path, body=None, headers=None):
    URL = "http://127.0.0.1:%d" % proc._port
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=5)
        return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}

PUBLIC_XFF = {"X-Forwarded-For": "8.8.8.8"}            # 公网 IP（非私有网段）
HTTPS_PROTO = {"X-Forwarded-Proto": "https"}
LAN_XFF = {"X-Forwarded-For": "127.0.0.1"}            # 私有/回环

# ---------- 服务器 1：secure_cookie=1 + trust_proxy=1 ----------
print("== Server1: secure_cookie=ON, trust_proxy=ON ==")
tmp1 = tempfile.mkdtemp(prefix="vd408a_")
p1 = start_server(9161, tmp1, secure=True, trust_proxy=True)
p1._port = 9161

# 1) 通过 HTTPS 协议头完成首次设置（放行路径）
st, d = req(p1, "POST", "/api/setup", {"password": "secret123"},
            headers={**PUBLIC_XFF, **HTTPS_PROTO})
check("setup via https-proto allowed", st == 200 and d.get("ok"), str((st, d)))

# 2) 公网 IP 经纯 HTTP 登录 → 应被禁止 (403 + HTTPS 提示)
st, d = req(p1, "POST", "/api/login", {"password": "secret123"}, headers=PUBLIC_XFF)
check("http public login blocked", st == 403, str((st, d)))
check("block msg mentions HTTPS", "HTTPS" in (d.get("error") or ""), str(d))

# 3) 公网 IP 经 X-Forwarded-Proto: https 登录 → 应放行
st, d = req(p1, "POST", "/api/login", {"password": "secret123"},
            headers={**PUBLIC_XFF, **HTTPS_PROTO})
check("https-proto public login allowed", st == 200 and d.get("ok"), str((st, d)))

# 4) 局域网 IP（经代理回环）纯 HTTP 登录 → 应放行（LAN 豁免）
st, d = req(p1, "POST", "/api/login", {"password": "secret123"}, headers=LAN_XFF)
check("lan proxy http login allowed", st == 200 and d.get("ok"), str((st, d)))

# 5) 登录日志应记录 login_blocked_http 事件（场景 2）
logf = os.path.join(tmp1, "login_log.json")
blocked = False
try:
    with open(logf, encoding="utf-8") as f:
        for e in json.load(f):
            if e.get("kind") == "login_blocked_http":
                blocked = True
except Exception:
    pass
check("login_log has login_blocked_http", blocked, "log=%s" % (os.path.exists(logf)))

p1.terminate()
try: p1.wait(timeout=5)
except Exception: p1.kill()

# ---------- 服务器 2：secure_cookie=1 + trust_proxy=OFF（局域网直连）----------
print("== Server2: secure_cookie=ON, trust_proxy=OFF (LAN direct) ==")
tmp2 = tempfile.mkdtemp(prefix="vd408b_")
p2 = start_server(9162, tmp2, secure=True, trust_proxy=False)
p2._port = 9162

# 6) 局域网直连纯 HTTP 完成首次设置 → 放行（LAN 豁免）
st, d = req(p2, "POST", "/api/setup", {"password": "secret123"})
check("lan direct setup allowed", st == 200 and d.get("ok"), str((st, d)))

# 7) 局域网直连纯 HTTP 登录 → 放行（即使 secure_cookie=ON）
st, d = req(p2, "POST", "/api/login", {"password": "secret123"})
check("lan direct http login allowed", st == 200 and d.get("ok"), str((st, d)))

p2.terminate()
try: p2.wait(timeout=5)
except Exception: p2.kill()

# ---------- 服务器 3：secure_cookie=OFF（对照组，纯 HTTP 公网也应放行）----------
print("== Server3: secure_cookie=OFF (control) ==")
tmp3 = tempfile.mkdtemp(prefix="vd408c_")
p3 = start_server(9163, tmp3, secure=False, trust_proxy=True)
p3._port = 9163

st, d = req(p3, "POST", "/api/setup", {"password": "secret123"}, headers=PUBLIC_XFF)
check("control setup allowed", st == 200 and d.get("ok"), str((st, d)))
st, d = req(p3, "POST", "/api/login", {"password": "secret123"}, headers=PUBLIC_XFF)
check("control http public login allowed", st == 200 and d.get("ok"), str((st, d)))

p3.terminate()
try: p3.wait(timeout=5)
except Exception: p3.kill()

for t in (tmp1, tmp2, tmp3):
    shutil.rmtree(t, ignore_errors=True)

print("\nRESULT(4.0.8 https-guard): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
