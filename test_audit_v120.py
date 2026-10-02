#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1.2.0 完整审计的**守护测试**：把本轮审计发现并修复的问题逐条钉死，
防止后续改动把它们改回去。

覆盖（对应 CODE_REVIEW.md 的问题清单）：
* H1  非对象 JSON 请求体（数组 / 字符串 / 数字 / null）不再让连接断开，一律回 400
* H2  版本时间戳 ts 非法（"abc" / None / 浮点串）不再抛 ValueError/TypeError
* M1  /api/m/asset/<name> 仍可正常取回附件（改为流式后的行为回归）
* M2  /api/m/asset/ 受「API 数据输出」开关约束，且判定逻辑已收敛到 _m_output_off
* M3  备份 / 备份恢复接口仍正常
* M4  /favicon.ico 在图标文件异常时不崩
* 兼容 修复后既有接口的正常路径行为不变（新建/保存/回滚/设置读写）

用法：`python test_audit_v120.py`
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(APP_DIR, "vditor-fpk", "app")
PORT = 8961
PASSWORD = "audit-pass-2026"

# 本测试只访问 127.0.0.1，必须绕开环境里的 HTTP_PROXY / HTTPS_PROXY
# （沙箱/CI 常设代理，走代理会让本机请求被转发到 27343 端口，出现随机超时与 502）。
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS %-10s %s" % (name, ""))
    else:
        FAIL += 1
        FAILED.append("%s %s" % (name, detail))
        print("  FAIL %-10s %s  %s" % (name, detail, ""))


def wait_port(port, timeout=25):
    for _ in range(int(timeout / 0.15)):
        try:
            s = socket.create_connection(("127.0.0.1", port), 0.3)
            s.close()
            return True
        except OSError:
            time.sleep(0.15)
    return False


class Client:
    def __init__(self):
        self.base = "http://127.0.0.1:%d" % PORT
        self.token = ""
        self.cookie = ""

    def _open(self, path, data=None, method=None, headers=None):
        body = data.encode("utf-8") if isinstance(data, str) else data
        req = urllib.request.Request(self.base + path, data=body, method=method)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                sc = r.headers.get("Set-Cookie")
                if sc:
                    self.cookie = sc.split(";")[0]
                return r.status, raw
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            # 连接被直接断开 / 超时 = 服务端抛了未捕获异常
            return -1, ("%s: %s" % (type(e).__name__, e)).encode()

    def j(self, path, data=None, method=None):
        """发 JSON；返回 (code, dict)"""
        body = None if data is None else json.dumps(data)
        h = {"Content-Type": "application/json"} if data is not None else None
        code, raw = self._open(path, body, method, h)
        try:
            return code, json.loads(raw.decode("utf-8"))
        except Exception:
            return code, {"_raw": raw[:200].decode("utf-8", "replace")}

    def raw(self, path, body, method="POST"):
        """发任意原始字节（用于构造非法 JSON）"""
        return self._open(path, body, method, {"Content-Type": "application/json"})

    def get(self, path):
        return self._open(path, None, "GET")


def start(cfg, docs, env_extra=None):
    env = dict(os.environ)
    env.update({
        "VDITOR_CONFIG": cfg,
        "VDITOR_DOC_DIR": docs,
        "VDITOR_DOC_NAME": "我的文档",
        "VDITOR_PORT": str(PORT),
        "VDITOR_PASSWORD": PASSWORD,
        "VDITOR_SECURE_COOKIE": "0",
        "VDITOR_TRUST_PROXY": "0",
        "VDITOR_API_OUTPUT": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    if env_extra:
        env.update(env_extra)
    # ⚠️ 服务端输出**绝不能**接 subprocess.PIPE：管道缓冲区（约 64KB）写满后，
    # 服务端会阻塞在 stderr/stdout 的写操作上，表现为「进程活着但不再应答任何请求」——
    # 症状与本测试要守护的「未捕获异常导致服务卡死」几乎一样，极易误判。
    # 故一律落到文件（Debug 时用 AUDIT_SRVLOG 指定）。
    log_path = os.environ.get("AUDIT_SRVLOG") or os.path.join(cfg, "_server.log")
    fh = open(log_path, "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-u", "server.py"], cwd=APP, env=env,
                         stdout=fh, stderr=subprocess.STDOUT)
    p._log_path = log_path
    if not wait_port(PORT):
        fh.close()
        with open(log_path, encoding="utf-8") as f:
            print("SERVER FAILED TO START:\n" + f.read()[-2000:])
        sys.exit(1)
    return p


def stop(p):
    p.terminate()
    try:
        p.wait(timeout=6)
    except Exception:
        p.kill()
    time.sleep(0.5)


def purge(path):
    for _ in range(6):
        if not os.path.exists(path):
            return True
        try:
            shutil.rmtree(path)
        except OSError:
            time.sleep(0.3)
    return not os.path.exists(path)


def canary():
    """裸 socket 探活：服务端是否仍能应答（用于定位「服务被卡死」发生在哪一步）。"""
    try:
        sock = socket.create_connection(("127.0.0.1", PORT), 2)
        sock.sendall(b"GET /api/m/health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        data = sock.recv(40)
        sock.close()
        return data[:15].decode("latin-1")
    except Exception as e:
        return "DEAD:%s" % type(e).__name__


def main():
    cfg = tempfile.mkdtemp(prefix="audit-cfg-")
    docs = tempfile.mkdtemp(prefix="audit-docs-")
    srv = start(cfg, docs)
    c = Client()
    try:
        # ---------- 登录（Web + 移动端双会话）----------
        print("\n== 0. 准备 ==")
        code, d = c.j("/api/login", {"password": PASSWORD}, method="POST")
        check("A0-1 Web 登录", code == 200, (code, d))
        code, d = c.j("/api/m/auth/login", {"password": PASSWORD}, method="POST")
        check("A0-2 移动端登录", code == 200 and d.get("ok"), (code, d))
        c.token = (d.get("data") or {}).get("token", "")
        check("A0-3 拿到 token", bool(c.token), d)
        check("canary-1 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 1. H1 非对象 JSON 请求体（原：AttributeError → 连接断开）==")
        # 每条都必须拿到**明确的状态码**，绝不能是 -1（连接断开/超时）
        cases = [
            ("POST", "/api/m/file", b"[1,2]"),
            ("POST", "/api/m/file", b'"str"'),
            ("POST", "/api/m/file", b"123"),
            ("POST", "/api/m/file", b"null"),
            ("PUT", "/api/m/file", b"[]"),
            ("DELETE", "/api/m/file", b"{}"),
            ("POST", "/api/save", b"[1,2]"),
            ("POST", "/api/new", b"[1,2]"),
            ("POST", "/api/version/restore", b"[1,2]"),
            ("POST", "/api/version/delete", b"[1,2]"),
            ("POST", "/api/doc/delete", b"[1,2]"),
            ("POST", "/api/export-zip", b"[1,2]"),
            ("POST", "/api/folders", b"[1,2]"),
            ("POST", "/api/settings/import", b"[1,2]"),
        ]
        for i, (m, p, body) in enumerate(cases, 1):
            code, _ = c.raw(p, body, m)
            check("H1-%02d %s %s" % (i, m, p),
                  code != -1 and 400 <= code < 500,
                  "code=%s（连接断开说明异常未被捕获）" % code)
        # 服务仍然存活（崩溃不得影响后续请求）
        code, d = c.j("/api/m/health")
        check("H1-15 崩溃后服务仍可用", code == 200 and d.get("ok"), (code, d))
        check("canary-2 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 2. H2 非法版本时间戳（原：ValueError → 连接断开）==")
        # 先建一个文档，制造真实的 root/path（分区 id 由分区名 slug 而来，不能写死 "r1"）
        code, d = c.j("/api/m/roots")
        roots = (d.get("data") or {}).get("roots", [])
        rid = roots[0]["id"] if roots else ""
        check("H2-00 拿到分区", bool(rid), (code, roots))
        code, d = c.j("/api/new", {"root": rid, "path": "审计/审计.md"}, method="POST")
        check("H2-01 建文档成功", code == 200 and d.get("ok"), (code, d))
        doc_path = d.get("path") or "审计/审计/审计.md"
        for i, bad in enumerate(["abc", None, "1.5", [1], {}, True], 1):
            code, r = c.j("/api/version/restore", {"root": rid, "path": doc_path, "ts": bad},
                          method="POST")
            check("H2-%02d restore ts=%r" % (10 + i, bad),
                  code != -1 and code in (400, 404), "code=%s" % code)
        for i, bad in enumerate(["abc", None, [1]], 1):
            code, r = c.j("/api/version/delete", {"root": rid, "path": doc_path, "ts": bad},
                          method="POST")
            check("H2-%02d delete ts=%r" % (20 + i, bad), code != -1, "code=%s" % code)
        # 合法但不存在的时间戳应回 404 而不是 500
        code, r = c.j("/api/version/restore", {"root": rid, "path": doc_path, "ts": 1},
                      method="POST")
        check("H2-24 不存在的 ts -> 404", code == 404, (code, r))
        check("canary-3 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 3. 精简后移动端正常路径 ==")
        code, d = c.j("/api/m/file", {"root": rid, "path": doc_path, "content": "# 正文\n"},
                      method="PUT")
        check("C1 保存成功", code == 200 and d.get("ok"), (code, d))
        ver = (d.get("data") or {}).get("version")
        check("C2 返回 version", isinstance(ver, int), ver)
        code, d = c.j("/api/m/file",
                      {"root": rid, "path": doc_path, "content": "# 覆盖\n",
                       "if_version": ver}, method="PUT")
        check("C3 乐观锁匹配可保存", code == 200 and d.get("ok"), (code, d))
        code, d = c.j("/api/m/file",
                      {"root": rid, "path": doc_path, "content": "# x\n", "if_version": 1},
                      method="PUT")
        check("C4 乐观锁冲突 FORBIDDEN",
              code == 403 and d.get("error") == "FORBIDDEN", (code, d))
        code, d = c.j("/api/m/file/versions?root=%s&path=%s"
                      % (urllib.parse.quote(rid), urllib.parse.quote(doc_path)))
        items = (d.get("data") or {}).get("items", [])
        check("C5 版本列表非空", code == 200 and len(items) >= 1, (code, d))
        check("C6 items 与 versions 双键一致",
              (d.get("data") or {}).get("versions") == items, d.get("data"))
        check("C7 版本倒序（最新在前）",
              items == sorted(items, key=lambda x: x["version"], reverse=True), items[:2])
        if items:
            ts = items[0]["version"]
            code, d = c.j("/api/m/file/version?root=%s&path=%s&version=%d"
                          % (urllib.parse.quote(rid), urllib.parse.quote(doc_path), ts))
            check("C8 读取单版本内容", code == 200 and "content" in (d.get("data") or {}),
                  (code, d))
            # H2 在移动端接口上同样成立
            code, _ = c.j("/api/m/file/version?root=%s&path=%s&version=abc"
                          % (urllib.parse.quote(rid), urllib.parse.quote(doc_path)))
            check("C9 单版本 ts 非法 -> 400", code == 400, code)
        check("canary-4 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 4. M1/M2 附件读取（改流式 + 开关判定收敛）==")
        boundary = "----auditboundary"
        fname = "cover.png"
        content = b"\x89PNG-fake-data"
        body = (
            ("--%s\r\n" % boundary).encode()
            + ('Content-Disposition: form-data; name="root"\r\n\r\n%s\r\n' % rid).encode()
            + ("--%s\r\n" % boundary).encode()
            + ('Content-Disposition: form-data; name="path"\r\n\r\n%s\r\n' % doc_path).encode()
            + ("--%s\r\n" % boundary).encode()
            + ('Content-Disposition: form-data; name="file"; filename="%s"\r\n'
               % fname).encode()
            + b"Content-Type: image/png\r\n\r\n" + content + b"\r\n"
            + ("--%s--\r\n" % boundary).encode()
        )
        code, d = c._open("/api/m/upload", body, "POST",
                          {"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        try:
            up = json.loads(d.decode("utf-8"))
        except Exception:
            up = {}
        check("D1 上传成功", code == 200 and up.get("ok"), (code, d[:200]))
        asset = (up.get("data") or {}).get("url", "")
        check("D2 返回 url", asset.startswith("/api/m/asset/"), asset)
        if asset:
            code, raw = c.get(asset)
            check("D3 附件可取回（流式）", code == 200 and raw == content,
                  (code, len(raw)))
            ctype = ""
            # 再取一次，确认响应体一致（流式路径稳定）
            code, raw2 = c.get(asset)
            check("D4 重复读取一致", code == 200 and raw2 == raw, (code,))
        check("canary-5 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 5. M3 备份与恢复（临时文件清理改为 try/finally）==")
        code, raw = c.get("/api/backup")
        check("E1 备份可下载", code == 200 and raw[:2] == b"\x1f\x8b", (code, len(raw)))
        check("E2 备份非空", len(raw) > 100, len(raw))
        # 恢复：把刚下载的备份原样 POST 回去（流式路径）
        code, d = c._open("/api/backup/restore", raw, "POST",
                          {"Content-Type": "application/gzip"})
        try:
            rr = json.loads(d.decode("utf-8"))
        except Exception:
            rr = {}
        check("E3 恢复成功", code == 200 and rr.get("ok"), (code, d[:200]))
        # 损坏的备份不得让连接断开
        code, d = c._open("/api/backup/restore", b"not-a-tarball", "POST",
                          {"Content-Type": "application/gzip"})
        check("E4 坏包不崩（回 4xx）", code != -1 and 400 <= code < 500, code)
        check("canary-6 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 6. M4 favicon 异常不崩 ==")
        code, _ = c.get("/favicon.ico")
        check("F1 favicon 无图标时 204", code == 204, code)
        # 造一个「目录」冒充 favicon.*，让 open() 失败 → 必须回 204 而不是断连
        os.makedirs(os.path.join(cfg, "favicon.png"), exist_ok=True)
        code, _ = c.get("/favicon.ico")
        check("F2 favicon 打开失败仍不崩", code in (204, 200), code)
        shutil.rmtree(os.path.join(cfg, "favicon.png"), ignore_errors=True)
        check("canary-7 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 7. 设置读写（_apply_and_reply 收敛后）==")
        code, d = c.j("/api/settings", {"api_output": True}, method="POST")
        check("G1 开启 api_output", code == 200 and d.get("ok"), (code, d))
        check("G2 回包带 settings", (d.get("settings") or {}).get("api_output") is True, d)
        code, d = c.j("/api/settings/import", {"settings": {"api_output": False}},
                      method="POST")
        check("G3 导入可写设置", code == 200 and d.get("ok"), (code, d))
        check("G4 导入回包仍带 imported", "imported" in d, list(d.keys()))
        code, d = c.j("/api/settings", {"api_output": "yes"}, method="POST")
        check("G5 非布尔被拒", code == 200 and "布尔" in (d.get("error") or ""), (code, d))
        code, d = c.j("/api/settings", [1, 2], method="POST")
        check("G6 数组设置体不崩", code != -1, code)
        if code == -1:
            print("  [diag] 进程存活:", srv.poll())
            try:
                s = socket.create_connection(("127.0.0.1", PORT), 3)
                s.sendall(b"GET /api/m/health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
                print("  [diag] 裸 socket 探活:", s.recv(60))
                s.close()
            except Exception as e:
                print("  [diag] 裸 socket 探活失败:", type(e).__name__, e)
        check("canary-8 服务仍应答", canary() == "HTTP/1.1 200 OK", canary())

        print("\n== 8. M2 关闭态下 /api/m/asset/ 同样被拦 ==")
        code, d = c.j("/api/settings", {"api_output": False}, method="POST")
        check("H1 关闭开关", code == 200, (code, d))
        if asset:
            code, d2 = c.j(asset)
            check("H2 关闭后附件被拦 API_OUTPUT_DISABLED",
                  code == 403 and d2.get("error") == "API_OUTPUT_DISABLED", (code, d2))
        # 未登录时仍应回 INVALID_TOKEN 而不是 API_OUTPUT_DISABLED（鉴权优先于开关）
        saved = c.token
        c.token = ""
        if asset:
            code, d2 = c.j(asset)
            check("H3 未登录回 INVALID_TOKEN",
                  code == 401 and d2.get("error") == "INVALID_TOKEN", (code, d2))
        c.token = saved
    finally:
        lp = getattr(srv, "_log_path", "")
        stop(srv)
        if lp and os.environ.get("AUDIT_DEBUG") and os.path.exists(lp):
            print("\n--- SERVER LOG (tail) ---")
            with open(lp, encoding="utf-8") as f:
                print(f.read()[-2500:])
        purge(cfg)
        purge(docs)

    print("\n" + "=" * 60)
    print("RESULT(audit v1.2.0): passed=%d failed=%d" % (PASS, FAIL))
    if FAILED:
        print("FAILED ITEMS:")
        for x in FAILED:
            print("   -", x)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
