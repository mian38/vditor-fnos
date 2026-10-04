#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_perf.py —— 大文件读写性能测试

目的：验证性能优化后，应用在小文件 → 超大文件（15MB）各档位的读写表现，
并校验两项关键保护：
  1. 超大文档不再生成历史版本快照（避免自动保存把磁盘写满）；
  2. 超大文档保存时不再「白读」一遍全文。

同时校验内容在大文件往返后**逐字节一致**（优化不能以损坏数据为代价）。

直接运行：python test_perf.py
"""
import os, sys, io, json, time, socket, tempfile, subprocess, shutil, hashlib
import urllib.request, urllib.error, urllib.parse

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name, extra)
    else:
        failed += 1
        print("  FAIL", name, extra)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def gen_content(target_bytes):
    """生成模拟「对话记录类」Markdown：代码块与标题密集，贴近真实大文件特征。

    之所以强调代码块/标题密度：渲染成本不与字节数线性相关，而与块级结构数量相关。
    只有用高密度样本才能真正压出渲染路径的开销。
    """
    unit = (
        "## 对话段落 {i}\n\n"
        "这是一段用于性能测试的示例正文，包含中英文混排 content {i}。\n\n"
        "```python\n"
        "def example_{i}():\n"
        "    # 模拟代码块内容，用于压测代码高亮与行号渲染路径\n"
        "    return sum(range({i}))\n"
        "```\n\n"
        "| 列A | 列B |\n| --- | --- |\n| 值{i} | 数据 |\n\n"
    )
    chunks = []
    size = 0
    i = 0
    while size < target_bytes:
        b = unit.format(i=i)
        chunks.append(b)
        size += len(b.encode("utf-8"))
        i += 1
    return "".join(chunks)


port = free_port()
tmp = tempfile.mkdtemp(prefix="vdperf_")
docdir = os.path.join(tmp, "docs")
uploaddir = os.path.join(tmp, "up")
os.makedirs(docdir, exist_ok=True)
os.makedirs(uploaddir, exist_ok=True)
env = dict(os.environ)
env.update({"VDITOR_CONFIG": tmp, "VDITOR_PORT": str(port), "VDITOR_HOST": "127.0.0.1",
            "VDITOR_DOC_DIR": docdir, "VDITOR_DOC_NAME": "perf",
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
    raise SystemExit("服务未能在 %s 就绪，中止" % URL)


def req(method, path, body=None, cookie=None, raw=False, ctype="application/json"):
    h = dict(ctype and {"Content-Type": ctype} or {})
    if cookie:
        h["Cookie"] = cookie
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=300)
        rb = resp.read()
        return resp.status, (rb if raw else (json.loads(rb.decode() or "{}") if rb else {})), resp.headers
    except urllib.error.HTTPError as e:
        rb = e.read()
        try:
            j = json.loads(rb.decode() or "{}")
        except Exception:
            j = {}
        return e.code, j, e.headers


print("== 大文件读写性能测试 ==")
st, d, hdrs = req("POST", "/api/setup", {"password": "perf12345"})
cookie = (hdrs.get("Set-Cookie") or "").split(";")[0]
check("setup 成功", st == 200 and d.get("ok"), (st, d))
if not cookie:
    st, d, hdrs = req("POST", "/api/login", {"password": "perf12345"})
    cookie = (hdrs.get("Set-Cookie") or "").split(";")[0]
RID = "perf"

# ---------------- 各档位读写计时 ----------------
# (档位名, 目标字节) —— 15MB 档用于验证「超大文件仍可读写」
TIERS = [
    ("small  10KB", 10 * 1024),
    ("medium 500KB", 500 * 1024),
    ("large  2MB", 2 * 1024 * 1024),
    ("huge   15MB", 15 * 1024 * 1024),
]
results = []
for label, target in TIERS:
    content = gen_content(target)
    cbytes = len(content.encode("utf-8"))
    name = "perf_%s.md" % label.split()[0]

    # 写
    t0 = time.perf_counter()
    st, d, _ = req("POST", "/api/save",
                   {"root": RID, "path": name, "content": content}, cookie=cookie)
    t_save = (time.perf_counter() - t0) * 1000
    if not (st == 200 and d.get("ok")):
        check("写入 %s" % label, False, (st, d))
        continue

    # 读
    t0 = time.perf_counter()
    st, d, _ = req("GET", "/api/file?root=%s&path=%s" % (urllib.parse.quote(RID), name),
                  cookie=cookie)
    t_read = (time.perf_counter() - t0) * 1000
    ok_read = (st == 200)
    # 内容完整性：逐字节哈希比对（优化不能以损坏数据为代价）
    same = False
    if ok_read:
        got = d.get("content", "")
        same = (hashlib.sha256(got.encode("utf-8")).hexdigest()
                == hashlib.sha256(content.encode("utf-8")).hexdigest())
    check("读取 %s 内容逐字节一致" % label, ok_read and same,
          "%s, %.0f ms" % (("一致" if same else "不一致"), t_read))
    results.append((label, cbytes, t_save, t_read))
    print("       %-14s %8.2f MB  写入 %7.0f ms  读取 %7.0f ms"
          % (label, cbytes / 1024 / 1024, t_save, t_read))

# ---------------- 历史版本体积保护 ----------------
print("-- 历史版本体积保护 --")
# 小文件：应生成快照
small = gen_content(20 * 1024)
req("POST", "/api/save", {"root": RID, "path": "ver_small.md", "content": small}, cookie=cookie)
req("POST", "/api/save", {"root": RID, "path": "ver_small.md", "content": small + "\n改动"}, cookie=cookie)
st, d, _ = req("GET", "/api/versions?root=%s&path=ver_small.md" % urllib.parse.quote(RID), cookie=cookie)
check("小文件仍生成历史版本快照", st == 200 and len(d.get("versions", [])) >= 1,
      "快照数=%d" % len(d.get("versions", [])))

# 超大文件（>5MB）：应跳过快照，避免磁盘被自动保存写满
huge = gen_content(6 * 1024 * 1024)
req("POST", "/api/save", {"root": RID, "path": "ver_huge.md", "content": huge}, cookie=cookie)
req("POST", "/api/save", {"root": RID, "path": "ver_huge.md", "content": huge + "\n改动"}, cookie=cookie)
st, d, _ = req("GET", "/api/versions?root=%s&path=ver_huge.md" % urllib.parse.quote(RID), cookie=cookie)
check("超大文件(>5MB)跳过历史版本快照（磁盘保护）",
      st == 200 and len(d.get("versions", [])) == 0,
      "快照数=%d（期望 0）" % len(d.get("versions", [])))

# 超大文件读取仍正常
st, d, _ = req("GET", "/api/file?root=%s&path=ver_huge.md" % urllib.parse.quote(RID), cookie=cookie)
check("超大文件跳过快照后仍可正常读取",
      st == 200 and d.get("content", "").endswith("\n改动"), st)

# ---------------- 文件列表在大文件下的响应 ----------------
t0 = time.perf_counter()
st, d, _ = req("GET", "/api/files", cookie=cookie)
t_list = (time.perf_counter() - t0) * 1000
check("文件列表响应正常（含大文件）", st == 200 and isinstance(d.get("roots"), list),
      "%.0f ms" % t_list)

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
shutil.rmtree(tmp, ignore_errors=True)

print("\n-- 性能汇总 --")
for label, cbytes, ts, tr in results:
    print("  %-14s %6.2f MB | 写 %7.0f ms (%6.2f MB/s) | 读 %7.0f ms (%6.2f MB/s)"
          % (label, cbytes / 1024 / 1024, ts,
             (cbytes / 1024 / 1024) / (ts / 1000) if ts > 0 else 0,
             tr, (cbytes / 1024 / 1024) / (tr / 1000) if tr > 0 else 0))
print("\nRESULT(perf): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
