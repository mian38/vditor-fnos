#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试：飞牛文件夹来源解析（冒号分隔 TRIM_DATA_SHARE_PATHS / shares/ / share_paths 文件）
          + 应用内文件夹管理 API 增删与持久化。"""
import os, sys, time, shutil, subprocess, tempfile, json, http.client, urllib.parse

PY = sys.executable
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vditor-nas", "server.py")

tmp = tempfile.mkdtemp(prefix="vdtestB_")
# 各类来源目录
ds_a = os.path.join(tmp, "shareA"); ds_b = os.path.join(tmp, "shareB")
appdest = os.path.join(tmp, "appdest"); shares = os.path.join(appdest, "shares")
os.makedirs(ds_a); os.makedirs(ds_b); os.makedirs(shares)
os.makedirs(os.path.join(shares, "extraShare"))   # data-share 软链/目录
pkgvar = os.path.join(tmp, "pkgvar"); os.makedirs(pkgvar)
with open(os.path.join(pkgvar, "share_paths"), "w", encoding="utf-8") as f:
    f.write('"%s"\n' % os.path.join(tmp, "fromFile"))   # share_paths 文件
os.makedirs(os.path.join(tmp, "fromFile"))
cfg = os.path.join(tmp, "cfg"); os.makedirs(cfg)

PORT = 9124
env = dict(os.environ)
env.update({
    "VDITOR_PORT": str(PORT),
    "VDITOR_HOST": "127.0.0.1",
    "TRIM_DATA_SHARE_PATHS": "%s:%s" % (ds_a, ds_b),   # 冒号分隔（飞牛实际格式）
    "TRIM_APPDEST": appdest,
    "TRIM_PKGVAR": pkgvar,
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
            data = json.dumps(body).encode("utf-8"); hdrs["Content-Type"] = "application/json"
        else:
            data = body
    h.request(method, path, body=data, headers=hdrs)
    r = h.getresponse(); txt = r.read().decode("utf-8", "replace")
    sc = r.getheader("Set-Cookie"); h.close()
    return r.status, txt, (sc.split(";")[0] if sc else "")

def check(name, cond, detail=""):
    results.append((name, cond, detail)); print(("PASS " if cond else "FAIL ")+name+(("  -> "+detail) if detail else ""))

try:
    # 首次设置并登录
    st, _, cookie = call("POST", "/api/setup", {"password": "Secret123"})
    check("首次设置密码", st == 200, "")
    st, body, _ = call("GET", "/api/auth/check", headers={"Cookie": cookie})
    check("已登录", json.loads(body).get("authenticated") is True, "")

    # 多来源分区：shareA, shareB(冒号), extraShare(shares/), fromFile(share_paths文件)
    st, body, _ = call("GET", "/api/files", headers={"Cookie": cookie})
    roots = json.loads(body).get("roots", [])
    names = {r["name"] for r in roots}
    check("冒号分隔 TRIM_DATA_SHARE_PATHS 解析为独立分区", {"shareA", "shareB"}.issubset(names), str(names))
    check("shares/ 目录被识别为分区(extraShare)", "extraShare" in names, str(names))
    check("share_paths 文件被识别为分区(fromFile)", "fromFile" in names, str(names))
    check("共 4 个分区来源", len(roots) == 4, "roots=%d" % len(roots))

    # 应用内新增文件夹（持久化）
    st, body, _ = call("POST", "/api/folders", {"action": "add", "name": "我的笔记", "path": os.path.join(tmp, "managedDir")},
                       headers={"Cookie": cookie})
    check("新增应用内文件夹", st == 200 and json.loads(body).get("ok"), body)
    st, body, _ = call("GET", "/api/files", headers={"Cookie": cookie})
    roots = json.loads(body).get("roots", [])
    check("新增后分区数=5", len(roots) == 5, "roots=%d" % len(roots))
    check("新增分区名=我的笔记", any(r["name"] == "我的笔记" for r in roots), str([r["name"] for r in roots]))
    # 持久化校验
    folders_json = os.path.join(cfg, "folders.json")
    check("folders.json 已写入", os.path.isfile(folders_json), "")
    with open(folders_json, encoding="utf-8") as f:
        fj = json.load(f)
    check("folders.json 含新增路径", any(x["path"] == os.path.join(tmp, "managedDir") for x in fj), str(fj))

    # 重复添加为幂等（已存在则不重复添加，返回 200 且仍由应用内管理）
    st, body, _ = call("POST", "/api/folders", {"action": "add", "name": "x", "path": os.path.join(tmp, "managedDir")}, headers={"Cookie": cookie})
    check("重复添加为幂等(返回200)", st == 200, "status=%d" % st)
    check("重复添加后仍由应用内管理", any(os.path.abspath(x["path"]) == os.path.abspath(os.path.join(tmp, "managedDir")) for x in json.loads(body).get("managed", [])), body)

    # 删除应用内文件夹
    st, body, _ = call("POST", "/api/folders", {"action": "remove", "path": os.path.join(tmp, "managedDir")}, headers={"Cookie": cookie})
    check("删除应用内文件夹", st == 200 and json.loads(body).get("ok"), body)
    st, body, _ = call("GET", "/api/files", headers={"Cookie": cookie})
    check("删除后分区数回到 4", len(json.loads(body).get("roots", [])) == 4, "roots=%d" % len(json.loads(body).get("roots", [])))

    # 系统默认分区：隐藏（删除）后可恢复（item #8）
    st, body, _ = call("POST", "/api/folders", {"action": "remove", "path": ds_a}, headers={"Cookie": cookie})
    check("隐藏系统分区 shareA", st == 200 and json.loads(body).get("ok"), body)
    st, body, _ = call("GET", "/api/files", headers={"Cookie": cookie})
    roots = json.loads(body).get("roots", [])
    check("隐藏后 shareA 不再作为分区出现", not any(r["path"] == ds_a for r in roots), str([r["name"] for r in roots]))
    st, body, _ = call("POST", "/api/folders", {"action": "restore", "path": ds_a}, headers={"Cookie": cookie})
    check("恢复系统分区 shareA", st == 200 and json.loads(body).get("ok"), body)
    st, body, _ = call("GET", "/api/files", headers={"Cookie": cookie})
    roots = json.loads(body).get("roots", [])
    check("恢复后 shareA 重新出现", any(r["path"] == ds_a for r in roots), str([r["name"] for r in roots]))

finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

passed = sum(1 for _, c, _ in results if c)
print("\n=== 结果: %d/%d 通过 ===" % (passed, len(results)))
sys.exit(0 if passed == len(results) else 1)
