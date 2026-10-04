#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_core.py —— 核心功能集成测试（替代旧 test_v1xx / test_audit114 等逐版本冗余用例）

启动一次后端服务，覆盖鉴权、文档 CRUD、历史版本、分区、备份、设置导出、
静态资源安全与上传黑名单等核心链路。版本号一律动态读取，升版不会假红。

直接运行：python test_core.py
"""
import os, sys, io, re, json, time, socket, tempfile, subprocess, shutil
import urllib.request, urllib.error

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable
MF = os.path.join(BASE, "vditor-fpk", "manifest")
SRV = os.path.join(APP, "server.py")

# 动态读取版本（不写死，避免升版假红）
def manifest_version():
    with io.open(MF, encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("version="):
                return ln.strip().split("=", 1)[1].strip()
    return ""
MV = manifest_version()
m = re.search(r'APP_VERSION = "([^"]+)"', io.open(SRV, encoding="utf-8").read())
SV = m.group(1) if m else ""

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


# ---------------- 启动后端（空闲端口 + 临时目录） ----------------
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


port = free_port()
tmp = tempfile.mkdtemp(prefix="vdcore_")
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


def req(method, path, body=None, cookie=None, raw=False, ctype="application/json", headers=None):
    h = dict(headers or {})
    if ctype:
        h["Content-Type"] = ctype
    if cookie:
        h["Cookie"] = cookie
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=15)
        sc = resp.status
        rb = resp.read()
        cd = resp.headers.get("Set-Cookie")
        return sc, (rb if raw else (json.loads(rb.decode() or "{}") if rb else {})), resp.headers, cd
    except urllib.error.HTTPError as e:
        rb = e.read()
        try:
            j = json.loads(rb.decode() or "{}")
        except Exception:
            j = {}
        return e.code, (rb if raw else j), e.headers, None


def multipart(fields, files):
    """构造 multipart/form-data 请求体。files=[(field,name,content)]"""
    boundary = "----vdtestboundary"
    parts = []
    for k, v in fields.items():
        parts.append(("--%s\r\n" % boundary).encode()
                     + ("Content-Disposition: form-data; name=\"%s\"\r\n\r\n" % k).encode()
                     + v.encode() + b"\r\n")
    for fld, fname, content in files:
        parts.append(("--%s\r\n" % boundary).encode()
                     + ("Content-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n\r\n" % (fld, fname)).encode()
                     + content + b"\r\n")
    body = b"".join(parts) + ("--%s--\r\n" % boundary).encode()
    return body, "multipart/form-data; boundary=%s" % boundary


print("== 核心功能集成测试 ==")
print("版本 manifest=%s server=%s" % (MV, SV))

# ---------- 1) 鉴权流程 ----------
st, d, _, ck = req("POST", "/api/setup", {"password": "secret123"})
check("setup 返回 ok", st == 200 and d.get("ok"), (st, d))
check("setup 下发会话 Cookie", bool(ck) and "vditor_sid=" in ck, ck)
cookie = ck

st, d, _, _ = req("GET", "/api/auth/check", cookie=cookie)
check("auth/check 已登录", st == 200 and d.get("authenticated") is True, (st, d))

st, d, _, _ = req("GET", "/api/files")  # 无 cookie
check("未登录访问受限接口返回 401", st == 401, st)

st, d, _, ck2 = req("POST", "/api/login", {"password": "secret123"})
check("login 成功并下发 Cookie", st == 200 and bool(ck2), (st, d))
cookie = ck2

# 默认分区 id（slugify("我的文档")）
rid = "我的文档"

# ---------- 2) 文档保存 / 读取 / 列表 ----------
st, d, _, _ = req("POST", "/api/save", {"root": rid, "path": "core_smoke.md", "content": "# 标题\n正文"}, cookie=cookie)
check("save 成功", st == 200 and d.get("ok"), (st, d))

st, d, _, _ = req("GET", "/api/file?root=%s&path=core_smoke.md" % urllib.parse.quote(rid), cookie=cookie)
check("file 读取内容一致", st == 200 and d.get("content") == "# 标题\n正文", (st, d))

st, d, _, _ = req("GET", "/api/files", cookie=cookie)
found = any(any(f.get("name") == "core_smoke.md" for f in r.get("files", [])) for r in d.get("roots", []))
check("files 列表含已保存文档", st == 200 and found, (st, d))

# ---------- 3) 新建 / 删除 ----------
st, d, _, _ = req("POST", "/api/new", {"root": rid, "path": "core_new.md"}, cookie=cookie)
check("new 创建空文档", st == 200 and d.get("ok"), (st, d))

st, d, _, _ = req("POST", "/api/doc/delete", {"root": rid, "path": "core_new.md"}, cookie=cookie)
check("doc/delete 删除文档", st == 200 and d.get("ok"), (st, d))

# ---------- 4) 历史版本：保存两次后列表 + 回滚 ----------
req("POST", "/api/save", {"root": rid, "path": "core_smoke.md", "content": "v1"}, cookie=cookie)
req("POST", "/api/save", {"root": rid, "path": "core_smoke.md", "content": "v2"}, cookie=cookie)
st, d, _, _ = req("GET", "/api/versions?root=%s&path=core_smoke.md" % urllib.parse.quote(rid), cookie=cookie)
vers = d.get("versions", [])
check("versions 至少记录 1 个历史版本", st == 200 and len(vers) >= 1, (st, d))
if len(vers) >= 1:
    oldest = min(vers, key=lambda x: x["ts"])
    st, d, _, _ = req("POST", "/api/version/restore",
                      {"root": rid, "path": "core_smoke.md", "ts": oldest["ts"]}, cookie=cookie)
    check("version/restore 回滚到早期版本内容", st == 200 and d.get("content") == "v1", (st, d))
    # 恢复当前内容，保持用例间独立
    req("POST", "/api/save", {"root": rid, "path": "core_smoke.md", "content": "# 标题\n正文"}, cookie=cookie)

# ---------- 5) 分区增删 ----------
st, d, _, _ = req("POST", "/api/folders",
                  {"action": "add", "name": "tmp", "path": os.path.join(tmp, "extra")}, cookie=cookie)
roots = [r.get("id") for r in d.get("roots", [])]
check("folders add 新增分区生效", st == 200 and "tmp" in roots, (st, d))
st, d, _, _ = req("POST", "/api/folders",
                  {"action": "remove", "path": os.path.join(tmp, "extra")}, cookie=cookie)
check("folders remove 移除分区", st == 200 and "tmp" not in [r.get("id") for r in d.get("roots", [])], (st, d))

# ---------- 6) 备份导出 ----------
st, raw, hdrs, _ = req("GET", "/api/backup", cookie=cookie, raw=True)
is_gzip = raw[:2] == b"\x1f\x8b"
cd = hdrs.get("Content-Disposition") or ""
check("backup 返回 gzip 流", st == 200 and is_gzip, (st, len(raw)))
check("backup 强制下载（attachment）", "attachment" in cd, cd)

# ---------- 7) 设置导出含版本 ----------
st, d, _, _ = req("GET", "/api/settings/export", cookie=cookie)
check("settings/export 含 version 且与 manifest 一致", d.get("version") == MV, (st, d.get("version"), MV))

# ---------- 8) 静态资源安全 ----------
for denied in ("/server.py", "/vd_util.py", "/config.env", "/manifest"):
    st, _, _, _ = req("GET", denied, raw=True)
    check("静态禁止路径 404: %s" % denied, st == 404, st)

st, raw, hdrs, _ = req("GET", "/index.html", raw=True)
csp = hdrs.get("Content-Security-Policy") or ""
check("index 返回 200", st == 200, st)
check("CSP 含 default-src 'self'", "default-src 'self'" in csp, csp[:60])
check("响应头含 X-Frame-Options: DENY", (hdrs.get("X-Frame-Options") or "") == "DENY", hdrs.get("X-Frame-Options"))

# ---------- 9) 上传黑名单（端到端） ----------
body, ctype = multipart({"root": rid, "path": "core_smoke.md"},
                        [("file", "evil.exe", b"MZ"), ("file", "ok.png", b"\x89PNG")])
st, d, _, _ = req("POST", "/api/upload", body=body, cookie=cookie, ctype=ctype)
err = d.get("data", {}).get("errFiles", [])
succ = d.get("data", {}).get("succMap", {})
check("上传黑名单拒绝 .exe", "evil.exe" in err, err)
check("上传放行 .png", "ok.png" in succ, succ)

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
shutil.rmtree(tmp, ignore_errors=True)
print("\nRESULT(core): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
