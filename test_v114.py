#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""v1.1.4 专项测试：定向验证本轮两项修复。

覆盖：
  #1 黑名单行「添加 / 恢复默认」按钮与输入框对齐（CSS 特异性须压过 .set-sec button.action 的上边距）
  #2 「恢复默认」后可保存（默认清单含 appref-ms，连字符扩展名必须被判合法）
      + 连字符扩展名落盘后可访问（UPLOAD_NAME_RE 须接受 '-'）
      + 非法项仍被拒（../bad、超长、纯连字符）
"""
import os, sys, json, time, tempfile, subprocess, urllib.request, urllib.error, shutil, re

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
PY = sys.executable

passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


def start_server(port, cfg):
    docs = os.path.join(cfg, "docs")
    os.makedirs(docs, exist_ok=True)
    env = dict(os.environ)
    env.update({"VDITOR_CONFIG": cfg, "VDITOR_PORT": str(port), "VDITOR_HOST": "127.0.0.1",
                "VDITOR_DOC_DIR": docs, "VDITOR_DOC_NAME": "docs"})
    proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    proc._port = port
    return proc


def req_full(proc, method, path, body=None, headers=None, raw=False):
    URL = "http://127.0.0.1:%d" % proc._port
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        hdrs = dict(resp.headers.items())
        rb = resp.read().decode()
        return resp.status, (rb if raw else json.loads(rb or "{}")), hdrs
    except urllib.error.HTTPError as e:
        hdrs = dict(e.headers.items())
        rb = e.read().decode()
        try:
            return e.code, (rb if raw else json.loads(rb or "{}")), hdrs
        except Exception:
            return e.code, {}, hdrs


def req(proc, method, path, body=None, headers=None):
    st, d, _ = req_full(proc, method, path, body, headers)
    return st, d


def cookie_of(h):
    sc = h.get("Set-Cookie", "")
    return sc.split(";")[0] if sc else ""


LAN = {"X-Forwarded-For": "127.0.0.1"}
_H = {}


def upload_file(proc, fname, content="x"):
    b = content.encode() if isinstance(content, str) else content
    bd = "----vd114b"
    parts = [("--%s\r\n" % bd).encode(),
             b'Content-Disposition: form-data; name="root"\r\n\r\n', b"\r\n",
             ("--%s\r\n" % bd).encode(),
             b'Content-Disposition: form-data; name="path"\r\n\r\n', b"\r\n",
             ("--%s\r\n" % bd).encode(),
             ('Content-Disposition: form-data; name="file[]"; filename="%s"\r\n' % fname).encode(),
             b"Content-Type: application/octet-stream\r\n\r\n", b,
             ("\r\n--%s--\r\n" % bd).encode()]
    h = dict(_H)
    h["Content-Type"] = "multipart/form-data; boundary=%s" % bd
    r = urllib.request.Request("http://127.0.0.1:%d/api/upload" % proc._port,
                              data=b"".join(parts), headers=h, method="POST")
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def uploaded(proc, fname, content="x"):
    st, d = upload_file(proc, fname, content)
    err = (d.get("data") or {}).get("errFiles") or []
    if st != 200:
        return False, ["<http %d>" % st]
    return fname not in err, err


# =================Server：默认清单可保存 & 连字符扩展名 =================
print("== Server: restore-default must be saveable ==")
tmp = tempfile.mkdtemp(prefix="vd114_")
p = start_server(9351, tmp)
st, d, h = req_full(p, "POST", "/api/setup", {"password": "secret123"}, headers=LAN)
check("setup ok", st == 200 and d.get("ok"), str((st, d)))
auth = {**LAN, "Cookie": cookie_of(h)}
_H = auth

st, d = req(p, "GET", "/api/settings", headers=auth)
deny = d.get("settings", {}).get("upload_deny", "")
check("default deny contains appref-ms", "appref-ms" in deny.split(","), repr(deny))
check("default deny entry count >= 68", len(deny.split(",")) >= 68, str(len(deny.split(","))))

# #2 核心回归：模拟前端「恢复默认」→ 把整份默认清单提交保存，必须成功
st, d = req(p, "POST", "/api/settings", {"upload_deny": deny}, headers=auth)
check("restore-default save succeeds", st == 200 and d.get("ok"), str((st, d))[:200])
check("no '不合法' error after restore", "不合法" not in str(d.get("error", "")), str(d.get("error")))
saved = d.get("settings", {}).get("upload_deny", "")
check("appref-ms persisted after save", "appref-ms" in saved.split(","), repr(saved)[:120])

# 连字符扩展名确实被黑名单命中
globals()["_p"] = p
ok, err = uploaded(p, "x.appref-ms")
check("hyphen ext denied by default blacklist", (not ok) and "x.appref-ms" in err, str(err))

# 用户移除 appref-ms 后可上传，且落盘文件能被取回（UPLOAD_NAME_RE 须接受 '-'）
req(p, "POST", "/api/settings", {"upload_deny": "exe,dll"}, headers=auth)
ok, err = uploaded(p, "doc.appref-ms")
check("hyphen ext allowed after removal", ok, str(err))
st, d = upload_file(p, "doc.appref-ms", "hello")
store = (d.get("data") or {}).get("succMap", {}).get("doc.appref-ms")
check("hyphen ext stored", bool(store), str(d))
if store:
    st2, _, h2 = req_full(p, "GET", "/" + store, headers=auth, raw=True)
    check("hyphen ext retrievable (no 404)", st2 == 200, str(st2))
    cd = h2.get("Content-Disposition", "")
    check("hyphen ext forced download + sandbox", "attachment" in cd and "sandbox" in h2.get("Content-Security-Policy", ""),
          str((cd, h2.get("Content-Security-Policy"))))

# 非法项仍被拒（修复不能放松校验）
st, d = req(p, "POST", "/api/settings", {"upload_deny": "exe,../bad,waytoolongnamehere"}, headers=auth)
check("illegal ext still rejected", st == 200 and not d.get("ok"), str((st, d))[:160])
check("illegal msg names all offenders",
      all(k in str(d.get("error", "")) for k in ("bad", "waytoolongnamehere")), str(d.get("error")))

# ================= 纯函数层校验（vd_util） =================
print("== vd_util validators ==")
sys.path.insert(0, APP)
from vd_util import (DEFAULT_UPLOAD_DENY, normalize_ext_list, UPLOAD_NAME_RE,  # noqa: E402
                     is_denied_upload)
check("appref-ms survives normalize", "appref-ms" in normalize_ext_list(DEFAULT_UPLOAD_DENY), "")
check("normalize keeps hyphen inside", normalize_ext_list("appref-ms") == ["appref-ms"], str(normalize_ext_list("appref-ms")))
check("normalize strips leading dot + case", normalize_ext_list(".EXE") == ["exe"], "")
check("normalize drops leading-hyphen token", normalize_ext_list("-exe") == [], str(normalize_ext_list("-exe")))
check("normalize drops bare hyphen", normalize_ext_list("-") == [], "")
check("normalize drops traversal", normalize_ext_list("../bad") == [], "")
check("normalize drops overlong", normalize_ext_list("waytoolongnamehere") == [], "")
check("normalize accepts max length 12", normalize_ext_list("abcdefghijkl") == ["abcdefghijkl"], "")
check("normalize drops 13 chars", normalize_ext_list("abcdefghijklm") == [], "")
check("UPLOAD_NAME_RE accepts hyphen", bool(UPLOAD_NAME_RE.match("a" * 32 + ".appref-ms")), "")
check("UPLOAD_NAME_RE still anchored", not UPLOAD_NAME_RE.match("a" * 31 + ".png"), "")
check("is_denied_upload matches hyphen", is_denied_upload("x.appref-ms", DEFAULT_UPLOAD_DENY) == "appref-ms", "")
# 默认清单幂等：清洗两次结果一致（保存不会自我破坏）
once = normalize_ext_list(DEFAULT_UPLOAD_DENY)
twice = normalize_ext_list(",".join(once))
check("default list idempotent", once == twice, str(set(once) ^ set(twice)))

# ================= 静态断言：CSS 对齐 + 前端校验器 =================
print("== Static: CSS alignment & frontend validator ==")
html = open(os.path.join(APP, "index.html"), encoding="utf-8").read()

# #1 对齐：须存在高特异性重置规则，压过 .set-sec button.action 的上边距。
#      注意：胜负由「特异性」决定，与先后顺序无关——不能断言 override 出现在其后。
m_reset = re.search(r"\.set-sec \.set-ext-row button\.action \{ margin: 0", html)
m_other = re.search(r"\.set-sec button\.action \{ margin: 10px 8px 0 0; \}", html)
check("both rules found", bool(m_reset and m_other), "")


def _spec(sel):
    """粗算 CSS 特异性：(类/属性/伪类 个数, 元素/伪元素 个数)。"""
    ids = sel.count("#")
    parts = re.split(r"[ .>+~]+", sel.strip())
    cls = sum(1 for p in parts if p and p not in (".", ">", "+", "~", " ") and not p.isdigit())
    # 去掉开头的点后再数元素：div / button 各算 1 个元素
    elems = sum(1 for p in parts if p and not p.startswith(("[", ":", ".")))
    return (ids, cls, elems)


if m_reset and m_other:
    s_reset = _spec(".set-sec .set-ext-row button.action")
    s_other = _spec(".set-sec button.action")
    check("override has higher specificity than .set-sec button.action",
          s_reset > s_other,
          "%s should beat %s" % (s_reset, s_other))
    # 即便 override 出现在前面也必须赢——这是选择提高特异性的意义所在
    check("override wins regardless of source order",
          m_reset.start() > m_other.start() or s_reset > s_other, "")
# 特异性手工核算：.set-sec .set-ext-row button.action = 3 类 + 1 元素 > .set-sec button.action = 2 类 + 1 元素
check("specificity documented in css comment",
      "特异性" in html and "(0,3,1)" in html, "缺少特异性说明注释")
check("set-ext-row uses flex + center align",
      ".set-ext-row { display: flex; gap: 8px; align-items: center; }" in html, "")

# #2 前端校验器须允许连字符
check("frontend validator allows hyphen",
      "/^[A-Za-z0-9][A-Za-z0-9-]{0,11}$/" in html, "前端 denyTokenValid 未更新")
check("frontend message mentions hyphen",
      "仅含字母 / 数字 / 连字符" in html, "")
check("frontend default list keeps appref-ms", "'appref-ms'" in html, "")
check("server message mentions hyphen",
      "仅含字母 / 数字 / 连字符" in open(os.path.join(APP, "server.py"), encoding="utf-8").read(), "")

# ================= 版本号 =================
check("APP_VERSION = 1.2.0", 'APP_VERSION = "1.2.0"' in
      open(os.path.join(APP, "server.py"), encoding="utf-8").read(), "")
check("manifest version=1.2.0", "version=1.2.0" in
      open(os.path.join(BASE, "vditor-fpk", "manifest"), encoding="utf-8").read(), "")

try:
    p.terminate()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)

print("\nRESULT(1.1.4): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)