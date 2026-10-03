#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""包内资源冒烟测试：确保交付所需的静态资源齐全、被移除的组件确实不存在、
静态服务白名单与安全响应头按预期工作、版本号一致。

放在常规回归套件里，防止「改静态服务或精简包体时误删/误放行」这类回归。
"""
import os, sys, json, time, socket, tempfile, subprocess, shutil, io, urllib.request, urllib.error

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable
tmp = tempfile.mkdtemp(prefix="vdpkg_")


def free_port():
    """取一个当前空闲端口，避免上一轮残留进程占用固定端口导致假失败。"""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


port = free_port()
env = dict(os.environ)
env.update({"VDITOR_CONFIG": tmp, "VDITOR_PORT": str(port), "VDITOR_HOST": "127.0.0.1",
            "VDITOR_DOC_DIR": os.path.join(tmp, "docs"), "VDITOR_DOC_NAME": "docs",
            "VDITOR_UPLOAD_DIR": os.path.join(tmp, "up")})
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
passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1; print("  PASS", name)
    else:
        failed += 1; print("  FAIL", name, extra)


def req(method, path, body=None, cookie=None, raw=False, ctype="application/json"):
    h = {"Content-Type": ctype} if ctype else {}
    if cookie:
        h["Cookie"] = cookie
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=15)
        return resp.status, (resp.read() if raw else json.loads(resp.read().decode() or "{}")), resp.headers, resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            j = json.loads(b.decode() or "{}")
        except Exception:
            j = {}
        return e.code, (b if raw else j), e.headers, None


# ---------- 1) 必需静态资源必须 200 ----------
NEEDED = [
    "/", "/index.html",
    "/vditor/dist/index.css", "/vditor/dist/index.min.js", "/vditor/dist/method.min.js",
    "/vditor/dist/js/lute/lute.min.js",
    "/vditor/dist/js/katex/katex.min.js", "/vditor/dist/js/katex/katex.min.css",
    "/vditor/dist/js/mermaid/mermaid.min.js",
    "/vditor/dist/js/graphviz/viz.js", "/vditor/dist/js/graphviz/full.render.js",
    "/vditor/dist/js/echarts/echarts.min.js", "/vditor/dist/js/markmap/markmap.min.js",
    "/vditor/dist/js/abcjs/abcjs_basic.min.js", "/vditor/dist/js/smiles-drawer/smiles-drawer.min.js",
    "/vditor/dist/js/wavedrom/wavedrom.min.js", "/vditor/dist/js/flowchart.js/flowchart.min.js",
    "/vditor/dist/js/plantuml/plantuml-encoder.min.js",
    "/vditor/dist/js/highlight.js/highlight.min.js", "/vditor/dist/js/highlight.js/third-languages.js",
    "/vditor/dist/js/highlight.js/styles/github.min.css", "/vditor/dist/js/highlight.js/styles/a11y-dark.min.css",
    "/vditor/dist/js/icons/ant.js", "/vditor/dist/js/i18n/zh_CN.js",
    "/vditor/dist/css/content-theme/light.css", "/vditor/dist/css/content-theme/dark.css",
    "/vditor/dist/css/content-theme/ant-design.css", "/vditor/dist/css/content-theme/wechat.css",
    "/ui/config", "/ui/images/icon_64.png", "/ui/images/icon_256.png",
]
for p in NEEDED:
    st, _, _, _ = req("GET", p, raw=True)
    check("200 %s" % p, st == 200, str(st))

# ---------- 2) 已移除/禁止的路径必须 404 ----------
FORBIDDEN = [
    "/server.py", "/vd_util.py", "/manifest", "/config.env",
    "/vditor/dist/js/mathjax/tex-svg-full.js",        # 精简时移除（不可达）
    "/vditor/dist/index.js", "/vditor/dist/method.js",  # 开发版
    "/vditor/dist/index.d.ts", "/vditor/src/index.ts",  # 类型/源码
    "/vditor/dist/js/icons/material.js",                # 未使用图标
    "/vditor/dist/js/i18n/en_US.js",                    # 未使用语言包
    "/random.txt", "/vditor/../server.py", "/ui/../server.py",
]
for p in FORBIDDEN:
    st, _, _, _ = req("GET", p, raw=True)
    check("404 %s" % p, st == 404, str(st))

# ---------- 3) 前端关键标记 ----------
st, raw, _, _ = req("GET", "/index.html", raw=True)
html = raw.decode("utf-8", "replace")
check("index 含默认教程块", '<script type="text/markdown" id="welcome-md">' in html and "# 教程" in html)
check("index 含工具栏 more 子菜单", "name: 'more'" in html)
check("index 含 outdent/indent", "'check', 'outdent', 'indent'" in html)
check("index 含忘记密码文案", "请在 fnOS 终端中执行命令" in html)

# ---------- 4) 静态缓存与 304 ----------
st, _, hdrs, _ = req("GET", "/vditor/dist/index.min.js", raw=True)
etag = hdrs.get("ETag")
check("静态资源带 ETag/Last-Modified", bool(etag) and bool(hdrs.get("Last-Modified")), str(etag))
r = urllib.request.Request(URL + "/vditor/dist/index.min.js", headers={"If-None-Match": etag or ""}, method="GET")
try:
    st304 = urllib.request.urlopen(r, timeout=5).status
except urllib.error.HTTPError as e:
    st304 = e.code
check("静态资源 304 复用", st304 == 304, str(st304))

# ---------- 5) 版本号一致（server 与 manifest） ----------
mf = os.path.join(BASE, "vditor-fpk", "manifest")
ver_manifest = ""
with io.open(mf, encoding="utf-8") as f:
    for line in f:
        if line.startswith("version="):
            ver_manifest = line.strip().split("=", 1)[1]
            break
st, d, _, ck = req("POST", "/api/setup", {"password": "secret123"})
check("setup", st == 200 and d.get("ok"), str((st, d)))
st, raw, _, _ = req("GET", "/api/settings/export", cookie=ck, raw=True)
ver_app = json.loads(raw.decode()).get("version")
check("server 版本 == manifest 版本 (%s)" % ver_manifest, ver_app == ver_manifest, "%r vs %r" % (ver_app, ver_manifest))

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
shutil.rmtree(tmp, ignore_errors=True)
print("\nRESULT(pkg): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
