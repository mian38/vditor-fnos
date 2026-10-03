#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""冒烟测试：新接口（设置/改密/登录日志/历史版本/备份）"""
import os, sys, json, time, tempfile, subprocess, urllib.request, urllib.error, urllib.parse, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

tmp = tempfile.mkdtemp(prefix="vdtest_")
docs = os.path.join(tmp, "docs")
os.makedirs(docs, exist_ok=True)
port = 9123
env = dict(os.environ)
env.update({
    "VDITOR_CONFIG": tmp,
    "VDITOR_PORT": str(port),
    "VDITOR_HOST": "127.0.0.1",
    "VDITOR_DOC_DIR": docs,
    "VDITOR_DOC_NAME": "docs",
    "VDITOR_UPLOAD_DIR": os.path.join(tmp, "uploads"),
})

proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.5)

URL = "http://127.0.0.1:%d" % port
passed = 0
failed = 0

def req(method, path, body=None, cookie=None):
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=5)
        return resp.status, json.loads(resp.read().decode() or "{}"), resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}"), None
        except Exception:
            return e.code, {}, None

def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)

# 1) 首次设置
st, d, ck = req("POST", "/api/setup", {"password": "secret123"})
check("setup ok", st == 200 and d.get("ok"), str((st, d)))
cookie = ck

# 2) 设置 GET（未登录应 401）
st, d, _ = req("GET", "/api/settings")
check("settings requires auth", st == 401, str(st))

# 3) 设置 GET（登录后）
st, d, _ = req("GET", "/api/settings", cookie=cookie)
check("settings get", st == 200 and "settings" in d and "autosave_interval" in d["settings"], str((st, d)))

# 4) 设置 UPDATE（改 trust_proxy + autosave_interval）
st, d, _ = req("POST", "/api/settings", {"trust_proxy": True, "autosave_interval": 120, "versioning": False}, cookie=cookie)
check("settings update", st == 200 and d["settings"]["trust_proxy"] is True and d["settings"]["autosave_interval"] == 120, str((st, d)))
# 文件应持久化
with open(os.path.join(tmp, "settings.json")) as f:
    sd = json.load(f)
check("settings persisted", sd["trust_proxy"] is True and sd["autosave_interval"] == 120, str(sd))

# 5) 改密码（错误旧密码）
st, d, _ = req("POST", "/api/change-password", {"old_password": "wrong", "new_password": "newpass123", "confirm_password": "newpass123"}, cookie=cookie)
check("change-pw wrong old", st == 403, str((st, d)))

# 6) 改密码（正确）
st, d, _ = req("POST", "/api/change-password", {"old_password": "secret123", "new_password": "newpass123", "confirm_password": "newpass123"}, cookie=cookie)
check("change-pw ok", st == 200 and d.get("ok"), str((st, d)))
# 旧密码应失效，新密码可登录，且会话被清空（cookie 失效）
st, d, _ = req("POST", "/api/login", {"password": "secret123"})
check("old pw invalid after change", st == 401, str(st))
st, d, ck2 = req("POST", "/api/login", {"password": "newpass123"})
check("new pw login ok", st == 200 and d.get("ok"), str((st, d)))
cookie = ck2

# 7) 保存文件并验证历史版本生成（先恢复 versioning=true）
req("POST", "/api/settings", {"versioning": True}, cookie=cookie)
# 新建
st, d, _ = req("POST", "/api/new", {"root": "docs", "path": "t.md"}, cookie=cookie)
check("new file", st == 200 and d.get("ok"), str((st, d)))
# 保存 v1
req("POST", "/api/save", {"root": "docs", "path": "t.md", "content": "hello v1"}, cookie=cookie)
# 保存 v2（内容变化，应生成版本）
st, d, _ = req("POST", "/api/save", {"root": "docs", "path": "t.md", "content": "hello v2"}, cookie=cookie)
check("save v2 ok", st == 200 and d.get("ok"), str((st, d)))
# 列表版本
st, d, _ = req("GET", "/api/versions?root=docs&path=" + urllib.parse.quote("t.md"), cookie=cookie)
vers = d.get("versions", [])
check("versions listed", st == 200 and len(vers) >= 1, str((st, d)))
# 恢复最早版本（v1 内容）
if vers:
    oldest = vers[-1]["ts"]
    st, d, _ = req("POST", "/api/version/restore", {"root": "docs", "path": "t.md", "ts": oldest}, cookie=cookie)
    check("restore version", st == 200 and "content" in d, str((st, d)))
    # 删除该版本
    st, d, _ = req("POST", "/api/version/delete", {"root": "docs", "path": "t.md", "ts": oldest}, cookie=cookie)
    check("delete version", st == 200 and d.get("ok") is True, str((st, d)))

# 8) 登录日志
st, d, _ = req("GET", "/api/login-log", cookie=cookie)
entries = d.get("entries", [])
check("login-log has entries", st == 200 and len(entries) >= 1, str((st, d)))

# 9) 备份导出（gzip tar）
try:
    r = urllib.request.Request(URL + "/api/backup", headers={"Cookie": cookie}, method="GET")
    resp = urllib.request.urlopen(r, timeout=5)
    data = resp.read()
    check("backup gzip", resp.headers.get("Content-Type") == "application/gzip" and data[:2] == b"\x1f\x8b", str(resp.headers.get("Content-Type")))
    # 解析 tar 内容
    import io, tarfile
    t = tarfile.open(fileobj=io.BytesIO(data))
    names = t.getnames()
    check("backup contains config+doc", any(n.startswith("config/") for n in names) and any(n.startswith("docs/") for n in names), str(names[:10]))
except Exception as e:
    check("backup", False, str(e))

# 清理
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
shutil.rmtree(tmp, ignore_errors=True)

print("\nRESULT: passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
