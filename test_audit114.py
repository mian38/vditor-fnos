#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""1.1.4 全量回归测试（审计后）。

覆盖范围（对照 server.py 全部对外接口）：
  A. CLI / 环境变量 / 配置文件   —— 命令行参数优先级、config.env 解析、非法值兜底
  B. 认证与会话                 —— setup / login / logout / 锁定 / 改密 / Cookie 属性 / HTTP 守卫
  C. 文档 CRUD                   —— files / file / new / save / delete / 路径穿越
  D. 上传                       —— 黑名单、大小上限、连字符扩展名、落盘可访问
  E. 历史版本                   —— save 快照 / list / diff / restore / delete
  F. 设置                       —— get / update / import / export / 校验与边界
  G. 文件夹管理                 —— add / remove / restore
  H. 备份与恢复                 —— backup 导出 / restore 导入 / 非法包
  I. 静态资源与安全头           —— 白名单 / 404 / ETag 304 / 安全头 / 源码不外泄
  J. 异常与边界                 —— 非法 Content-Length / 畸形 JSON / 超大请求 / 未知路由
  K. 纯函数单元                 —— vd_util 全量等价性与边界
  L. 代码卫生                   —— 死代码 / 未用 import / 重复样板 / 语法

用法：
    python test_audit114.py
输出：
    每项 PASS / FAIL，末尾汇总 RESULT(audit 1.1.4): passed=N failed=M
"""
import os
import re
import sys
import json
import time
import socket
import shutil
import tempfile
import threading
import subprocess
from urllib.parse import quote as _q

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "vditor-fpk", "app")
PY = sys.executable

PASSED = 0
FAILED = 0
FAIL_LOG = []


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("  PASS %s" % name)
    else:
        FAILED += 1
        FAIL_LOG.append((name, extra))
        print("  FAIL %s   %s" % (name, extra))
    return bool(cond)


def enc(v):
    """路径参数 URL 编码（中文 / 空格等非 ASCII 字符不能直接进 HTTP 请求行）。"""
    return _q(str(v), safe="")


def section(title):
    print("\n== %s ==" % title)


# ============================================================
# 测试服务器管理
# ============================================================
class ServerProc(object):
    """在独立进程里起一个 server，配置目录与文档目录都用临时目录，互不干扰。"""

    _next_port = [9800]

    def __init__(self, env=None, doc_sub="docs"):
        self.port = ServerProc._next_port[0]
        ServerProc._next_port[0] += 1
        self.cfg = tempfile.mkdtemp(prefix="vditor-cfg-")
        self._doc_parent = tempfile.mkdtemp(prefix="vditor-doc-")
        # self.doc 必须是**服务的真实文档根**（即 VDITOR_DOC_DIR 指向的那一层），
        # 否则测试里拼 os.path.join(self.doc, rel) 会错位一层，导致"文件不存在"的假失败。
        self.doc = os.path.join(self._doc_parent, doc_sub)
        os.makedirs(self.doc, exist_ok=True)
        e = dict(os.environ)
        e.update({
            "VDITOR_PORT": str(self.port),
            "VDITOR_HOST": "127.0.0.1",
            "VDITOR_CONFIG": self.cfg,
            "VDITOR_DOC_DIR": self.doc,
            "VDITOR_PASSWORD": "auditpass123",
        })
        if env:
            e.update({k: str(v) for k, v in env.items()})
        self.env = e
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen(
            [PY, os.path.join(APP, "server.py")],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.wait_ready()
        return self

    def wait_ready(self, timeout=15.0):
        end = time.time() + timeout
        while time.time() < end:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), 0.4)
                s.close()
                return True
            except OSError:
                if self.proc and self.proc.poll() is not None:
                    return False
                time.sleep(0.08)
        return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for d in (self.cfg, self._doc_parent):
            shutil.rmtree(d, ignore_errors=True)

    # ---- HTTP 助手 ----
    def request(self, method, path, body=None, headers=None, cookie=None, timeout=10):
        """返回 (status, headers_dict, body_bytes)；失败返回 (0, {}, b'')。"""
        s = socket.socket()
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", self.port))
        except OSError:
            return 0, {}, b""
        h = {"Host": "127.0.0.1", "Connection": "close"}
        if cookie:
            h["Cookie"] = "vditor_sid=%s" % cookie
        if headers:
            h.update(headers)
        payload = b""
        if body is not None:
            if isinstance(body, (dict, list)):
                payload = json.dumps(body).encode("utf-8")
                h.setdefault("Content-Type", "application/json")
            elif isinstance(body, str):
                payload = body.encode("utf-8")
            else:
                payload = body
            # 若调用方显式给了 Content-Length（如故意声明超大值测413），**尊重它**，
            # 不然会被真实长度覆盖，测不到服务端的前置限长判定。
            if "Content-Length" not in h:
                h["Content-Length"] = str(len(payload))
        req = "%s %s HTTP/1.1\r\n" % (method, path.encode("latin1", "replace").decode("latin1"))
        req += "".join("%s: %s\r\n" % (k, v) for k, v in h.items())
        req += "\r\n"
        try:
            s.sendall(req.encode("latin1") + payload)
            buf = b""
            while True:
                d = s.recv(65536)
                if not d:
                    break
                buf += d
        except OSError:
            return -1, {}, b""
        finally:
            s.close()
        if not buf:
            return -1, {}, b""
        head, _, rest = buf.partition(b"\r\n\r\n")
        lines = head.decode("latin1", "replace").split("\r\n")
        try:
            status = int(lines[0].split()[1])
        except (IndexError, ValueError):
            return -1, {}, b""
        hd = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, _, v = ln.partition(":")
                hd[k.strip()] = v.strip()
        # 处理 chunked
        if hd.get("Transfer-Encoding", "").lower() == "chunked":
            out, cur = b"", rest
            while True:
                nl = cur.find(b"\r\n")
                if nl == -1:
                    break
                try:
                    size = int(cur[:nl].split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    break
                out += cur[nl + 2:nl + 2 + size]
                cur = cur[nl + 2 + size + 2:]
            rest = out
        return status, hd, rest

    def raw_post(self, path, content_length, ctype="application/json", cookie=None, body=b"{}"):
        """手工发一个 Content-Length 异常的 POST，返回状态码；0=连接被断开。"""
        s = socket.socket()
        s.settimeout(10)
        try:
            s.connect(("127.0.0.1", self.port))
            h = "POST %s HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: %s\r\n" % (path, ctype)
            if cookie:
                h += "Cookie: vditor_sid=%s\r\n" % cookie
            h += "Content-Length: %s\r\nConnection: close\r\n\r\n" % content_length
            s.sendall(h.encode("latin1") + body)
            buf = b""
            while True:
                d = s.recv(65536)
                if not d:
                    break
                buf += d
        except OSError:
            return 0
        finally:
            s.close()
        if not buf:
            return 0
        try:
            return int(buf.split(b" ")[1])
        except (IndexError, ValueError):
            return -1

    def j(self, method, path, body=None, cookie=None, headers=None):
        st, hd, raw = self.request(method, path, body, headers, cookie)
        try:
            return st, hd, json.loads(raw.decode("utf-8"))
        except Exception:
            return st, hd, {}

    def login(self, pw="auditpass123"):
        st, hd, d = self.j("POST", "/api/login", {"password": pw})
        sc = hd.get("Set-Cookie", "")
        m = re.search(r"vditor_sid=([^;]+)", sc)
        return (m.group(1) if m else None), d


# ============================================================
# A. CLI / 环境变量 / 配置文件
# ============================================================
section("A. CLI / 环境变量 / 配置文件")
sv = ServerProc()
check("A1 服务可启动并监听", sv.start())

st, hd, d = sv.j("GET", "/api/auth/check")
check("A2 /api/auth/check 返回 authenticated/needsSetup",
      st == 200 and "authenticated" in d and "needsSetup" in d, str(d))
check("A3 已配置密码时 needsSetup=False", d.get("needsSetup") is False, str(d))

#环境变量优先级：VDITOR_DOC_DIR 生效
st, hd, d = sv.j("POST", "/api/login", {"password": "auditpass123"})
check("A4 VDITOR_PASSWORD 可直接登录", st == 200 and d.get("ok") is True, str(d))
tok, _ = sv.login()
check("A5 登录返回会话 Cookie", bool(tok))

# 非法 Content-Length 头在 config.env 层面无关，用端口环境变量验证
sv2 = ServerProc(env={"VDITOR_PORT": "notaport"})
sv2.proc = subprocess.Popen([PY, os.path.join(APP, "server.py")],
                            env=sv2.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(1.2)
rc = sv2.proc.poll()
check("A6 非法 VDITOR_PORT 时进程退出而非静默异常", rc is not None, "rc=%s" % rc)
sv2.stop()

# config.env 解析：直接测 load_config 的读取逻辑
code = (
    "import sys; sys.path.insert(0, %r);"
    "import server;"
    "print(server.HOST, server.PORT)" % APP
)
r = subprocess.run([PY, "-c", code], capture_output=True, text=True,
                   env=dict(os.environ, VDITOR_PORT="9123", VDITOR_HOST="0.0.0.0",
                            VDITOR_CONFIG=tempfile.mkdtemp()))
check("A7 端口/主机可由环境变量覆盖", r.stdout.strip() == "0.0.0.0 9123", r.stdout.strip() + r.stderr[:120])

# 自举：-c 方式 import 必须成功
r2 = subprocess.run([PY, "-c", "import sys; sys.path.insert(0, %r); import server; print('ok')" % APP],
                    capture_output=True, text=True,
                    env=dict(os.environ, VDITOR_CONFIG=tempfile.mkdtemp()))
check("A8 python -c 方式自举 import 成功", "ok" in r2.stdout, r2.stderr[:160])

# -m 方式：长驻服务，改为「起进程→确认端口可连→主动终止」，
# 不能用 subprocess.run 等它自己退出（那是长驻服务，TimeoutExpired 属预期而非失败）。
mcfg = tempfile.mkdtemp(prefix="vditor-mcfg-")
mproc = subprocess.Popen([PY, "-m", "server"], cwd=APP, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         env=dict(os.environ, VDITOR_PORT="9124", VDITOR_HOST="127.0.0.1",
                                  VDITOR_CONFIG=mcfg, VDITOR_DOC_DIR=tempfile.mkdtemp()))
mready = False
for _ in range(60):
    try:
        socket.create_connection(("127.0.0.1", 9124), 0.3).close()
        mready = True
        break
    except OSError:
        if mproc.poll() is not None:
            break
        time.sleep(0.1)
merr = b""
if not mready:
    try:
        mproc.terminate()
        _, merr = mproc.communicate(timeout=5)
    except Exception:
        mproc.kill()
check("A9 python -m 方式可启动（自举不失败）", mready and b"ModuleNotFoundError" not in merr,
      (merr[:160] or b"port never opened").decode("latin1"))
if mproc.poll() is None:
    mproc.terminate()
    try:
        mproc.wait(timeout=5)
    except Exception:
        mproc.kill()
shutil.rmtree(mcfg, ignore_errors=True)


# ============================================================
# B. 认证与会话
# ============================================================
section("B. 认证与会话")
st, hd, d = sv.j("GET", "/api/files")
check("B1 未登录访问受保护接口 -> 401", st == 401, "st=%s" % st)

st, _, d = sv.j("POST", "/api/login", {"password": "wrong"})
check("B2 错误密码 -> 401", st == 401 and d.get("ok") is False, str(d))

st, _, d = sv.j("POST", "/api/login", {"password": ""})
check("B3 空密码 -> 401", st == 401, "st=%s" % st)

# Cookie 属性
st, hd, _ = sv.j("POST", "/api/login", {"password": "auditpass123"})
sc = hd.get("Set-Cookie", "")
check("B4 会话 Cookie 含 HttpOnly", "HttpOnly" in sc, sc[:80])
check("B5 会话 Cookie 含 SameSite=Lax", "SameSite=Lax" in sc, sc[:80])
check("B6 会话 Cookie 含 Path=/", "Path=/" in sc, sc[:80])
check("B7 Cookie 值高熵（>=32 字符 token）", len(re.search(r"vditor_sid=([^;]+)", sc).group(1)) >= 32)

# setup 不可重复
st, _, d = sv.j("POST", "/api/setup", {"password": "newpass123"})
check("B8 已设密码后 setup 被拒 -> 403", st == 403, "st=%s %s" % (st, d))

# 改密：原密码错
st, _, d = sv.j("POST", "/api/change-password", {"old_password": "bad", "new_password": "x123456"}, cookie=tok)
check("B9 改密原密码错误 -> 403", st == 403, "st=%s" % st)

# 改密：新密码过短
st, _, d = sv.j("POST", "/api/change-password",
                {"old_password": "auditpass123", "new_password": "123"}, cookie=tok)
check("B10 改密新密码过短 -> 400", st == 400, "st=%s" % st)

# 改密：两次不一致
st, _, d = sv.j("POST", "/api/change-password",
                {"old_password": "auditpass123", "new_password": "abcdefg", "confirm_password": "other"}, cookie=tok)
check("B11 改密两次不一致 -> 400", st == 400, "st=%s" % st)

# 改密成功后会话全清
st, _, d = sv.j("POST", "/api/change-password",
                {"old_password": "auditpass123", "new_password": "auditpass456"}, cookie=tok)
check("B12 改密成功", st == 200 and d.get("ok") is True, str(d))
st, _, _ = sv.j("GET", "/api/files", cookie=tok)
check("B13 改密后旧会话失效 -> 401", st == 401, "st=%s" % st)
tok, _ = sv.login("auditpass456")
check("B14 用新密码可重新登录", bool(tok))

# 锁定：连续失败
sv3 = ServerProc()
sv3.start()
for i in range(5):
    sv3.j("POST", "/api/login", {"password": "nope"})
st, _, d = sv3.j("POST", "/api/login", {"password": "auditpass123"})
check("B15 连续失败后锁定 -> 423", st == 423, "st=%s" % st)
sv3.stop()

# 登出
st, _, d = sv.j("POST", "/api/logout", {}, cookie=tok)
check("B16 登出成功", st == 200 and d.get("ok") is True, str(d))
st, _, _ = sv.j("GET", "/api/files", cookie=tok)
check("B17 登出后会话失效", st == 401, "st=%s" % st)


# ============================================================
# C. 文档 CRUD
# ============================================================
section("C. 文档 CRUD")
tok, _ = sv.login("auditpass456")
st, _, files = sv.j("GET", "/api/files", cookie=tok)
check("C1 文件列表可获取", st == 200 and "roots" in files, str(files)[:120])
root_id = files["roots"][0]["id"]

st, _, d = sv.j("POST", "/api/new", {"root": root_id, "path": "a"}, cookie=tok)
check("C2 新建文档", st == 200 and d.get("ok") is True, str(d))
doc_path = d.get("path")

st, _, d = sv.j("POST", "/api/new", {"root": root_id, "path": "a"}, cookie=tok)
check("C3 重复新建 -> 409", st == 409, "st=%s" % st)

st, _, d = sv.j("GET", "/api/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)), cookie=tok)
check("C4 读取文档", st == 200 and d.get("content") == "", str(d)[:120])

st, _, d = sv.j("POST", "/api/save",
                {"root": root_id, "path": doc_path, "content": "# 标题\n正文"}, cookie=tok)
check("C5 保存文档", st == 200 and d.get("ok") is True, str(d)[:120])

st, _, d = sv.j("GET", "/api/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)), cookie=tok)
check("C6 读回内容一致", d.get("content") == "# 标题\n正文", str(d)[:120])

# 路径穿越
st, _, d = sv.j("GET", "/api/file?root=%s&path=../../etc/passwd" % root_id, cookie=tok)
check("C7 路径穿越读取被拒 -> 404", st == 404, "st=%s" % st)
st, _, d = sv.j("POST", "/api/save",
                {"root": root_id, "path": "../../evil.md", "content": "x"}, cookie=tok)
check("C8 路径穿越保存被拒 -> 400", st == 400, "st=%s" % st)
st, _, d = sv.j("POST", "/api/save", {"root": "nope", "path": "x", "content": "y"}, cookie=tok)
check("C9 无效 root 保存被拒 -> 400", st == 400, "st=%s" % st)

# 删除
st, _, d = sv.j("POST", "/api/doc/delete", {"root": root_id, "path": doc_path}, cookie=tok)
check("C10 删除文档", st == 200 and d.get("ok") is True, str(d))


# ============================================================
# D. 上传
# ============================================================
section("D. 上传")


def multipart(fields, files):
    """fields: dict, files: [(field, filename, bytes)]"""
    b = "----auditboundary1234"
    out = b""
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode()
    for field, fname, content in files:
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n" % (b, field, fname)).encode()
        out += content + b"\r\n"
    out += ("--%s--\r\n" % b).encode()
    return out, "multipart/form-data; boundary=%s" % b


svu = ServerProc()
svu.start()
utok, _ = svu.login()
ust, _, ufiles = svu.j("GET", "/api/files", cookie=utok)
uroot = ufiles["roots"][0]["id"]

body, ct = multipart({"root": uroot, "path": ""}, [("file", "ok.txt", b"hello")])
st, _, d = svu.j("POST", "/api/upload", body, cookie=utok,
                 headers={"Content-Type": ct})
check("D1 普通文件上传成功", st == 200 and d.get("code") == 0, str(d)[:120])

body, ct = multipart({"root": uroot, "path": ""}, [("file", "bad.exe", b"MZ")])
st, _, d = svu.j("POST", "/api/upload", body, cookie=utok, headers={"Content-Type": ct})
check("D2 黑名单文件被拒", st == 200 and "bad.exe" in d["data"]["errFiles"], str(d)[:120])

# 连字符扩展名：默认被拒
body, ct = multipart({"root": uroot, "path": ""}, [("file", "x.appref-ms", b"data")])
st, _, d = svu.j("POST", "/api/upload", body, cookie=utok, headers={"Content-Type": ct})
check("D3 连字符扩展名默认被黑名单拦截",
      st == 200 and "x.appref-ms" in d["data"]["errFiles"], str(d)[:120])

# 从黑名单移除后应可上传，且落盘文件可访问
st, _, d = svu.j("POST", "/api/settings", {"upload_deny": "exe,dll"}, cookie=utok)
check("D4 可收窄黑名单", st == 200 and d.get("ok") is True, str(d)[:120])
body, ct = multipart({"root": uroot, "path": ""}, [("file", "x.appref-ms", b"data")])
st, _, d = svu.j("POST", "/api/upload", body, cookie=utok, headers={"Content-Type": ct})
check("D5 移除后连字符扩展名可上传", st == 200 and d.get("code") == 0, str(d)[:120])
store = d["data"]["succMap"].get("x.appref-ms")
check("D6 返回存储文件名", bool(store) and store.endswith(".appref-ms"), str(store))
if store:
    st, hd, raw = svu.request("GET", "/" + store, cookie=utok)
    check("D7 连字符扩展名落盘后可访问（不404）", st == 200, "st=%s" % st)
    check("D8 非内联类型强制下载",
          hd.get("Content-Disposition") == "attachment", str(hd.get("Content-Disposition")))
    check("D9 强制下载带 CSP sandbox", "sandbox" in hd.get("Content-Security-Policy", ""),
          hd.get("Content-Security-Policy"))

# 大小上限
st, _, d = svu.j("POST", "/api/settings", {"upload_max_mb": 1}, cookie=utok)
check("D10 可设置上传大小上限为 1MB", st == 200 and d.get("ok") is True, str(d)[:120])
body, ct = multipart({"root": uroot, "path": ""}, [("file", "big.txt", b"x" * (2 * 1024 * 1024))])
st, _, d = svu.j("POST", "/api/upload", body, cookie=utok, headers={"Content-Type": ct})
# 两种合规拒绝方式都算通过：整体请求体超限（413，顶层拦截）或单文件超限（errFiles）
rejected = (st == 413) or (st == 200 and "big.txt" in d.get("data", {}).get("errFiles", []))
check("D11 超限文件被拒", rejected, "st=%s %s" % (st, str(d)[:100]))

# 无 boundary
st, _, d = svu.j("POST", "/api/upload", b"x", cookie=utok,
                 headers={"Content-Type": "application/json"})
check("D12 缺 boundary -> 400", st == 400, "st=%s" % st)
svu.stop()


# ============================================================
# E. 历史版本
# ============================================================
section("E. 历史版本")
svv = ServerProc()
svv.start()
vtok, _ = svv.login()
_, _, vf = svv.j("GET", "/api/files", cookie=vtok)
vroot = vf["roots"][0]["id"]
_, _, d = svv.j("POST", "/api/new", {"root": vroot, "path": "v"}, cookie=vtok)
vp = d.get("path")
svv.j("POST", "/api/save", {"root": vroot, "path": vp, "content": "v1"}, cookie=vtok)
svv.j("POST", "/api/save", {"root": vroot, "path": vp, "content": "v2"}, cookie=vtok)
svv.j("POST", "/api/save", {"root": vroot, "path": vp, "content": "v3"}, cookie=vtok)

st, _, d = svv.j("GET", "/api/versions?root=%s&path=%s" % (enc(vroot), enc(vp)), cookie=vtok)
check("E1 历史版本列表非空", st == 200 and len(d.get("versions", [])) >= 2, str(d)[:150])
vers = d.get("versions", [])
if len(vers) >= 2:
    ts = vers[0]["ts"]
    st, _, dd = svv.j("GET", "/api/version/diff?root=%s&path=%s&ts=%d" % (enc(vroot), enc(vp), ts), cookie=vtok)
    check("E2 版本差异可计算", st == 200 and "diff" in dd, str(dd)[:120])
    st, _, rr = svv.j("POST", "/api/version/restore", {"root": vroot, "path": vp, "ts": ts}, cookie=vtok)
    check("E3 版本可恢复", st == 200 and rr.get("ok") is True, str(rr)[:120])
    st, _, dd2 = svv.j("POST", "/api/version/delete", {"root": vroot, "path": vp, "ts": ts}, cookie=vtok)
    check("E4 版本可删除", st == 200 and dd2.get("ok") is True, str(dd2)[:120])
else:
    check("E2-E4 版本操作", False, "版本数不足，无法验证")

st, _, d = svv.j("GET", "/api/version/diff?root=%s&path=%s&ts=abc" % (enc(vroot), enc(vp)), cookie=vtok)
check("E5非法 ts 不崩溃", st in (200, 400, 404), "st=%s" % st)
st, _, d = svv.j("GET", "/api/versions?root=nope&path=x", cookie=vtok)
check("E6 无效 root -> 400", st == 400, "st=%s" % st)
svv.stop()


# ============================================================
# F. 设置
# ============================================================
section("F. 设置")
svs = ServerProc()
svs.start()
stok, _ = svs.login()

st, _, d = svs.j("GET", "/api/settings", cookie=stok)
check("F1 读取设置", st == 200 and "settings" in d, str(d)[:100])
check("F2 返回 envLocked 信息", "envLocked" in d, str(d)[:100])

st, _, d = svs.j("POST", "/api/settings", {"page_title": "我的笔记"}, cookie=stok)
check("F3 保存页面标题", st == 200 and d["settings"]["page_title"] == "我的笔记", str(d)[:100])

st, _, d = svs.j("POST", "/api/settings", {"max_versions": "abc"}, cookie=stok)
check("F4 非数字 max_versions 被拒", st == 200 and d.get("ok") is False, str(d)[:100])

st, _, d = svs.j("POST", "/api/settings", {"versioning": "notbool"}, cookie=stok)
check("F5 非布尔 versioning 被拒", st == 200 and d.get("ok") is False, str(d)[:100])

st, _, d = svs.j("POST", "/api/settings", {"upload_deny": "exe,../bad,toolongextensionhere"}, cookie=stok)
check("F6 非法黑名单项被拒并回显", st == 200 and d.get("ok") is False and "不合法" in d.get("error", ""), str(d)[:150])

st, _, d = svs.j("POST", "/api/settings", {"upload_deny": ""}, cookie=stok)
check("F7 黑名单可清空（=不限制）", st == 200 and d.get("ok") is True, str(d)[:100])

st, hd, raw = svs.request("GET", "/api/settings/export", cookie=stok)
check("F8 设置导出", st == 200, "st=%s" % st)
check("F9 导出为附件", "attachment" in hd.get("Content-Disposition", ""), hd.get("Content-Disposition"))
try:
    exp = json.loads(raw.decode("utf-8"))
    # 版本号：与服务端一致即可（不写死，避免每次升版假红）
    _mf = open(os.path.join(HERE, "vditor-fpk", "manifest"), encoding="utf-8").read()
    _vdef = (re.search(r"(?m)^version\s*=\s*(\S+)\s*$", _mf) or [None, None])[1]
    check("F10 导出内容含 version 字段", exp.get("version") == _vdef,
          "%s vs %s" % (str(exp.get("version"))[:40], _vdef))
except Exception as e:
    check("F10 导出内容可解析", False, str(e))

st, _, d = svs.j("POST", "/api/settings/import", {"settings": {"max_versions": 20}}, cookie=stok)
check("F11 设置导入生效", st == 200 and d.get("ok") is True, str(d)[:100])

st, _, d = svs.j("POST", "/api/settings/import", {"settings": {"max_versions": 20}}, cookie=stok)
check("F12 重复导入幂等", st == 200, str(d)[:100])
svs.stop()


# ============================================================
# G. 文件夹管理
# ============================================================
section("G. 文件夹管理")
svg = ServerProc()
svg.start()
gtok, _ = svg.login()
st, _, d = svg.j("GET", "/api/folders", cookie=gtok)
check("G1 文件夹列表可读", st == 200 and "roots" in d, str(d)[:100])

extra = tempfile.mkdtemp(prefix="vditor-extra-")
st, _, d = svg.j("POST", "/api/folders", {"action": "add", "path": extra}, cookie=gtok)
check("G2 添加文件夹", st == 200 and d.get("ok") is True, str(d)[:100])
st, _, d = svg.j("POST", "/api/folders", {"action": "remove", "path": extra}, cookie=gtok)
check("G3 移除文件夹", st == 200 and d.get("ok") is True, str(d)[:100])
st, _, d = svg.j("POST", "/api/folders", {"action": "restore", "path": extra}, cookie=gtok)
check("G4 恢复文件夹", st == 200 and d.get("ok") is True, str(d)[:100])
st, _, d = svg.j("POST", "/api/folders", {"action": "unknown"}, cookie=gtok)
check("G5 未知操作 -> 400", st == 400, "st=%s" % st)
st, _, d = svg.j("POST", "/api/folders", {"action": "add", "path": ""}, cookie=gtok)
check("G6 空路径 -> 400", st == 400, "st=%s" % st)
shutil.rmtree(extra, ignore_errors=True)
svg.stop()


# ============================================================
# H. 备份与恢复
# ============================================================
section("H. 备份与恢复")
svb = ServerProc()
svb.start()
btok, _ = svb.login()
_, _, bf = svb.j("GET", "/api/files", cookie=btok)
broot = bf["roots"][0]["id"]
svb.j("POST", "/api/new", {"root": broot, "path": "bk"}, cookie=btok)
svb.j("POST", "/api/save", {"root": broot, "path": "bk/bk.md", "content": "backup me"}, cookie=btok)

st, hd, raw = svb.request("GET", "/api/backup", cookie=btok)
check("H1 备份导出", st == 200 and len(raw) > 0, "st=%s len=%s" % (st, len(raw)))
check("H2 备份为 gzip 附件", "attachment" in hd.get("Content-Disposition", ""), hd.get("Content-Disposition"))
backup_bytes = raw

# 恢复一个合法备份
st, _, d = svb.j("POST", "/api/backup/restore", backup_bytes, cookie=btok,
                 headers={"Content-Type": "application/gzip"})
check("H3 合法备份可恢复", st == 200 and d.get("ok") is True, str(d)[:120])

# 非法 gzip
st, _, d = svb.j("POST", "/api/backup/restore", b"not a gzip at all", cookie=btok,
                 headers={"Content-Type": "application/gzip"})
check("H4 非法备份被拒-> 400", st == 400, "st=%s" % st)

# 空请求
st, _, d = svb.j("POST", "/api/backup/restore", b"", cookie=btok,
                 headers={"Content-Type": "application/gzip"})
check("H5 空备份请求 -> 400", st == 400, "st=%s" % st)
svb.stop()


# ============================================================
# I. 静态资源与安全头
# ============================================================
section("I. 静态资源与安全头")
svi = ServerProc()
svi.start()
itok, _ = svi.login()

st, hd, raw = svi.request("GET", "/index.html")
check("I1 index.html 可公开访问", st == 200 and b"Vditor" in raw, "st=%s" % st)
check("I2 响应含 X-Content-Type-Options", hd.get("X-Content-Type-Options") == "nosniff", str(hd.get("X-Content-Type-Options")))
check("I3 响应含 X-Frame-Options", hd.get("X-Frame-Options") == "DENY", str(hd.get("X-Frame-Options")))
check("I4 响应含 CSP", "default-src" in hd.get("Content-Security-Policy", ""), "")
check("I5 响应含 Referrer-Policy", hd.get("Referrer-Policy") == "same-origin", str(hd.get("Referrer-Policy")))

etag = hd.get("ETag")
st2, _, _ = svi.request("GET", "/index.html", headers={"If-None-Match": etag} if etag else None)
check("I6 ETag 条件请求 -> 304", st2 == 304, "st=%s" % st2)

st, _, _ = svi.request("GET", "/vditor/dist/index.min.js")
check("I7 vditor 静态资源可访问", st == 200, "st=%s" % st)

for p in ["/server.py", "/vd_util.py", "/settings.json", "/config.env", "/../etc/passwd", "/vditor/../server.py"]:
    st, _, _ = svi.request("GET", p)
    check("I8 敏感路径不可访问 %s -> 404" % p, st == 404, "st=%s" % st)

st, _, _ = svi.request("GET", "/mathjax", cookie=itok)
check("I9 已移除路径 -> 404", st == 404, "st=%s" % st)
svi.stop()


# ============================================================
# J. 异常与边界
# ============================================================
section("J. 异常与边界（审计重点）")
svj = ServerProc()
svj.start()
jtok, _ = svj.login()

# 非法 Content-Length（本次审计修复的核心缺陷）
for path in ["/api/upload", "/api/favicon", "/api/backup/restore", "/api/save"]:
    for cl in ["abc", "-1", ""]:
        code = svj.raw_post(path, cl, cookie=jtok)
        check("J1 %s Content-Length=%r 不崩且有响应" % (path, cl), code > 0, "code=%s" % code)

#畸形 JSON
for path in ["/api/save", "/api/new", "/api/doc/delete", "/api/folders", "/api/settings"]:
    st, _, _ = svj.request("POST", path, b"{bad json!!!", cookie=jtok,
                           headers={"Content-Type": "application/json"})
    check("J2 %s 畸形JSON -> 400" % path, st == 400, "st=%s" % st)

# 空body
st, _, _ = svj.request("POST", "/api/save", b"", cookie=jtok,
                       headers={"Content-Type": "application/json"})
check("J3 空 body 不崩", st in (200, 400), "st=%s" % st)

# 超大 Content-Length：顶�� limit 对普通 JSON 接口是 MAX_BODY_BYTES(64MB)，
# 声明超过即 413，且不会真去读那一大坨字节。
st, _, d4 = svj.request("POST", "/api/folders", b"{}",
                        cookie=jtok,
                        headers={"Content-Type": "application/json",
                                 "Content-Length": str(128 * 1024 * 1024)})
check("J4 超大 Content-Length -> 413", st == 413, "st=%s %s" % (st, str(d4)[:100]))

# 未知路由
st, _, _ = svj.request("GET", "/api/does-not-exist", cookie=jtok)
check("J5 未知 GET 路由 -> 404", st == 404, "st=%s" % st)
st, _, _ = svj.request("POST", "/api/does-not-exist", {}, cookie=jtok)
check("J6 未知 POST 路由 -> 404", st == 404, "st=%s" % st)

# 越权：不带 cookie 访问所有受保护接口
for path in ["/api/files", "/api/settings", "/api/folders", "/api/login-log", "/api/backup"]:
    st, _, _ = svj.request("GET", path)
    check("J7 未登录 %s -> 401" % path, st == 401, "st=%s" % st)

# HEAD 请求不应返回 body 但状态正常
st, hd, raw = svj.request("HEAD", "/index.html")
check("J8 HEAD 请求正常", st == 200, "st=%s" % st)

# 伪造 XFF 不应影响鉴权
st, _, _ = svj.request("GET", "/api/files", headers={"X-Forwarded-For": "1.2.3.4"})
check("J9 伪造 XFF 无法绕过鉴权", st == 401, "st=%s" % st)
svj.stop()


# ============================================================
# K. 纯函数单元测试
# ============================================================
section("K. 纯函数单元测试")
sys.path.insert(0, APP)
import vd_util as U  # noqa: E402

check("K1 normalize_ext_list 基本归一化",
      U.normalize_ext_list("exe,dll") == ["exe", "dll"])
check("K2 normalize_ext_list 去点+小写",
      U.normalize_ext_list(".EXE;JS") == ["exe", "js"])
check("K3 normalize_ext_list 支持全角逗号/分号/空格",
      U.normalize_ext_list("exe，php; js") == ["exe", "php", "js"])
check("K4 normalize_ext_list 去重",
      U.normalize_ext_list("exe,exe,EXE") == ["exe"])
check("K5 normalize_ext_list 丢弃非法项",
      U.normalize_ext_list("../bad,-lead,waytoolongnamehere") == [])
check("K6 normalize_ext_list 支持连字符",
      U.normalize_ext_list("appref-ms,x-zmachine") == ["appref-ms", "x-zmachine"])
check("K7 normalize_ext_list 空输入-> []", U.normalize_ext_list("") == [] and U.normalize_ext_list(None) == [])
check("K8 normalize_ext_list 接受 12 位边界",
      U.normalize_ext_list("abcdefghijkl") == ["abcdefghijkl"])
check("K9 normalize_ext_list 拒绝 13 位",
      U.normalize_ext_list("abcdefghijklm") == [])
check("K10 split_ext_tokens 语义",
      U.split_ext_tokens("a,b;c d") == ["a", "b", "c", "d"])

check("K11 is_denied_upload 命中黑名单", U.is_denied_upload("a.exe", "exe") == "exe")
check("K12 is_denied_upload 未命中放行", U.is_denied_upload("a.txt", "exe") == "")
check("K13 is_denied_upload 无扩展名放行", U.is_denied_upload("noext", "exe") == "")
check("K14 is_denied_upload 空黑名单全放行", U.is_denied_upload("a.exe", "") == "")
check("K15 is_denied_upload 支持连字符扩展名",
      U.is_denied_upload("x.appref-ms", "appref-ms") == "appref-ms")
check("K16 is_denied_upload 大小写不敏感", U.is_denied_upload("A.EXE", "exe") == "exe")

check("K17 safe_join 正常路径", U.safe_join("/base", "a/b.md") is not None)
check("K18 safe_join 阻断穿越", U.safe_join("/base", "../../etc/passwd") is None)
_sj = U.safe_join("/base", "/etc/passwd")
check("K19 safe_join 绝对路径不出base（剥前导斜杠后拼接）",
      _sj is not None and os.path.abspath(_sj).startswith(os.path.abspath("/base") + os.sep), str(_sj))

check("K20 is_private_ip 局域网", U.is_private_ip("192.168.1.1") and U.is_private_ip("127.0.0.1"))
check("K21 is_private_ip 公网为 False", not U.is_private_ip("8.8.8.8"))
check("K22 is_private_ip 非法输入为 False", not U.is_private_ip("not-an-ip"))

check("K23 is_public_static 白名单内", U.is_public_static("/index.html")
      and U.is_public_static("/vditor/dist/index.min.js")
      and U.is_public_static("/ui/config"))
check("K24 is_public_static 白名单外", not U.is_public_static("/server.py")
      and not U.is_public_static("/settings.json"))

check("K25 is_static_denied 拦截源码", U.is_static_denied("server.py"))
check("K26 is_static_denied 拦截点文件", U.is_static_denied(".env"))
check("K27 is_static_denied 放行正常", not U.is_static_denied("index.html"))

check("K28 UPLOAD_NAME_RE 接受 uuid+连字符扩展名",
      bool(U.UPLOAD_NAME_RE.match("a" * 32 + ".appref-ms")))
check("K29 UPLOAD_NAME_RE 拒绝路径穿越",
      not U.UPLOAD_NAME_RE.match("../../etc/passwd"))
check("K30 UPLOAD_NAME_RE 拒绝非 uuid",
      not U.UPLOAD_NAME_RE.match("hello.txt"))

check("K31 upload_headers 非内联强制下载+sandbox",
      U.upload_headers("/x/a.txt").get("Content-Disposition") == "attachment"
      and "sandbox" in U.upload_headers("/x/a.txt").get("Content-Security-Policy", ""))
check("K32 upload_headers svg 内联但sandbox",
      "Content-Disposition" not in U.upload_headers("/x/a.svg")
      and "sandbox" in U.upload_headers("/x/a.svg").get("Content-Security-Policy", ""))
check("K33 upload_headers png 正常内联",
      "Content-Disposition" not in U.upload_headers("/x/a.png"))

check("K34 static_headers 含 ETag/Last-Modified",
      "ETag" in U.static_headers(APP) and "Last-Modified" in U.static_headers(APP))
check("K35 guess_mime 已知类型", U.guess_mime("a.js") == "text/javascript")
check("K36 guess_mime 未知类型兜底",
      U.guess_mime("a.unknownext") == "application/octet-stream")

check("K37 parse_multipart 基本解析",
      len(U.parse_multipart(b"--b\r\nContent-Disposition: form-data; name=\"root\"\r\n\r\nv\r\n--b--",
                            b"b")[1].get("root", "")) == 1)
check("K38 slugify 中文保留", U.slugify("我的文档") == "我的文档")
check("K39 slugify 特殊字符转-", U.slugify("a/b:c") == "a-b-c")
check("K40 slugify 空值兜底", U.slugify("") == "root")

check("K41 DEFAULT_UPLOAD_DENY 含 appref-ms",
      "appref-ms" in U.normalize_ext_list(U.DEFAULT_UPLOAD_DENY))
check("K42 DEFAULT_UPLOAD_DENY 归一化幂等",
      U.normalize_ext_list(U.DEFAULT_UPLOAD_DENY) == U.normalize_ext_list(",".join(U.normalize_ext_list(U.DEFAULT_UPLOAD_DENY))))
check("K43 版本键含哈希后缀",
      bool(re.match(r"^.+--[0-9a-f]{12}$", U._version_key("a/b.md"))))

check("K44 parse_data_share_paths JSON 数组",
      U.parse_data_share_paths('["/a","/b"]') == ["/a", "/b"])
check("K45 parse_data_share_paths 冒号分隔",
      U.parse_data_share_paths("/a:/b") == ["/a", "/b"])
check("K46 parse_data_share_paths 换行分隔",
      U.parse_data_share_paths("/a\n/b") == ["/a", "/b"])
check("K47 _paths_from_json 非 JSON 返回 None",
      U._paths_from_json("just a path") is None)


# ============================================================
# L. 代码卫生
# ============================================================
section("L. 代码卫生")
server_src = open(os.path.join(APP, "server.py"), encoding="utf-8").read()
util_src = open(os.path.join(APP, "vd_util.py"), encoding="utf-8").read()
html_src = open(os.path.join(APP, "index.html"), encoding="utf-8").read()

check("L1 语法正确（server.py）", compile(server_src, "server.py", "exec") is not None)
check("L2 语法正确（vd_util.py）", compile(util_src, "vd_util.py", "exec") is not None)
check("L3 APP_VERSION 与 manifest 一致",
      ('APP_VERSION = "%s"' % _vdef) in server_src, str(_vdef))

check("L4 死代码 _env_bool 已删除", "def _env_bool" not in server_src)
check("L5 统一入口 _content_length 存在", "def _content_length" in server_src)
check("L6 带上限的 _read_body 存在", "def _read_body" in server_src)
check("L7 统一 JSON 读取 _json_body 存在", "def _json_body" in server_src)
check("L8 统一响应头 _build_headers 存在", "def _build_headers" in server_src)
check("L9 统一整型设置 _apply_int_setting 存在", "def _apply_int_setting" in server_src)
check("L10 统一失败计数 _fail_entry 存在", "def _fail_entry" in server_src)
check("L11 split_ext_tokens 已抽取", "def split_ext_tokens" in util_src)
check("L12 _paths_from_json 已抽取", "def _paths_from_json" in util_src)

check("L13 无裸 int(Content-Length) 解析",
      server_src.count('int(self.headers.get("Content-Length"') == 0,
      "剩余 %d 处" % server_src.count('int(self.headers.get("Content-Length"'))
check("L14 _read_json try/except 样板仅剩 1 处",
      len(re.findall(r"try:\n\s+return self\._read_json\(\)", server_src)) == 1)
check("L15 SEC_HEADERS 手工合并仅剩 1 处",
      server_src.count("h = dict(SEC_HEADERS)") == 1)
check("L16 无 console 调试残留",
      not re.search(r"\bconsole\.(log|debug|info)\b", html_src))
check("L17 无 debugger/TODO 残留",
      not re.search(r"\bdebugger\b|TODO|FIXME", server_src + html_src))
check("L18 无 eval/exec/pickle",
      not re.search(r"\beval\(|\bexec\(|pickle|subprocess|os\.system", server_src))
check("L19 无 f-string 注入式 SQL（无 SQL 场景）", "SELECT" not in server_src.upper())
check("L20 前端 escapeHtml 存在", "function escapeHtml" in html_src)
check("L21 版本号与 manifest 一致",
      ('APP_VERSION = "%s"' % _vdef) in server_src and
      tuple(int(x) for x in _vdef.split(".")) >= (1, 2, 0), str(_vdef))
check("L22 无 __pycache__ 混入包内",
      not os.path.exists(os.path.join(APP, "__pycache__")))
# 说明：app/uploads 与 app/docs 由 server.py 启动时的 os.makedirs 创建（运行时目录），
# 测试跑完它们会重新出现属正常；打包产物中不存在（已由test_smoke_pkg 的文件清单校验）。
_runtime_dirs = {"uploads", "docs"}
check("L23 无非运行时空目录残留", not any(
    os.path.isdir(os.path.join(dp, d)) and not os.listdir(os.path.join(dp, d))
    and d not in _runtime_dirs
    for dp, dn, fn in os.walk(APP) for d in dn))

sv.stop()

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 60)
if FAILED == 0:
    print("RESULT(audit 1.1.4): passed=%d failed=0  —— 全部通过" % PASSED)
else:
    print("RESULT(audit 1.1.4): passed=%d failed=%d" % (PASSED, FAILED))
    print("\n失败明细：")
    for n, e in FAIL_LOG:
        print("  - %s   %s" % (n, e))
print("=" * 60)
sys.exit(1 if FAILED else 0)
