#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_single_session.py —— 单活会话（后登踢先登）防回归测试（1.6.0.2）

背景：应用是「一个访问密码 = 一个席位」的单用户定位，但旧实现允许多个
页面 / 设备同时持有效会话。用户反馈多标签场景下「后开的页面把先开的
顶掉」还是「先开的把后开的挡死」语义不清，且改密 / 重启后行为不一致。

1.6.0.2 起 start_session() 采用**后登踢先登**：新登录成功即清空所有既有
会话，先登录者的下一个请求因 token 失效收到 401（前端据此弹「会话失效」
并返回登录页）。设计取舍（为什么不「先到先得」）：
  - 先登者不主动退出 → 后登者永远进不去（死锁）；
  - 服务重启后内存会话清空，锁自然失效（先到先得的锁不可靠）；
  - 误锁：先登者只是忘关页面，就挡住了所有后续登录。
后登踢先登无额外持久状态、重启即恢复，语义也符合单用户定位。

本测试拉起真实服务，按浏览器时序断言：
  1. setup / login 均能建立会话，且会话自身稳定（连续请求不误踢）；
  2. 第二次 login 后，旧 cookie 立即 401、新 cookie 200；
  3. 第三次 login 后，第二个 cookie 也 401、第三个 200（连锁踢出）；
  4. 登录日志记录 session_kicked 事件（含 evicted 数量，便于审计）；
  5. logout 仍按原语义失效当前会话（不受新机制影响）。

直接运行：python tests/test_single_session.py
"""
import os
import sys
import json
import time
import socket
import tempfile
import subprocess
import shutil
import urllib.request
import urllib.error

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


port = free_port()
tmp = tempfile.mkdtemp(prefix="vdsess_")
docdir = os.path.join(tmp, "docs")
uploaddir = os.path.join(tmp, "up")
os.makedirs(docdir, exist_ok=True)
os.makedirs(uploaddir, exist_ok=True)
env = dict(os.environ)
env.update({"VDITOR_CONFIG": tmp, "VDITOR_PORT": str(port), "VDITOR_HOST": "127.0.0.1",
            "VDITOR_DOC_DIR": docdir, "VDITOR_DOC_NAME": "我的文档",
            "VDITOR_UPLOAD_DIR": uploaddir})
proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
URL = "http://127.0.0.1:%d" % port
_ready = False
for _ in range(60):
    try:
        if urllib.request.urlopen(URL + "/index.html", timeout=2).status == 200:
            _ready = True
            break
    except Exception:
        pass
    if proc.poll() is not None:
        break
    time.sleep(0.5)
if not _ready:
    proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)
    raise SystemExit("服务未能在 %s 就绪（端口 %d），中止" % (URL, port))


def req(method, path, body=None, cookie=None, ctype="application/json"):
    h = {}
    if ctype:
        h["Content-Type"] = ctype
    if cookie:
        h["Cookie"] = cookie
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=30)
        sc = resp.status
        rb = resp.read()
        cd = resp.headers.get("Set-Cookie")
        return sc, (json.loads(rb.decode() or "{}") if rb else {}), cd
    except urllib.error.HTTPError as e:
        rb = e.read()
        try:
            j = json.loads(rb.decode() or "{}")
        except Exception:
            j = {}
        return e.code, j, None


def cookie_of(setc):
    """从 Set-Cookie 头取 vditor_sid=... 片段（不含属性）"""
    if not setc:
        return None
    for part in setc.split(";"):
        part = part.strip()
        if part.startswith("vditor_sid="):
            return part
    return None


print("== 单活会话（后登踢先登）测试（1.6.0.2）==")

try:
    # ---------- 1. 首次设置建立会话 A ----------
    st, d, ckA = req("POST", "/api/setup", {"password": "secret123"})
    check("setup 成功并下发会话 A", st == 200 and d.get("ok") and bool(ckA), (st, d))
    cookieA = cookie_of(ckA)

    st, d, _ = req("GET", "/api/settings", cookie=cookieA)
    check("会话 A 可访问受限接口（200）", st == 200, (st, d))

    # ---------- 2. 同一会话连续请求稳定（不得误踢自己） ----------
    stable = True
    for _ in range(3):
        st, d, _ = req("GET", "/api/settings", cookie=cookieA)
        if st != 200:
            stable = False
            break
    check("会话自身连续请求保持有效（无自杀式踢出）", stable)

    # ---------- 3. 第二次登录（第二个标签页）→ 踢掉 A ----------
    st, d, ckB = req("POST", "/api/login", {"password": "secret123"})
    check("第二次 login 成功并下发会话 B", st == 200 and d.get("ok") and bool(ckB), (st, d))
    cookieB = cookie_of(ckB)
    check("会话 B 与 A 是不同的 token", cookieB and cookieA and cookieB != cookieA,
          (cookieA, cookieB))

    st, d, _ = req("GET", "/api/settings", cookie=cookieA)
    check("旧会话 A 被踢出：请求返回 401", st == 401 and d.get("code") == 401, (st, d))
    st, d, _ = req("GET", "/api/settings", cookie=cookieB)
    check("新会话 B 正常（200）", st == 200, (st, d))

    # ---------- 4. 第三次登录 → 连锁踢出 B ----------
    st, d, ckC = req("POST", "/api/login", {"password": "secret123"})
    check("第三次 login 成功并下发会话 C", st == 200 and d.get("ok") and bool(ckC), (st, d))
    cookieC = cookie_of(ckC)
    st, d, _ = req("GET", "/api/settings", cookie=cookieB)
    check("会话 B 被连锁踢出：401", st == 401, (st, d))
    st, d, _ = req("GET", "/api/settings", cookie=cookieC)
    check("会话 C 正常（200）", st == 200, (st, d))

    # ---------- 5. 登录日志记录 session_kicked（可审计） ----------
    st, d, _ = req("GET", "/api/login-log", cookie=cookieC)
    entries = (d or {}).get("entries") or []
    kicked = [e for e in entries if e.get("kind") == "session_kicked"]
    check("登录日志含 session_kicked 事件", len(kicked) >= 2, len(kicked))
    check("session_kicked 记录 evicted 数量（detail）",
          all("evicted=" in (e.get("detail") or "") for e in kicked),
          [e.get("detail") for e in kicked])

    # ---------- 6. logout 语义不受影响 ----------
    st, d, _ = req("POST", "/api/logout", cookie=cookieC)
    check("logout 成功", st == 200 and d.get("ok"), (st, d))
    st, d, _ = req("GET", "/api/settings", cookie=cookieC)
    check("logout 后会话失效（401）", st == 401, (st, d))

    # ---------- 7. 全部登出后可重新登录（无死锁残留） ----------
    st, d, ckD = req("POST", "/api/login", {"password": "secret123"})
    check("全部失效后可重新登录（无死锁）", st == 200 and d.get("ok") and bool(ckD), (st, d))
    cookieD = cookie_of(ckD)
    st, d, _ = req("GET", "/api/settings", cookie=cookieD)
    check("重登会话可用（200）", st == 200, (st, d))

    # ---------- 8. 错误密码不得踢掉现有会话 ----------
    st, d, _ = req("POST", "/api/login", {"password": "wrong-pass"})
    check("错误密码登录被拒（401）", st == 401 and not d.get("ok"), (st, d))
    st, d, _ = req("GET", "/api/settings", cookie=cookieD)
    check("错误密码不影响现有会话（仍 200）", st == 200, (st, d))

finally:
    proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

print("\n结果: %d 通过, %d 失败" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
