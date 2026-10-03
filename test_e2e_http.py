#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_e2e_http.py —— 手段 B：真实 HTTP 端到端（模拟用户在浏览器中的全部操作）

启动真实后端服务，用 urllib 按浏览器实际会调用的 API 顺序逐一驱动：
  鉴权(setup/login/auth-check) → 状态 → 文件列表 → 新建/保存/读回(逐字节校验) →
  历史版本(存两版/列出版/回滚) → 设置读写 → 分区增删 → 备份下载 → 文档信息/资产 →
  登录日志/应用日志 → 登出 → 再次 auth-check 应为未登录
并在每轮校验 gzip 压缩对静态资源（index.html / lute.min.js）的实际生效。

每一轮都重新拉起一个全新的服务进程（临时配置 + 临时文档目录），
既能跑通完整链路，也能顺带验证「冷启动 → 就绪」路径在反复重启下的稳定性。

直接运行：python test_e2e_http.py [轮数默认=5]
"""
import os, sys, io, re, json, time, socket, tempfile, subprocess, hashlib, gzip
import urllib.request, urllib.error, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
MF = os.path.join(BASE, "vditor-fpk", "manifest")
SRV = os.path.join(APP, "server.py")
PY = sys.executable

def manifest_version():
    with io.open(MF, encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("version="):
                return ln.strip().split("=", 1)[1].strip()
    return ""
MV = manifest_version()
m = re.search(r'APP_VERSION = "([^"]+)"', io.open(SRV, encoding="utf-8").read())
SV = m.group(1) if m else ""

PW = "e2e-pass-1234"

passed = failed = 0
def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("  FAIL", name, extra)

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p

def req(url, method="GET", data=None, cookie=None, headers=None, accept_gzip=False):
    hdrs = dict(headers or {})
    if cookie:
        hdrs["Cookie"] = cookie
    if accept_gzip:
        hdrs["Accept-Encoding"] = "gzip"
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
        else:
            body = data if isinstance(data, bytes) else data.encode("utf-8")
    r = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        resp = urllib.request.urlopen(r, timeout=60)
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        # 透明解 gzip
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        ce = resp.headers.get("Content-Encoding", "")
        vary = resp.headers.get("Vary", "")
        return resp.status, raw, ctype, resp.headers, cookie
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            raw = gzip.decompress(raw) if e.headers.get("Content-Encoding","").lower()=="gzip" else raw
        except Exception:
            pass
        return e.code, raw, e.headers.get("Content-Type",""), e.headers, cookie

def run_once(round_no):
    global passed, failed
    port = free_port()
    tmp = tempfile.mkdtemp(prefix="vde2e_")
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
    try:
        ready = False
        for _ in range(80):
            try:
                if urllib.request.urlopen(URL + "/index.html", timeout=2).status == 200:
                    ready = True; break
            except Exception:
                pass
            if proc.poll() is not None:
                break
            time.sleep(0.25)
        check("[R%d] 服务冷启动就绪" % round_no, ready)
        if not ready:
            return

        # ---- gzip 校验：静态资源（比较「压缩后 Content-Length」与明文长度） ----
        st, raw, ct, h, _ = req(URL + "/index.html", accept_gzip=True)
        ce = h.get("Content-Encoding", "").lower()
        vary = h.get("Vary", "")
        gz_len = int(h.get("Content-Length") or 0)   # 压缩后字节数
        _, raw_plain, _, _, _ = req(URL + "/index.html")
        plain_len = len(raw_plain)
        check("[R%d] index.html gzip 生效(Content-Encoding=gzip)" % round_no, ce == "gzip", (st, ce))
        check("[R%d] index.html Vary: Accept-Encoding 已声明" % round_no, "accept-encoding" in vary.lower(), vary)
        check("[R%d] index.html gzip 实际压缩(%d<%d)" % (round_no, gz_len, plain_len),
              ce == "gzip" and gz_len < plain_len, "gz=%d plain=%d" % (gz_len, plain_len))

        st, raw, ct, h, _ = req(URL + "/vditor/dist/js/lute/lute.min.js", accept_gzip=True)
        ce = h.get("Content-Encoding", "").lower()
        gz_len2 = int(h.get("Content-Length") or 0)
        _, raw_plain, _, _, _ = req(URL + "/vditor/dist/js/lute/lute.min.js")
        plain_len2 = len(raw_plain)
        check("[R%d] lute.min.js gzip 生效" % round_no, ce == "gzip", (st, ce))
        check("[R%d] lute.min.js gzip 显著压缩(%d<%d)" % (round_no, gz_len2, plain_len2),
              ce == "gzip" and gz_len2 < plain_len2, "gz=%d plain=%d" % (gz_len2, plain_len2))

        # ---- 鉴权：未初始化时 setup/status ----
        st, d, _, _, _ = req(URL + "/api/setup/status")
        d = json.loads(d) if d else {}
        check("[R%d] 初始 needsSetup=true" % round_no, st == 200 and d.get("needsSetup") is True, (st, d))
        st, d, _, _, _ = req(URL + "/api/auth/check")
        d = json.loads(d) if d else {}
        check("[R%d] 初始未登录" % round_no, st == 200 and d.get("authenticated") is False, (st, d))

        # 密码过短应被拒
        st, d, _, _, _ = req(URL + "/api/setup", method="POST", data={"password": "123"})
        check("[R%d] 设置密码过短被拒(>=6)" % round_no, st == 400, st)
        # 正确设置
        st, d, _, h, _ = req(URL + "/api/setup", method="POST", data={"password": PW})
        d = json.loads(d) if d else {}
        ck = h.get("Set-Cookie")
        check("[R%d] 首次设置成功" % round_no, st == 200 and d.get("ok") is True, (st, d))
        check("[R%d] 设置后下发会话 Cookie" % round_no, bool(ck), ck)
        cookie = ck.split(";")[0] if ck else None

        # auth/check 现在应已登录
        st, d, _, _, _ = req(URL + "/api/auth/check", cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 设置后已处于登录态" % round_no, d.get("authenticated") is True, d)

        # 错误密码登录失败
        st, d, _, _, _ = req(URL + "/api/login", method="POST", data={"password": "wrong"})
        d = json.loads(d) if d else {}
        check("[R%d] 错误密码登录失败" % round_no, st == 401 and d.get("ok") is False, (st, d))
        # 正确密码登录
        st, d, _, h, _ = req(URL + "/api/login", method="POST", data={"password": PW})
        d = json.loads(d) if d else {}
        ck2 = h.get("Set-Cookie")
        check("[R%d] 正确密码登录成功" % round_no, st == 200 and d.get("ok") is True, (st, d))
        if ck2:
            cookie = ck2.split(";")[0]

        # ---- 状态 / 文件列表 ----
        st, d, _, _, _ = req(URL + "/api/status", cookie=cookie)
        d = json.loads(d) if d else {}
        sroots = d.get("app", {}).get("docRoots", [])
        check("[R%d] /api/status 返回版本与分区" % round_no,
              st == 200 and d.get("app", {}).get("version") == MV and len(sroots) >= 1, (st, MV, len(sroots)))

        st, d, _, _, _ = req(URL + "/api/files", cookie=cookie)
        d = json.loads(d) if d else {}
        roots = d.get("roots", [])
        check("[R%d] /api/files 返回分区(含 id)" % round_no, st == 200 and len(roots) >= 1, (st, len(roots)))
        rid = roots[0].get("id")
        check("[R%d] 默认分区 id 非空" % round_no, bool(rid), rid)

        st, d, _, _, _ = req(URL + "/api/files", cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] /api/files 返回 roots" % round_no, st == 200 and "roots" in d, st)

        # ---- 新建 / 保存 / 读回（逐字节） ----
        content = "# 端到端测试\n\n- 行1\n- 行2\n\n```python\nprint('hello')\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
        st, d, _, _, _ = req(URL + "/api/new", method="POST",
                             data={"root": rid, "path": "e2e_doc.md"}, cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 新建文档成功" % round_no, st == 200 and d.get("ok") is True, (st, d))
        st, d, _, _, _ = req(URL + "/api/save", method="POST",
                             data={"root": rid, "path": "e2e_doc.md", "content": content}, cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 保存文档成功" % round_no, st == 200 and d.get("ok") is True, (st, d))

        st, d, _, _, _ = req(URL + "/api/file?root=%s&path=%s" %
                             (urllib.parse.quote(rid), urllib.parse.quote("e2e_doc.md")), cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 读回文档逐字节一致" % round_no,
              st == 200 and d.get("content") == content, (st, "len=%d" % len(d.get("content",""))))

        # 大文档保存（4MB，触发历史版本）+ 读回
        big = ("# 大文档 %d\n\n" % round_no) + ("这是一段用来压测的中文内容 line-%d。\n" % round_no) * 60000
        big = (big + "```js\nconst x = %d;\n```\n" % round_no) * 1
        # 调整到约 4MB
        while len(big.encode("utf-8")) < 4 * 1024 * 1024:
            big += "追加压测行 %d：中文内容填充，确保体积达到 4MB 量级。\n" % round_no
        h_big = hashlib.sha256(big.encode("utf-8")).hexdigest()
        t0 = time.time()
        st, d, _, _, _ = req(URL + "/api/save", method="POST",
                             data={"root": rid, "path": "e2e_big.md", "content": big}, cookie=cookie)
        dt_save = time.time() - t0
        d = json.loads(d) if d else {}
        check("[R%d] 大文档(4MB)保存成功" % round_no, st == 200 and d.get("ok") is True, (st, d))
        t0 = time.time()
        st, d, _, _, _ = req(URL + "/api/file?root=%s&path=%s" %
                             (urllib.parse.quote(rid), urllib.parse.quote("e2e_big.md")), cookie=cookie)
        dt_read = time.time() - t0
        d = json.loads(d) if d else {}
        got = d.get("content", "")
        check("[R%d] 大文档(4MB)读回逐字节一致" % round_no,
              st == 200 and hashlib.sha256(got.encode("utf-8")).hexdigest() == h_big,
              (st, len(got)))
        print("    · 4MB 保存 %.0fms / 读取 %.0fms" % (dt_save * 1000, dt_read * 1000))

        # 再存一次（产生历史版本）
        st, d, _, _, _ = req(URL + "/api/save", method="POST",
                             data={"root": rid, "path": "e2e_doc.md", "content": content + "\n编辑第二版\n"}, cookie=cookie)
        st, d, _, _, _ = req(URL + "/api/versions?root=%s&path=%s" %
                             (urllib.parse.quote(rid), urllib.parse.quote("e2e_doc.md")), cookie=cookie)
        d = json.loads(d) if d else {}
        vers = d.get("versions", [])
        check("[R%d] 历史版本已记录(>=1)" % round_no, isinstance(vers, list) and len(vers) >= 1, (st, len(vers)))
        if vers:
            oldest = vers[-1]
            st, d, _, _, _ = req(URL + "/api/version/restore", method="POST",
                                 data={"root": rid, "path": "e2e_doc.md", "ts": oldest.get("ts")}, cookie=cookie)
            d = json.loads(d) if d else {}
            check("[R%d] 历史版本回滚成功" % round_no, st == 200 and d.get("ok") is True, (st, d))

        # ---- 设置读写 ----
        st, d, _, _, _ = req(URL + "/api/settings", method="POST",
                             data={"autosave_interval": 120, "versioning": True, "max_versions": 30}, cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 设置更新成功" % round_no, st == 200 and d.get("ok") is True, (st, d))
        st, d, _, _, _ = req(URL + "/api/settings", cookie=cookie)
        d = json.loads(d) if d else {}
        setd = d.get("settings", {})
        check("[R%d] 设置已持久化(autosave_interval=120)" % round_no,
              setd.get("autosave_interval") == 120, setd.get("autosave_interval"))
        # 非法范围应被夹取/拒绝
        st, d, _, _, _ = req(URL + "/api/settings", method="POST",
                             data={"autosave_interval": -5, "upload_max_mb": 9999}, cookie=cookie)
        d = json.loads(d) if d else {}
        setd = d.get("settings", {})
        check("[R%d] 非法设置被夹取到合法区间" % round_no,
              setd.get("autosave_interval") == 10 and setd.get("upload_max_mb") == 512, setd)

        # ---- 分区增删 ----
        new_dir = os.path.join(tmp, "extra")
        os.makedirs(new_dir, exist_ok=True)
        st, d, _, _, _ = req(URL + "/api/folders", method="POST",
                             data={"action": "add", "name": "临时分区", "path": new_dir}, cookie=cookie)
        d = json.loads(d) if d else {}
        roots2 = d.get("roots", [])
        check("[R%d] 新增分区生效" % round_no, st == 200 and any(r.get("id") for r in roots2) and len(roots2) >= 2, (st, len(roots2)))
        # 还原（移除）
        st, d, _, _, _ = req(URL + "/api/folders", method="POST",
                             data={"action": "remove", "path": new_dir}, cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 移除分区生效" % round_no, st == 200, (st, d.get("ok")))

        # ---- 备份下载 ----
        st, raw, ct, h, _ = req(URL + "/api/backup", cookie=cookie)
        check("[R%d] 备份下载成功(非空 zip/json)" % round_no, st == 200 and len(raw) > 0, (st, len(raw)))
        check("[R%d] 备份为附件下载" % round_no, "attachment" in h.get("Content-Disposition", ""), h.get("Content-Disposition"))

        # ---- 文档信息 / 资产 ----
        st, d, _, _, _ = req(URL + "/api/doc/info?root=%s&path=%s" %
                             (urllib.parse.quote(rid), urllib.parse.quote("e2e_doc.md")), cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 文档信息返回" % round_no, st == 200 and ("name" in d or "path" in d or "info" in d), (st, list(d.keys())[:5]))
        st, d, _, _, _ = req(URL + "/api/doc/assets?root=%s&path=%s" %
                             (urllib.parse.quote(rid), urllib.parse.quote("e2e_doc.md")), cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 文档资产列表返回" % round_no, st == 200, st)

        # ---- 日志 ----
        st, d, _, _, _ = req(URL + "/api/login-log", cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 登录日志返回" % round_no, st == 200 and "entries" in d, st)
        st, d, _, _, _ = req(URL + "/api/app-log", cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 应用日志返回" % round_no, st == 200, st)

        # ---- 静态安全：源码/配置不可外泄 ----
        for denied in ("/server.py", "/vd_util.py", "/config.env", "/manifest"):
            st, _, _, _, _ = req(URL + denied)
            check("[R%d] 静态白名单拦截 %s (404/403)" % (round_no, denied), st in (403, 404), st)

        # ---- 登出 ----
        st, d, _, _, _ = req(URL + "/api/logout", method="POST", cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 登出成功" % round_no, st == 200 and d.get("ok") is True, (st, d))
        st, d, _, _, _ = req(URL + "/api/auth/check", cookie=cookie)
        d = json.loads(d) if d else {}
        check("[R%d] 登出后再次 auth/check 为未登录" % round_no, d.get("authenticated") is False, d)

    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            try: proc.kill()
            except Exception: pass
        # 清理临时目录
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass

def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    global_start = time.time()
    for r in range(1, rounds + 1):
        print("======== 手段B 第 %d/%d 轮 ========" % (r, rounds))
        run_once(r)
    dt = time.time() - global_start
    print("\nRESULT e2e_http passed=%d failed=%d rounds=%d time=%.1fs version=%s" %
          (passed, failed, rounds, dt, MV))
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
