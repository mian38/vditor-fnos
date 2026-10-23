#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_concurrent_save.py —— 并发保存防回归测试（1.6.0）

背景：ThreadingHTTPServer 每请求一线程，多标签页 / 多实例对同一文档并发保存时，
旧实现「读旧内容 → 归档历史版本 → 直接 open("w") 写」存在三类风险：
  1. 后写覆盖先写——败者内容既非当前、也未被归档，不可恢复丢失；
  2. 截断 + 非原子写，重叠窗口内可能留下半截 / 交错损坏内容；
  3. 版本归档两处都存同一旧版，无法用于恢复。

修复方式（vditor-fpk/app/server.py）：
  - SAVE_LOCK 串行化「读旧内容 → 归档历史版本 → 写文件」整个临界区；
  - 写盘改「同目录临时文件 + os.replace」原子替换。

本测试并发向同一文档发多个不同内容的 /api/save，逐轮断言：
  1. 最终磁盘文件完整等于某一个请求的内容（无损坏、无交错、无半截）；
  2. 无 .tmp.* 临时文件残留；
  3. 败者内容被归档进历史版本目录（可恢复）；
  4. 多轮压测（含大内容轮）不稳定失败。

直接运行：python tests/test_concurrent_save.py
"""
import os
import sys
import io
import json
import time
import socket
import tempfile
import subprocess
import shutil
import threading
import urllib.request
import urllib.error
import urllib.parse

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


# ---------------- 启动后端（空闲端口 + 临时目录，约定同 test_core） ----------------
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


port = free_port()
tmp = tempfile.mkdtemp(prefix="vdsave_")
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
        resp = urllib.request.urlopen(r, timeout=30)
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


print("== 并发保存防回归测试（1.6.0）==")

try:
    # ---------- 登录 ----------
    st, d, _, _ = req("POST", "/api/setup", {"password": "secret123"})
    check("setup 返回 ok", st == 200 and d.get("ok"), (st, d))
    st, d, _, ck2 = req("POST", "/api/login", {"password": "secret123"})
    check("login 成功并下发 Cookie", st == 200 and bool(ck2), (st, d))
    cookie = ck2

    # 默认分区 id（slugify("我的文档")）
    rid = "我的文档"
    doc = "cs_smoke.md"
    fp = os.path.join(docdir, doc)

    # 版本目录定位：与 server._version_dir 同一算法（从 vd_util 导入，避免写死）
    sys.path.insert(0, APP)
    from vd_util import _version_key
    vdir = os.path.join(docdir, ".vditor_versions", _version_key(doc))

    def version_texts():
        out = []
        if not os.path.isdir(vdir):
            return out
        for n in os.listdir(vdir):
            if not n.endswith(".md"):
                continue
            try:
                with io.open(os.path.join(vdir, n), encoding="utf-8") as f:
                    out.append(f.read())
            except (OSError, UnicodeDecodeError):
                pass
        return out

    # ---------- 初始内容 ----------
    st, d, _, _ = req("POST", "/api/save", {"root": rid, "path": doc, "content": "base-v0"},
                      cookie=cookie)
    check("初始保存成功", st == 200 and d.get("ok"), (st, d))

    # ---------- 并发保存：多轮 × 每轮多线程同时发 ----------
    def concurrent_round(round_no, conc, filler):
        """一轮：conc 个线程经 barrier 对齐后同时保存不同内容。"""
        contents = ["r%d-c%d|%s" % (round_no, i, filler) for i in range(conc)]
        barrier = threading.Barrier(conc)
        results = [None] * conc
        errors = []

        def worker(i):
            try:
                barrier.wait(timeout=10)
                st, d, _, _ = req("POST", "/api/save",
                                  {"root": rid, "path": doc, "content": contents[i]},
                                  cookie=cookie)
                results[i] = (st, d)
            except Exception as e:                      # noqa: BLE001
                errors.append(repr(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(conc)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        return contents, results, errors

    ROUNDS = 10
    for rnd in range(ROUNDS):
        contents, results, errors = concurrent_round(rnd, 2, "x" * 64)
        tag = "第 %d 轮" % (rnd + 1)
        check("%s 两个并发保存均返回 ok" % tag,
              not errors and all(r is not None and r[0] == 200 and r[1].get("ok")
                                 for r in results), (errors, results))
        # 磁盘内容必须完整等于其中一个（无半截 / 交错 / 串数据）
        with io.open(fp, encoding="utf-8") as f:
            disk = f.read()
        check("%s 磁盘内容完整等于某一请求内容" % tag, disk in contents,
              repr(disk[:80]))
        # 败者必须被归档为历史版本（可恢复）
        losers = [c for c in contents if c != disk]
        vtexts = version_texts()
        for lc in losers:
            check("%s 败者内容已归档可恢复" % tag, lc in vtexts,
                  "loser=%r 版本数=%d" % (lc[:40], len(vtexts)))
        # 无临时文件残留
        leftovers = [n for n in os.listdir(docdir) if ".tmp." in n]
        check("%s 无 .tmp 临时文件残留" % tag, not leftovers, leftovers)

    # ---------- 大内容并发（放大截断窗口，旧实现更易出现半截损坏） ----------
    big = "并发保存测试大内容|" + ("y" * 200000)
    contents, results, errors = concurrent_round(999, 2, big)
    check("大内容轮 两个并发保存均返回 ok",
          not errors and all(r is not None and r[0] == 200 and r[1].get("ok")
                             for r in results), (errors, results))
    with io.open(fp, encoding="utf-8") as f:
        disk = f.read()
    check("大内容轮 磁盘内容完整等于某一请求内容", disk in contents,
          "len=%d 期望=%d" % (len(disk), len(big) + 20))
    losers = [c for c in contents if c != disk]
    vtexts = version_texts()
    for lc in losers:
        check("大内容轮 败者内容已归档可恢复", lc in vtexts,
              "len(loser)=%d 版本数=%d" % (len(lc), len(vtexts)))
    leftovers = [n for n in os.listdir(docdir) if ".tmp." in n]
    check("大内容轮 无 .tmp 临时文件残留", not leftovers, leftovers)

    # ---------- 并发不影响其它文档 ----------
    other = "cs_other.md"
    st, d, _, _ = req("POST", "/api/save", {"root": rid, "path": other, "content": "other-v1"},
                      cookie=cookie)
    check("其它文档保存不受影响", st == 200 and d.get("ok"), (st, d))
    with io.open(os.path.join(docdir, other), encoding="utf-8") as f:
        check("其它文档内容正确", f.read() == "other-v1")

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

print("-" * 60)
print("RESULT 通过 %d，失败 %d" % (passed, failed))
sys.exit(1 if failed else 0)
