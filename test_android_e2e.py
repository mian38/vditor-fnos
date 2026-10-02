#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端联调：模拟 Android 客户端 ApiClient 的**真实请求序列**，
跑通「登录 → 分区 → 列表 → 新建 → 打开 → 保存(乐观锁) → 附件 → 版本 → 回滚 → 登出」全链路。

与 test_mobile_api.py 的区别：
- test_mobile_api.py 测的是**接口契约**（边界、异常、错误码）
- 本脚本测的是**客户端调用序**（字段名与 App 的 data/Models.kt 逐字对应）

任何一方改了字段名而另一方没跟上，本脚本会立刻红。
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8931
PASSWORD = "e2e-pass-2026"

PASS = 0
FAIL = 0
FAILED_ITEMS = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS %-6s %s" % (name, ""))
    else:
        FAIL += 1
        FAILED_ITEMS.append("%s %s" % (name, detail))
        print("  FAIL %-6s %s  %s" % (name, detail, ""))


def assert_no_pollution():
    """守护：确认测试没有往工作区默认文档目录里写东西。

    服务端的文档根目录解析链是VDITOR_DOC_DIRS → fnOS 共享目录 →
    应用内管理的文件夹 → VDITOR_DOC_DIR → BASE_DIR/docs。
    只要环境变量名写错（如写成 VDITOR_DOC_ROOT），就会静默回落到
    `vditor-fpk/app/docs/`，把测试数据写进真实文档区。
    这里做一次事后校验，宁可测试红也不能默默污染。
    """
    default_docs = os.path.join(APP_DIR, "vditor-fpk", "app", "docs")
    if not os.path.isdir(default_docs):
        return True
    stray = []
    for root, dirs, files in os.walk(default_docs):
        for f in files:
            stray.append(os.path.join(root, f))
    if stray:
        print("!! 工作区默认文档目录被污染：%s" % stray[:5])
        return False
    return True


def wait_port(port, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.create_connection(("127.0.0.1", port), 0.5)
            s.close()
            return True
        except OSError:
            time.sleep(0.15)
    return False


def purge(path, attempts=5):
    """删干净测试目录。

    Windows 上文件句柄释放有延迟，上一轮服务端刚 terminate 时
    `rmtree(ignore_errors=True)` 会**静默失败**并留下残file，
    导致下一轮「空列表」断言被上一轮的产物污染。故改为显式重试并校验。
    """
    import shutil
    import time as _t
    for i in range(attempts):
        if not os.path.exists(path):
            return True
        try:
            shutil.rmtree(path)
        except Exception:
            pass
        _t.sleep(0.4 * (i + 1))
    if os.path.exists(path):
        left = []
        for root, dirs, files in os.walk(path):
            for f in files:
                left.append(os.path.join(root, f))
        print("!! 未能清空测试目录，残留：%s" % left[:5])
        return False
    return True


class Client:
    """与 Android ApiClient 同构的最小客户端（裸 socket，便于构造边界请求）。"""

    def __init__(self, port):
        self.port = port
        self.token = ""

    def call(self, method, path, body=None, raw_body=None, headers=None):
        h = {"Accept": "application/json", "Connection": "close"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        payload = b""
        if raw_body is not None:
            payload = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
        elif body is not None:
            payload = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json; charset=utf-8"
        if payload:
            h["Content-Length"] = str(len(payload))
        if headers:
            h.update(headers)
        req = "%s %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n" % (method, path, self.port)
        for k, v in h.items():
            req += "%s: %s\r\n" % (k, v)
        req += "\r\n"
        s = socket.create_connection(("127.0.0.1", self.port), 10)
        s.settimeout(30)
        s.sendall(req.encode("utf-8") + payload)
        buf = b""
        while True:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        s.close()
        head, _, body_bytes = buf.partition(b"\r\n\r\n")
        if b"transfer-encoding: chunked" in head.lower():
            body_bytes = dechunk(body_bytes)
        text = head.split(b"\r\n")[0].decode("latin-1")
        code = int(text.split()[1]) if len(text.split()) > 1 else 0
        try:
            obj = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            obj = None
        return code, obj

    def get(self, p):
        return self.call("GET", p)

    def post(self, p, b=None):
        return self.call("POST", p, body=b)

    def put(self, p, b=None):
        return self.call("PUT", p, body=b)

    def delete(self, p, b=None):
        return self.call("DELETE", p, body=b)


def dechunk(data):
    out = b""
    while True:
        line, _, rest = data.partition(b"\r\n")
        try:
            n = int(line.strip().split(b";")[0], 16)
        except Exception:
            return out + data
        if n == 0:
            return out
        out += rest[:n]
        data = rest[n + 2:]


def enc(v):
    return urllib.parse.quote(str(v), safe="")


def multipart(fields, filename, content):
    boundary = "----vditorE2E0123456789"
    out = b""
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, k, v)).encode("utf-8")
    out += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
            "Content-Type: image/png\r\n\r\n" % (boundary, filename)).encode("utf-8")
    out += content + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    return out, "multipart/form-data; boundary=%s" % boundary


def main():
    docs = os.path.join(APP_DIR, "_e2e_docs")
    purge(docs)
    os.makedirs(docs, exist_ok=True)

    env = dict(os.environ)
    # 注意：文档根目录的环境变量是 VDITOR_DOC_DIR（单数，回退用），
    # 不是 VDITOR_DOC_ROOT —— 用错名字会静默回落到工作区默认目录，
    # 导致测试写进真实文档区。
    env["VDITOR_DOC_DIR"] = docs
    env["VDITOR_DOC_DIRS"] = ""          # 不继承外部可能设置的多分区
    env["VDITOR_PASSWORD"] = PASSWORD
    env["VDITOR_PORT"] = str(PORT)
    env["VDITOR_TRUST_PROXY"] = "0"
    env["VDITOR_SECURE_COOKIE"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'%s'); "
         "import runpy; runpy.run_path(r'%s', run_name='__main__')"
         % (os.path.join(APP_DIR, "vditor-fpk", "app"),
            os.path.join(APP_DIR, "vditor-fpk", "app", "server.py"))],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        if not wait_port(PORT):
            print("!! 服务端未能启动")
            out = proc.stdout.read(4000).decode("utf-8", "replace") if proc.stdout else ""
            print(out)
            return 1

        c = Client(PORT)

        print("\n== 1. 登录（App：health 探活 -> login）==")
        code, r = c.get("/api/m/health")
        check("health", code == 200 and r and r.get("ok"), str(r)[:120])
        d = r.get("data") or {}
        check("字段 status/app/version/api_version",
              d.get("status") == "ok" and d.get("app") == "com.mian38.vditor"
              and d.get("api_version") == "m1", str(d)[:160])
        check("字段 setup_completed（App 用它区分未初始化）",
              "setup_completed" in d, str(d)[:160])

        code, r = c.post("/api/m/auth/login", {"password": PASSWORD})
        check("login", code == 200 and r.get("ok"), str(r)[:120])
        d = r.get("data") or {}
        c.token = d.get("token", "")
        check("字段 token/expires_in/idle_expires_in",
              bool(c.token) and "expires_in" in d and "idle_expires_in" in d, str(d)[:160])

        print("\n== 2. 分区与列表（App：roots -> files）==")
        code, r = c.get("/api/m/roots")
        check("roots", code == 200 and r.get("ok"), str(r)[:120])
        roots = (r.get("data") or {}).get("roots") or []
        check("roots 字段 id/name/path/hidden/exists",
              bool(roots) and all(k in roots[0] for k in
                                  ("id", "name", "path", "hidden", "exists")),
              str(roots[:1])[:200])
        # 守护：确认分区确实落在临时目录。若环境变量名写错会回落到工作区默认
        # 目录，那就会污染真实文档区——这里显式拦住。
        check("分区路径落在临时目录（未污染工作区）",
              bool(roots) and os.path.abspath(roots[0]["path"]) == os.path.abspath(docs),
              "got %r want %r" % (roots[0]["path"] if roots else None, docs))
        root_id = roots[0]["id"] if roots else ""

        code, r = c.get("/api/m/files?root=%s" % enc(root_id))
        check("files", code == 200 and r.get("ok"), str(r)[:120])
        d = r.get("data") or {}
        check("files 字段 items/total/limit/offset",
              all(k in d for k in ("items", "total", "limit", "offset")), str(d)[:160])
        check("干净起点 -> items=[]（App 走空态）", d.get("items") == [], str(d)[:200])

        print("\n== 3. 新建（App：createFile(root, path, content)）==")
        code, r = c.post("/api/m/file",
                         {"root": root_id, "path": "e2e/e2e", "content": "# 标题\n\n第一版\n"})
        check("create", code == 200 and r.get("ok"), str(r)[:200])
        doc = r.get("data") or {}
        check("详情字段 id/name/path/root/content/size/version/updated_at/assets",
              all(k in doc for k in ("id", "name", "path", "root", "content",
                                     "size", "version", "updated_at", "assets")),
              str(doc)[:220])
        v1 = doc.get("version", 0)
        check("version 初始为 1", v1 == 1, "got %r" % v1)
        check("assets 初始为空数组", doc.get("assets") == [], str(doc.get("assets")))
        doc_path = doc.get("path")

        code, r = c.post("/api/m/file",
                         {"root": root_id, "path": "e2e/e2e", "content": "x"})
        check("重名 -> CONFLICT(409)", code == 409 and r.get("error") == "CONFLICT",
              "%s %s" % (code, r.get("error") if r else None))

        print("\n== 4. 读取（App：file(root, path)）==")
        code, r = c.get("/api/m/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)))
        check("file", code == 200 and r.get("ok"), str(r)[:160])
        d = r.get("data") or {}
        check("content 往返一致", "第一版" in (d.get("content") or ""), str(d.get("content"))[:80])
        v1 = d.get("version")

        print("\n== 5. 保存 + 乐观锁（App：saveFile(..., if_version)）==")
        code, r = c.put("/api/m/file",
                        {"root": root_id, "path": doc_path,
                         "content": "# 标题\n\n第二版\n", "if_version": v1})
        check("save", code == 200 and r.get("ok"), str(r)[:160])
        v2 = (r.get("data") or {}).get("version")
        check("version 递增", isinstance(v2, int) and v2 > v1, "%r -> %r" % (v1, v2))

        # 用过期版本号再存一次：必须被拒（App 靠这个弹「保存冲突」）
        code, r = c.put("/api/m/file",
                        {"root": root_id, "path": doc_path,
                         "content": "第三版\n", "if_version": v1})
        check("过期 if_version -> FORBIDDEN(403)",
              code == 403 and r.get("error") == "FORBIDDEN",
              "%s %s" % (code, r.get("error") if r else None))

        code, r = c.get("/api/m/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)))
        check("冲突后服务端内容未被覆盖",
              "第二版" in ((r.get("data") or {}).get("content") or ""),
              str((r.get("data") or {}).get("content"))[:80])

        # 再来一次**合法**保存：此时应产生第二份历史快照
        code, r = c.get("/api/m/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)))
        v_now = (r.get("data") or {}).get("version")
        code, r = c.put("/api/m/file",
                        {"root": root_id, "path": doc_path,
                         "content": "# 标题\n\n第四版\n", "if_version": v_now})
        check("再次合法保存", code == 200 and r.get("ok"), str(r)[:160])

        print("\n== 6. 附件（App：uploadLimits -> upload -> insert_text）==")
        code, r = c.get("/api/m/settings/upload")
        check("uploadLimits", code == 200 and r.get("ok"), str(r)[:160])
        lim = r.get("data") or {}
        check("限制字段 max_mb/min_mb/max_mb_limit/deny_exts/default_deny_exts",
              all(k in lim for k in ("max_mb", "min_mb", "max_mb_limit",
                                     "deny_exts", "default_deny_exts")),
              str(lim)[:200])

        png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)      # 伪 PNG，仅测通路
        body, ctype = multipart({"root": root_id, "path": doc_path}, "shot.png", png)
        code, r = c.call("POST", "/api/m/upload", raw_body=body,
                         headers={"Content-Type": ctype})
        check("upload", code == 200 and r.get("ok"), str(r)[:200])
        up = r.get("data") or {}
        check("上传返回 name/url/ext/size/insert_text",
              all(k in up for k in ("name", "url", "ext", "size", "insert_text")),
              str(up)[:200])
        check("insert_text 是 Markdown 图片引用（App 直接插这句）",
              (up.get("insert_text") or "").startswith("![]("),
              str(up.get("insert_text")))

        # 黑名单必须真的拦住（回归 is_denied_upload 传裸扩展名那个坑）
        body, ctype = multipart({"root": root_id, "path": doc_path}, "bad.exe", b"MZ")
        code, r = c.call("POST", "/api/m/upload", raw_body=body,
                         headers={"Content-Type": ctype})
        check(".exe 被黑名单拦下DENIED_EXT(400)",
              code == 400 and r.get("error") == "DENIED_EXT",
              "%s %s" % (code, r.get("error") if r else None))

        code, r = c.post("/api/m/file/assets", {"root": root_id, "path": doc_path})
        check("assets 列表", code == 200 and r.get("ok"), str(r)[:160])
        assets = (r.get("data") or {}).get("assets") or []
        check("assets 含刚上传的 png", any(a.get("ext") == "png" for a in assets),
              str(assets)[:200])
        check("assets 元素字段 name/url/size/ext",
              bool(assets) and all(k in assets[0] for k in ("name", "url", "size", "ext")),
              str(assets[:1])[:200])

        code, r = c.get("/api/m/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)))
        d = r.get("data") or {}
        check("文档详情的 assets 已含新附件", len(d.get("assets") or []) >= 1,
              str(d.get("assets"))[:200])

        print("\n== 7. 历史版本与回滚（App：versions -> restore）==")
        code, r = c.get("/api/m/file/versions?root=%s&path=%s" % (enc(root_id), enc(doc_path)))
        check("versions", code == 200 and r.get("ok"), str(r)[:160])
        items = (r.get("data") or {}).get("items") or []
        check("至少 2 个版本（两次保存）", len(items) >= 2, "got %d" % len(items))
        check("版本元素字段 version/created_at/size/source/comment",
              bool(items) and all(k in items[0] for k in
                                  ("version", "created_at", "size", "source", "comment")),
              str(items[:1])[:200])
        check("version 是毫秒时间戳（不是序号）",
              bool(items) and isinstance(items[0].get("version"), int)
              and items[0]["version"] > 10 ** 12,
              str(items[:1])[:200])
        oldest = min(items, key=lambda x: x["version"])

        code, r = c.post("/api/m/file/versions/restore",
                         {"root": root_id, "path": doc_path, "version": oldest["version"]})
        check("restore", code == 200 and r.get("ok"), str(r)[:200])
        code, r = c.get("/api/m/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)))
        check("回滚后内容为第一版",
              "第一版" in ((r.get("data") or {}).get("content") or ""),
              str((r.get("data") or {}).get("content"))[:80])

        print("\n== 8. 目录与删除（App：files(is_dir) -> deleteFile）==")
        code, r = c.get("/api/m/files?root=%s" % enc(root_id))
        names = [i.get("name") for i in ((r.get("data") or {}).get("items") or [])]
        check("目录 e2e 出现在列表（is_dir=True）", "e2e" in names, str(names)[:160])
        e2e_item = [i for i in (r.get("data") or {}).get("items") or []
                    if i.get("name") == "e2e"]
        check("目录项 is_dir=True",
              bool(e2e_item) and e2e_item[0].get("is_dir") is True, str(e2e_item[:1])[:160])
        check("文档同名文件夹未被暴露为目录",
              names.count("e2e") == 1, str(names)[:160])

        code, r = c.delete("/api/m/file", {"root": root_id, "path": doc_path})
        check("delete", code == 200 and r.get("ok"), str(r)[:200])
        code, r = c.get("/api/m/file?root=%s&path=%s" % (enc(root_id), enc(doc_path)))
        check("删除后 404", code == 404 and r.get("error") == "NOT_FOUND",
              "%s %s" % (code, r.get("error") if r else None))

        print("\n== 9. 登出（App：logout 后清 token）==")
        code, r = c.post("/api/m/auth/logout")
        check("logout", code == 200 and r.get("ok"), str(r)[:120])
        saved = c.token
        c.token = ""
        code, r = c.get("/api/m/roots")
        check("登出后 token 失效 INVALID_TOKEN(401)",
              code == 401 and r.get("error") == "INVALID_TOKEN",
              "%s %s" % (code, r.get("error") if r else None))
        c.token = "not-a-real-token"
        code, r = c.get("/api/m/roots")
        check("伪造 token 同样被拒", code == 401, str(code))
        c.token = saved
        code, r = c.post("/api/m/auth/logout")
        check("重复登出幂等", code == 200 and r.get("ok"), str(r)[:120])

        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
        purge(docs)


if __name__ == "__main__":
    rc = main()
    # 守护放在收尾处：服务端子进程已终止、句柄已释放，此时检查污染才准确
    if not assert_no_pollution():
        FAILED_ITEMS.append("污染 vditor-fpk/app/docs")
        FAIL += 1
    print("\n" + "=" * 60)
    print("RESULT(e2e): passed=%d failed=%d" % (PASS, FAIL))
    if FAILED_ITEMS:
        for f in FAILED_ITEMS:
            print("  - " + f)
    print("=" * 60)
    sys.exit(rc if rc else (0 if FAIL == 0 else 1))
