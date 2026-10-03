#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""v4.0.6 专项测试：配置导入/导出、历史版本目录不进入“我的文档”、备份收录历史版本与配置。

注：1.0 起「导出备份」改为完整快照（含文档 + 历史版本 + 上传物 + 配置），
故此处断言由「备份排除历史版本」改为「备份包含历史版本」。"""
import os, sys, json, time, tempfile, subprocess, urllib.request, urllib.error, urllib.parse, shutil, io, tarfile

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

tmp = tempfile.mkdtemp(prefix="vd406_")
docs = os.path.join(tmp, "docs")
os.makedirs(docs, exist_ok=True)
port = 9131
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

def req(method, path, body=None, cookie=None, raw=False):
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=5)
        if raw:
            return resp.status, resp.read(), resp.headers
        return resp.status, json.loads(resp.read().decode() or "{}"), resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as e:
        if raw:
            return e.code, e.read(), e.headers
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

# 1) 首次设置 + 登录
st, d, ck = req("POST", "/api/setup", {"password": "secret123"})
check("setup ok", st == 200 and d.get("ok"), str((st, d)))
cookie = ck

# 2) 配置导出（JSON）
st, raw, hdr = req("GET", "/api/settings/export", cookie=cookie, raw=True)
try:
    exp = json.loads(raw.decode())
except Exception as e:
    exp = {}
check("export is json", st == 200 and hdr.get("Content-Type", "").startswith("application/json"), str(hdr))
check("export has settings", isinstance(exp.get("settings"), dict) and "autosave_interval" in exp["settings"], str(exp))
check("export has version", exp.get("version") == "1.2.2", str(exp.get("version")))

# 3) 配置导入：改一个值后回写
mod = dict(exp.get("settings", {}))
mod["autosave_interval"] = 222
mod["trust_proxy"] = (not mod.get("trust_proxy", False))
st, d, _ = req("POST", "/api/settings/import", {"settings": mod}, cookie=cookie)
check("import ok", st == 200 and d.get("ok") and d["settings"]["autosave_interval"] == 222 and d["settings"]["trust_proxy"] == mod["trust_proxy"], str((st, d)))
# 持久化校验
with open(os.path.join(tmp, "settings.json")) as f:
    sd = json.load(f)
check("import persisted", sd["autosave_interval"] == 222, str(sd))

# 4) 配置导入：非法字段应报错（不影响其他字段）
st, d, _ = req("POST", "/api/settings/import", {"settings": {"autosave_interval": "abc"}}, cookie=cookie)
check("import rejects bad field", st == 200 and d.get("ok") is False and "autosave_interval" in (d.get("error") or ""), str((st, d)))

# 5) 历史版本目录不进入“我的文档”
req("POST", "/api/settings", {"versioning": True}, cookie=cookie)
req("POST", "/api/new", {"root": "docs", "path": "doc1.md"}, cookie=cookie)
req("POST", "/api/save", {"root": "docs", "path": "doc1.md", "content": "v1"}, cookie=cookie)
req("POST", "/api/save", {"root": "docs", "path": "doc1.md", "content": "v2"}, cookie=cookie)
# 确认 .vditor_versions 已生成
vdir_exists = os.path.isdir(os.path.join(docs, ".vditor_versions"))
check("versions dir created", vdir_exists, str(os.listdir(docs)))
st, d, _ = req("GET", "/api/files", cookie=cookie)
files = []
for r in d.get("roots", []):
    if r["id"] == "docs":
        files = [f["path"] for f in r.get("files", [])]
check("files lists doc1.md", "doc1.md" in files, str(files))
check("files excludes .vditor_versions", not any(".vditor_versions" in p for p in files), str(files))

# 6) 备份应包含 .vditor_versions（1.0 起备份为完整快照：文档 + 历史版本 + 上传物 + 配置）
try:
    st, raw, hdr = req("GET", "/api/backup", cookie=cookie, raw=True)
    t = tarfile.open(fileobj=io.BytesIO(raw))
    names = t.getnames()
    check("backup includes versions", any(".vditor_versions" in n for n in names), str([n for n in names if "vditor" in n][:5]))
    check("backup includes config", any(n.startswith("config/") for n in names), str(names[:5]))
except Exception as e:
    check("backup", False, str(e))

# 清理
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
shutil.rmtree(tmp, ignore_errors=True)

print("\nRESULT(4.0.6): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
