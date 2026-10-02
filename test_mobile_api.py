#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""移动端 API（/api/m/）定向回归测试。

覆盖 MOBILE_API.md 约定的全部 15 个接口 + 鉴权/参数校验/错误处理/响应格式。
测试方式：起真实server 进程（独立端口 + 临时配置/文档目录），用原始 socket 发请求。

测试脚本约定（见 MEMORY「写 HTTP 测试用例两条硬规则」）：
1. URL 参数必须百分号编码（`enc()`），中文 root/path 直拼会得到 404 假失败；
2. 起长驻服务用 Popen + 轮询端口 + terminate()，不用 subprocess.run(timeout=)。

用法：python test_mobile_api.py
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "vditor-fpk", "app")
PASSWORD = "test1234"

PASSED = []
FAILED = []


def check(cid, desc, cond, extra=""):
    if cond:
        PASSED.append(cid)
        print("  PASS %s %s" % (cid, desc))
    else:
        FAILED.append((cid, desc, extra))
        print("  FAIL %s %s%s" % (cid, desc, ("  -> " + str(extra)) if extra else ""))


def enc(v):
    """URL 百分号编码。请求行是 latin-1，中文必须先编码才能放进 URL。"""
    return quote(str(v), safe="")


class Client:
    """极简 HTTP 客户端：直接走 socket，便于构造非法请求（非法长度、畸形 JSON 等）。"""

    def __init__(self, port):
        self.port = port
        self.token = None

    def raw(self, method, path, body=None, headers=None, token=None):
        h = dict(headers or {})
        if token is None:
            token = self.token
        if token:
            h["Authorization"] = "Bearer " + token
        payload = body if isinstance(body, (bytes, type(None))) else body.encode("utf-8")
        if payload is not None and "Content-Length" not in h:
            h["Content-Length"] = str(len(payload))
        if "Host" not in h:
            h["Host"] = "127.0.0.1:%d" % self.port
        if "Connection" not in h:
            h["Connection"] = "close"
        lines = ["%s %s HTTP/1.1" % (method, path)]
        for k, v in h.items():
            lines.append("%s: %s" % (k, v))
        req = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
        if payload:
            req += payload
        try:
            s = socket.create_connection(("127.0.0.1", self.port), timeout=15)
            s.sendall(req)
            chunks = []
            while True:
                b = s.recv(65536)
                if not b:
                    break
                chunks.append(b)
            s.close()
            raw = b"".join(chunks)
        except Exception as e:
            return 0, {}, {"_error": str(e)}
        if not raw:
            return 0, {}, {"_empty": True}
        head, _, body2 = raw.partition(b"\r\n\r\n")
        first = head.split(b"\r\n")[0].decode("latin-1", "replace")
        parts = first.split(" ")
        code = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        hd = {}
        for ln in head.split(b"\r\n")[1:]:
            if b":" in ln:
                k, _, v = ln.partition(b":")
                hd[k.decode("latin-1").strip()] = v.decode("latin-1").strip()
        if hd.get("Transfer-Encoding", "").lower() == "chunked":
            body2 = dechunk(body2)
        try:
            data = json.loads(body2.decode("utf-8"))
        except Exception:
            data = {"_raw": body2[:200].decode("utf-8", "replace")}
        return code, hd, data

    def j(self, method, path, obj=None, token=None, headers=None):
        body = None if obj is None else json.dumps(obj, ensure_ascii=False)
        return self.raw(method, path, body, headers, token)


def dechunk(b):
    out = b""
    while True:
        i = b.find(b"\r\n")
        if i < 0:
            break
        try:
            n = int(b[:i].split(b";")[0], 16)
        except ValueError:
            break
        if n == 0:
            break
        out += b[i + 2:i + 2 + n]
        b = b[i + 2 + n + 2:]
    return out


def wait_port(port, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except Exception:
            time.sleep(0.15)
    return False


def main():
    tmp = tempfile.mkdtemp(prefix="vditor_m_")
    cfg = os.path.join(tmp, "cfg")
    docs = os.path.join(tmp, "docs")
    os.makedirs(cfg, exist_ok=True)
    os.makedirs(docs, exist_ok=True)
    port = 9422
    env = dict(os.environ)
    env.update({
        "VDITOR_CONFIG": cfg,
        "VDITOR_DOC_DIR": docs,
        "VDITOR_DOC_NAME": "我的文档",
        "VDITOR_PORT": str(port),
        "VDITOR_PASSWORD": PASSWORD,
        "VDITOR_SECURE_COOKIE": "0",
        "VDITOR_TRUST_PROXY": "0",
        "PYTHONIOENCODING": "utf-8",
    })
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=APP, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        if not wait_port(port):
            out, err = proc.communicate(timeout=5)
            print("服务启动失败：\n%s\n%s" % (out.decode("utf-8", "replace"),
                                       err.decode("utf-8", "replace")))
            return
        run(Client(port), port, docs)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 60)
    print("RESULT(mobile api): passed=%d failed=%d" % (len(PASSED), len(FAILED)))
    if FAILED:
        for cid, desc, extra in FAILED:
            print("  FAILED %s %s  %s" % (cid, desc, extra))
        sys.exit(1)
    print("=" * 60)


def run(c, port, docs):
    root = "我的文档"

    # ---- A. 公开接口与健康检查 ----
    print("\n== A. 健康检查与鉴权 ==")
    code, _, d = c.j("GET", "/api/m/health")
    check("A1", "health 无需鉴权即可访问", code == 200 and d.get("ok"), (code, d))
    check("A2", "health 返回版本与 api_version",
          d.get("data", {}).get("api_version") == "m1" and d.get("data", {}).get("version"),
          d.get("data"))
    check("A3", "health 时间格式为ISO8601 UTC",
          str(d.get("data", {}).get("time", "")).endswith("Z"), d.get("data", {}).get("time"))

    # 未带 token 访问受保护接口
    code, _, d = c.j("GET", "/api/m/roots", token="")
    check("A4", "未带 token -> INVALID_TOKEN",
          code == 401 and d.get("error") == "INVALID_TOKEN", (code, d))
    code, _, d = c.j("GET", "/api/m/roots", token="deadbeef-invalid")
    check("A5", "非法 token -> INVALID_TOKEN",
          code == 401 and d.get("error") == "INVALID_TOKEN", (code, d))
    code, _, d = c.j("GET", "/api/m/roots", headers={"Authorization": "Basic xyz"})
    check("A6", "非 Bearer 认证头被拒",
          code == 401 and d.get("error") == "INVALID_TOKEN", (code, d))

    # ---- B. 登录 ----
    print("\n== B. 登录与会话 ==")
    code, _, d = c.j("POST", "/api/m/auth/login", {"password": "wrong-pwd"})
    check("B1", "密码错误 -> FORBIDDEN", code == 403 and d.get("error") == "FORBIDDEN", (code, d))
    code, _, d = c.j("POST", "/api/m/auth/login", {"password": PASSWORD})
    check("B2", "正确密码登录成功", code == 200 and d.get("ok"), (code, d))
    tok = d.get("data", {}).get("token")
    check("B3", "下发 token", bool(tok) and len(tok) >= 32, tok)
    check("B4", "返回有效期", d.get("data", {}).get("expires_in", 0) > 0, d.get("data"))
    c.token = tok
    code, _, d = c.j("POST", "/api/m/auth/login", {"password": PASSWORD})
    check("B5", "可重复登录（互不干扰）", code == 200 and d.get("ok"), (code, d))
    code, _, d = c.j("GET", "/api/m/auth/session")
    check("B6", "session 查询已登录", code == 200 and d.get("data", {}).get("authenticated"), (code, d))
    check("B7", "session 返回剩余有效期",
          d.get("data", {}).get("abs_expires_in", 0) > 0, d.get("data"))
    code, _, d = c.j("POST", "/api/m/auth/login", {"password": 123})
    check("B8", "非字符串密码 -> BAD_REQUEST",
          code == 400 and d.get("error") == "BAD_REQUEST", (code, d))
    code, _, d = c.j("POST", "/api/m/auth/login", None,
                     headers={"Content-Length": "abc"})
    # 非法长度被归一为 0 → 请求体视为空 → 空密码判错；关键是**有正常响应而非断连**
    check("B9", "非法 Content-Length 不崩且有响应", code in (400, 403), (code, d))

    # ---- C. 分区与列表 ----
    print("\n== C. 分区与文档列表 ==")
    code, _, d = c.j("GET", "/api/m/roots")
    check("C1", "列出分区", code == 200 and isinstance(d.get("data", {}).get("roots"), list), (code, d))
    roots = d.get("data", {}).get("roots", [])
    check("C2", "包含测试分区", any(r.get("name") == root for r in roots), roots)
    rid = roots[0]["id"] if roots else ""

    code, _, d = c.j("GET", "/api/m/files?root=%s" % enc(rid))
    check("C3", "空目录列表", code == 200 and d.get("data", {}).get("total") == 0, (code, d))
    code, _, d = c.j("GET", "/api/m/files?root=%s&limit=abc&offset=xyz" % enc(rid))
    check("C4", "非法分页参数回落默认",
          code == 200 and d.get("data", {}).get("limit") == 200, (code, d))
    code, _, d = c.j("GET", "/api/m/files?root=%s&limit=99999" % enc(rid))
    check("C5", "limit 上限被夹到 1000", d.get("data", {}).get("limit") == 1000, d.get("data"))
    code, _, d = c.j("GET", "/api/m/files?root=%s" % enc("no-such-root"))
    check("C6", "无效 root -> BAD_REQUEST",
          code == 400 and d.get("error") == "BAD_REQUEST", (code, d))

    # ---- D. 文档 CRUD ----
    print("\n== D. 文档增删改查 ==")
    # 路径语义与 Web 端一致：文档落盘为 <dir>/<stem>/<stem>.md（同名文件夹便于放附件）
    code, _, d = c.j("POST", "/api/m/file",
                     {"root": rid, "path": "笔记/笔记.md", "content": "# 标题\n\n正文"})
    check("D1", "新建文档", code == 200 and d.get("ok"), (code, d))
    doc_path = d.get("data", {}).get("path")
    check("D2", "落盘为同名文件夹结构", doc_path == "笔记/笔记/笔记.md", doc_path)
    check("D3", "返回内容与 id",
          d.get("data", {}).get("content", "").startswith("# 标题")
          and bool(d.get("data", {}).get("id")), d.get("data"))

    code, _, d = c.j("POST", "/api/m/file",
                     {"root": rid, "path": "笔记/笔记.md", "content": "dup"})
    check("D4", "重复新建 -> CONFLICT", code == 409 and d.get("error") == "CONFLICT", (code, d))

    code, _, d = c.j("GET", "/api/m/file?root=%s&path=%s" % (enc(rid), enc(doc_path)))
    check("D5", "读取文档", code == 200 and d.get("data", {}).get("content", "").startswith("# 标题"), (code, d))
    ver = d.get("data", {}).get("version", 0)

    code, _, d = c.j("PUT", "/api/m/file",
                     {"root": rid, "path": doc_path, "content": "# 新内容\n", "if_version": ver})
    check("D6", "保存文档（乐观锁匹配）", code == 200 and d.get("ok"), (code, d))
    check("D7", "内容已更新", d.get("data", {}).get("content") == "# 新内容\n", d.get("data", {}).get("content"))

    code, _, d = c.j("PUT", "/api/m/file",
                     {"root": rid, "path": doc_path, "content": "x", "if_version": 999})
    check("D8", "乐观锁冲突 -> FORBIDDEN",
          code == 403 and d.get("error") == "FORBIDDEN", (code, d))
    code, _, d = c.j("PUT", "/api/m/file",
                     {"root": rid, "path": doc_path, "content": "x", "if_version": "abc"})
    check("D9", "if_version 非整数 -> BAD_REQUEST",
          code == 400 and d.get("error") == "BAD_REQUEST", (code, d))

    code, _, d = c.j("GET", "/api/m/files?root=%s" % enc(rid))
    items = d.get("data", {}).get("items", [])
    # 文档落在 笔记/ 目录下；列表为单层，笔记/ 是个目录（文档同名文件夹本身不作为条目）
    check("D10", "列表含文档所在目录",
          any(i["name"] == "笔记" and i["is_dir"] for i in items), items)

    code, _, d = c.j("GET", "/api/m/file?root=%s&path=%s" % (enc(rid), enc("../../etc/passwd")))
    check("D11", "路径穿越读取被拒", code in (400, 403, 404), (code, d))

    # ---- E. 历史版本 ----
    print("\n== E. 历史版本 ==")
    code, _, d = c.j("GET", "/api/m/file/versions?root=%s&path=%s" % (enc(rid), enc(doc_path)))
    check("E1", "版本列表非空", code == 200 and len(d.get("data", {}).get("items", [])) > 0, (code, d))
    vs = d.get("data", {}).get("items", [])
    check("E2", "版本项含 created_at/size/source",
          all(k in vs[0] for k in ("created_at", "size", "source")) if vs else False, vs[:1])
    vts = vs[0]["version"] if vs else None

    code, _, d = c.j("POST", "/api/m/file/versions/restore",
                     {"root": rid, "path": doc_path, "version": vts})
    check("E3", "回滚到指定版本", code == 200 and d.get("ok"), (code, d))
    check("E4", "回滚后内容为旧版", d.get("data", {}).get("content", "").startswith("# 标题"),
          d.get("data", {}).get("content"))

    code, _, d = c.j("POST", "/api/m/file/versions/restore",
                     {"root": rid, "path": doc_path, "version": 1234567890})
    check("E5", "回滚到不存在版本 -> NOT_FOUND",
          code == 404 and d.get("error") == "NOT_FOUND", (code, d))
    code, _, d = c.j("POST", "/api/m/file/versions/restore",
                     {"root": rid, "path": doc_path, "version": "abc"})
    check("E6", "version 非整数 -> BAD_REQUEST",
          code == 400 and d.get("error") == "BAD_REQUEST", (code, d))

    # ---- F. 上传限制与附件 ----
    print("\n== F. 上传限制与附件 ==")
    code, _, d = c.j("GET", "/api/m/settings/upload")
    data = d.get("data", {})
    check("F1", "读取上传限制", code == 200 and data.get("max_mb") == 256, (code, data))
    check("F2", "返回当前黑名单", len(data.get("deny_exts", [])) > 0, len(data.get("deny_exts", [])))
    check("F3", "返回默认黑名单", len(data.get("default_deny_exts", [])) > 0,
          len(data.get("default_deny_exts", [])))
    check("F4", "黑名单含 appref-ms（连字符支持）",
          "appref-ms" in data.get("deny_exts", []), data.get("deny_exts", [])[:5])

    boundary = "----vditorMTest"
    def multipart(fname, content, fields=None):
        body = b""
        for k, v in (fields or {}).items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                     % (boundary, k, v)).encode("utf-8")
        body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                 "Content-Type: application/octet-stream\r\n\r\n" % (boundary, fname)).encode("utf-8")
        body += content + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
        return body

    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    body = multipart("shot.png", png, {"root": rid, "path": doc_path})
    code, _, d = c.raw("POST", "/api/m/upload", body,
                       {"Content-Type": "multipart/form-data; boundary=" + boundary})
    check("F5", "上传附件成功", code == 200 and d.get("ok"), (code, d))
    asset_name = (d.get("data") or {}).get("name", "")
    check("F6", "返回存储名与可插入文本",
          bool(asset_name) and (d.get("data") or {}).get("insert_text", "").startswith("![]("),
          d.get("data"))

    code, _, d = c.j("POST", "/api/m/file/assets", {"root": rid, "path": doc_path})
    check("F7", "列出文档附件", code == 200 and len(d.get("data", {}).get("assets", [])) >= 1, (code, d))

    code, _, d = c.raw("GET", "/api/m/asset/" + enc(asset_name))
    check("F8", "读取附件（已鉴权）", code == 200, (code, d))

    exe = b"MZ\x90\x00"
    body = multipart("bad.exe", exe, {"root": rid, "path": doc_path})
    code, _, d = c.raw("POST", "/api/m/upload", body,
                       {"Content-Type": "multipart/form-data; boundary=" + boundary})
    check("F9", "黑名单格式被拒-> DENIED_EXT",
          code == 400 and d.get("error") == "DENIED_EXT", (code, d))

    appref = b"\x01\x02"
    body = multipart("x.appref-ms", appref, {"root": rid, "path": doc_path})
    code, _, d = c.raw("POST", "/api/m/upload", body,
                       {"Content-Type": "multipart/form-data; boundary=" + boundary})
    check("F10", "连字符格式命中黑名单", code == 400 and d.get("error") == "DENIED_EXT", (code, d))

    code, _, d = c.raw("POST", "/api/m/upload", b"not multipart",
                       {"Content-Type": "application/json"})
    check("F11", "非 multipart -> BAD_REQUEST",
          code == 400 and d.get("error") == "BAD_REQUEST", (code, d))

    # ---- G. 异常与边界 ----
    print("\n== G. 异常与边界 ==")
    code, _, d = c.j("GET", "/api/m/nope")
    check("G1", "未知接口 -> NOT_FOUND", code == 404 and d.get("error") == "NOT_FOUND", (code, d))
    code, _, d = c.j("POST", "/api/m/nope", {})
    check("G2", "未知 POST 接口 -> NOT_FOUND", code == 404, (code, d))
    code, _, d = c.j("PUT", "/api/m/nope", {})
    check("G3", "未知 PUT 接口 -> NOT_FOUND", code == 404, (code, d))
    code, _, d = c.j("DELETE", "/api/m/nope")
    check("G4", "未知 DELETE 接口 -> NOT_FOUND", code == 404, (code, d))
    code, _, d = c.raw("PUT", "/api/m/file", b"{bad json",
                       {"Content-Type": "application/json"})
    check("G5", "畸形 JSON -> 400", code == 400, (code, d))
    code, _, d = c.j("POST", "/api/m/file", {"root": rid})
    check("G6", "缺 path -> FORBIDDEN", code == 403, (code, d))
    code, _, d = c.j("DELETE", "/api/m/file", {"root": rid, "path": "no/such.md"})
    check("G7", "删除不存在 -> NOT_FOUND", code == 404, (code, d))
    code, _, d = c.raw("POST", "/api/m/upload", b"x", {"Content-Length": "-5"})
    check("G8", "负 Content-Length 不崩", code in (400, 413), (code, d))
    code, _, d = c.j("DELETE", "/api/m/file", {"root": rid, "path": doc_path})
    check("G9", "删除文档（含附件与历史）", code == 200 and d.get("ok"), (code, d))
    code, _, d = c.j("GET", "/api/m/file?root=%s&path=%s" % (enc(rid), enc(doc_path)))
    check("G10", "删除后读取 404", code == 404, (code, d))

    # ---- H. 登出 ----
    print("\n== H. 登出 ==")
    code, _, d = c.j("POST", "/api/m/auth/logout")
    check("H1", "登出成功", code == 200 and d.get("ok"), (code, d))
    code, _, d = c.j("GET", "/api/m/roots", token=tok)
    check("H2", "登出后 token 失效", code == 401, (code, d))
    code, _, d = c.j("POST", "/api/m/auth/logout", token="invalid-token")
    # 登出**必须幂等**：「当前无有效会话」就是「已登出」，不是错误。
    # 端上常见「token 刚过期就点退出」或「重复点退出」，
    # 若回401 会让App 弹一个无法理解的报错。语义定义见 MOBILE_API.md §3.3。
    check("H3", "非法 token 登出幂等回 ok", code == 200 and d.get("ok"), (code, d))
    code, _, d = c.j("POST", "/api/m/auth/logout", token="invalid-token")
    check("H3b", "重复登出仍幂等", code == 200 and d.get("ok"), (code, d))

    # ---- I. Web端接口不受影响 ----
    print("\n== I. Web 端兼容性 ==")
    code, _, d = c.j("GET", "/api/auth/check")
    check("I1", "Web 鉴权检查仍正常", code == 200 and "authenticated" in d, (code, d))
    code, _, d = c.j("GET", "/api/m/health")
    check("I2", "登出后 health 仍公开", code == 200, (code, d))
    check("I3", "版本已升为 1.2.0",
          c.j("GET", "/api/m/health")[2].get("data", {}).get("version") == "1.2.0",
          c.j("GET", "/api/m/health")[2].get("data", {}).get("version"))


if __name__ == "__main__":
    main()