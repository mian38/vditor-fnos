#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地端到端测试：验证 Request4 三项功能（多分区 / 安全 / API 门禁）"""
import os, sys, time, shutil, subprocess, tempfile, json, http.client, urllib.parse

PY = sys.executable
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vditor-nas", "server.py")

tmp = tempfile.mkdtemp(prefix="vdtest_")
root_a = os.path.join(tmp, "Notes")
root_b = os.path.join(tmp, "Essays")
os.makedirs(root_a); os.makedirs(root_b)
cfg = os.path.join(tmp, "cfg")
os.makedirs(cfg)

PORT = 9123
env = dict(os.environ)
env.update({
    "VDITOR_PORT": str(PORT),
    "VDITOR_HOST": "127.0.0.1",
    "VDITOR_DOC_DIRS": "工作笔记::%s,个人随笔::%s" % (root_a, root_b),
    "VDITOR_CONFIG": cfg,
    "VDITOR_TRUST_PROXY": "0",
})

proc = subprocess.Popen([PY, SRC], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(2.0)

BASE = "127.0.0.1:%d" % PORT
results = []
def call(method, path, body=None, headers=None):
    h = http.client.HTTPConnection(BASE, timeout=5)
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        if isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        else:
            data = body
    h.request(method, path, body=data, headers=hdrs)
    r = h.getresponse()
    txt = r.read().decode("utf-8", "replace")
    sc = r.getheader("Set-Cookie")
    h.close()
    cookie = sc.split(";")[0] if sc else ""
    return r.status, txt, cookie

def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))

try:
    # 1. 未认证访问受保护 API 应 401
    st, _, _ = call("GET", "/api/files")
    check("未登录访问 /api/files 返回 401", st == 401, "status=%d" % st)

    # 2. 首次设置状态
    st, body, _ = call("GET", "/api/auth/check")
    d = json.loads(body)
    check("auth/check 返回 needsSetup=true", d.get("needsSetup") is True, body)

    # 3. 首次设置密码（并捕获会话 Cookie）
    st, body, cookie = call("POST", "/api/setup", {"password": "Secret123"})
    check("首次设置密码成功", st == 200 and json.loads(body).get("ok") is True, body)
    check("首次设置下发会话 Cookie", bool(cookie), cookie)

    # 4. 设置后 authenticated=true
    st, body, _ = call("GET", "/api/auth/check", headers={"Cookie": cookie})
    d = json.loads(body)
    check("设置后 authenticated=true", d.get("authenticated") is True, body)

    # 5. 多分区文件列表：应有两个 root
    st, body, _ = call("GET", "/api/files", headers={"Cookie": cookie})
    roots = json.loads(body).get("roots", [])
    check("多分区：返回 2 个分区", len(roots) == 2, "roots=%d" % len(roots))
    names = [r["name"] for r in roots]
    check("分区名为工作笔记/个人随笔", "工作笔记" in names and "个人随笔" in names, str(names))
    rid_a = next(r["id"] for r in roots if r["name"] == "工作笔记")

    # 6. 在分区A新建+保存
    st, body, _ = call("POST", "/api/new", {"root": rid_a, "path": "hello.md"}, headers={"Cookie": cookie})
    check("在分区A新建文件", st == 200 and json.loads(body).get("ok"), body)
    st, body, _ = call("POST", "/api/save", {"root": rid_a, "path": "hello.md", "content": "# Hi\n你好"}, headers={"Cookie": cookie})
    check("在分区A保存文件", st == 200 and json.loads(body).get("ok"), body)
    physical = os.path.join(root_a, "hello.md")
    check("文件实际落盘到分区A目录", os.path.isfile(physical), physical)

    # 7. 读取该文件
    q = "/api/file?root=%s&path=%s" % (urllib.parse.quote(rid_a), urllib.parse.quote("hello.md"))
    st, body, _ = call("GET", q, headers={"Cookie": cookie})
    d = json.loads(body)
    check("读取分区A文件内容正确", d.get("content") == "# Hi\n你好", str(d.get("content")))

    # 8. 分区隔离：分区B不应出现分区A的文件
    st, body, _ = call("GET", "/api/files", headers={"Cookie": cookie})
    roots = json.loads(body)["roots"]
    b = next(r for r in roots if r["name"] == "个人随笔")
    check("分区B与分区A隔离(无 hello.md)", all(f["path"] != "hello.md" for f in b["files"]), str([f["path"] for f in b["files"]]))

    # 9. 上传需登录（无 cookie 应 401）
    st, _, _ = call("POST", "/api/upload")
    check("未登录上传被拒(401)", st == 401, "status=%d" % st)

    # 10. 暴力破解锁定：连续错误密码
    call("POST", "/api/logout", headers={"Cookie": cookie})
    locked = False
    fails = 0
    for i in range(6):
        st, _, _ = call("POST", "/api/login", {"password": "wrong"})
        if st == 423:
            locked = True
            break
        fails += 1
    check("连续错误密码触发锁定(423)", locked, "failed_attempts=%d" % fails)

    # 11. 锁定期间正确密码也被拒
    if locked:
        st, _, _ = call("POST", "/api/login", {"password": "Secret123"})
        check("锁定期间正确密码也被拒(423)", st == 423, "status=%d" % st)

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

passed = sum(1 for _, c, _ in results if c)
print("\n=== 结果: %d/%d 通过 ===" % (passed, len(results)))
sys.exit(0 if passed == len(results) else 1)
