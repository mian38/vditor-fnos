# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""1.1.5 定向测试：/api/status、/api/app-log、会话失效 401。"""
import subprocess, sys, time, socket, os, json, shutil, urllib.request, urllib.error, http.cookiejar

PORT = 8947
ROOT = os.path.abspath("_t115")
shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(ROOT)
env = dict(os.environ, VDITOR_PORT=str(PORT),
           VDITOR_DOC_DIR=os.path.join(ROOT, "docs"),
           VDITOR_CONFIG=os.path.join(ROOT, "etc"))
p = subprocess.Popen([sys.executable, "server.py"], cwd="vditor-fpk/app", env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cj))
B = "http://127.0.0.1:%d" % PORT
ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  PASS %s" % name)
    else: fail += 1; print("  FAIL %s %s" % (name, extra))

try:
    for _ in range(80):
        try: socket.create_connection(("127.0.0.1", PORT), 0.3).close(); break
        except OSError: time.sleep(0.2)
    else:
        print("服务未启动"); sys.exit(1)

    def post(path, obj):
        d = json.dumps(obj).encode()
        rq = urllib.request.Request(B + path, data=d, headers={"Content-Type": "application/json"})
        return op.open(rq, timeout=10)
    def get(path):
        return op.open(B + path, timeout=10)

    print("--- 未登录应 401 ---")
    try:
        get("/api/status"); check("status 未登录拦截", False, "居然成功")
    except urllib.error.HTTPError as e:
        check("status 未登录返回 401", e.code == 401, "got %s" % e.code)
    try:
        get("/api/app-log"); check("app-log 未登录拦截", False, "居然成功")
    except urllib.error.HTTPError as e:
        check("app-log 未登录返回 401", e.code == 401, "got %s" % e.code)

    print("--- 设置密码并登录 ---")
    post("/api/setup", {"password": "test1234"})
    post("/api/logout", {})
    post("/api/login", {"password": "test1234"})

    print("--- /api/status ---")
    d = json.loads(get("/api/status").read().decode())
    check("含 app/network/security 三段", all(k in d for k in ("app","network","security")), str(list(d.keys())))
    # 版本号：与服务端 APP_VERSION 一致即可（不写死具体版本，避免每次升版假红）
    _mf = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "vditor-fpk", "manifest"), encoding="utf-8").read()
    import re as _re
    _mv = _re.search(r"(?m)^version\s*=\s*(\S+)\s*$", _mf)
    _vdef = _mv.group(1) if _mv else None
    check("app.version 与 manifest 一致", d["app"]["version"] == _vdef,
          "%s vs %s" % (d["app"]["version"], _vdef))
    check("app.port == %d" % PORT, d["app"]["port"] == PORT, str(d["app"]["port"]))
    check("uptime 存在且为数字", isinstance(d["app"]["uptime"], int))
    check("docRoots 为列表", isinstance(d["app"]["docRoots"], list) and len(d["app"]["docRoots"]) >= 1)
    check("docRoots 含 exists/writable", all("exists" in r and "writable" in r for r in d["app"]["docRoots"]))
    check("network 有 clientIp/proto", "clientIp" in d["network"] and "proto" in d["network"])
    check("security 有 hasSession", d["security"]["hasSession"] is True)
    check("不含敏感字段", not any(k in json.dumps(d) for k in ("pwhash","password","VDITOR_PWHASH")))

    print("--- /api/app-log ---")
    a = json.loads(get("/api/app-log").read().decode())
    check("含 exists/path/lines", all(k in a for k in ("exists","path","lines")))

    print("--- CSP ---")
    resp = get("/index.html")
    csp = resp.headers.get("Content-Security-Policy","")
    check("CSP 含 unsafe-eval", "'unsafe-eval'" in csp)
    check("CSP script-src 仍限 self", "script-src 'self'" in csp)

    print("--- graphviz 资源 ---")
    for path, mn in (("/vditor/dist/js/graphviz/viz.js", 1000),
                     ("/vditor/dist/js/graphviz/full.render.js", 100000)):
        b = get(path).read()
        check("%s 可访问" % path.split("/")[-1], len(b) >= mn, "%d bytes" % len(b))

    print("--- 前端控件存在性 ---")
    html = get("/index.html").read().decode("utf-8","replace")
    for cid in ("set-tabs","pg-about","btn-word-help","status-list","btn-refresh-status",
                "btn-view-app-log","session-mask","btn-session-reload",
                "about-version","btn-view-log"):
        check("含 #%s" % cid, ('id="%s"' % cid) in html)
    check("顶栏已无 btn-word-help 按钮", html.count('id="btn-word-help"') == 1)
    check("含 vditorGraphVizScript", "vditorGraphVizScript" in html)
    check("快捷键表 class=kb-list", "class=\"kb-list\"" in html)
    check("快捷键行>=12", html.count("<tr><td>") >= 12, str(html.count("<tr><td>")))
finally:
    p.terminate(); p.wait(timeout=10)
    shutil.rmtree(ROOT, ignore_errors=True)

print("\nRESULT(1.1.5): passed=%d failed=%d" % (ok, fail))
sys.exit(1 if fail else 0)
