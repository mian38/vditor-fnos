#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_security.py —— 安全与正确性原语（纯函数，无需启动服务）

覆盖上传黑名单、路径穿越防护、私网 IP 判定、multipart 解析、历史版本键无碰撞、
共享路径收集等核心防御逻辑。这些「静默失效」高发点曾在多个版本反复出现，
现以纯函数单测固化，避免回归。

直接运行：python test_security.py
"""
import os, sys, io

# 直接 import 纯函数模块（无副作用，不触发服务端状态）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vditor-fpk", "app"))
import vd_util as V

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


print("== 安全与正确性原语测试 ==")

# ---------- 1) 上传黑名单 ----------
check("默认清单放行 .md", V.is_denied_upload("note.md", V.DEFAULT_UPLOAD_DENY) == "")
check("默认清单拒绝 .exe", V.is_denied_upload("virus.exe", V.DEFAULT_UPLOAD_DENY) == "exe")
check("默认清单拒绝 .php", V.is_denied_upload("shell.php", V.DEFAULT_UPLOAD_DENY) == "php")
check("无扩展名一律放行", V.is_denied_upload("noext", "") == "")
check("自定义清单生效", V.is_denied_upload("a.js", "js,exe") == "js")
check("空黑名单不误拦", V.is_denied_upload("a.exe", "") == "")

# ---------- 2) 扩展名规范化 ----------
check("大小写/点/去重归一", V.normalize_ext_list("EXE, .php ,php") == ["exe", "php"],
      V.normalize_ext_list("EXE, .php ,php"))
check("重复项去重", V.normalize_ext_list("a,b,c,a") == ["a", "b", "c"])
check("含连字符扩展名保留", "appref-ms" in V.normalize_ext_list("appref-ms"))
check("中文逗号分隔", V.normalize_ext_list("exe，php") == ["exe", "php"])
check("非法项丢弃（过长/空）", V.normalize_ext_list("ok,toolongname123,,") == ["ok"])

# ---------- 3) 路径穿越防护 ----------
base = "/srv/docs"
check("普通子路径允许", V.safe_join(base, "sub/file.md") ==
      os.path.abspath(os.path.join(base, "sub/file.md")))
check("单层 .. 被拒", V.safe_join(base, "../escape") is None)
check("嵌套 .. 被拒", V.safe_join(base, "a/../../x") is None)
# 绝对路径输入：safe_join 会去掉头斜杠并收敛到 base 内，绝不逃逸
joined_abs = V.safe_join(base, "/etc/passwd")
check("绝对路径输入被收敛到 base 内（不逃逸）",
      joined_abs is not None and joined_abs.startswith(os.path.abspath(base) + os.sep), joined_abs)
check("点文件被拒", V.is_static_denied(os.path.join(base, ".secret")))

# ---------- 4) 私网 IP 判定 ----------
for priv in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.5.4", "::1", "fc00::1"):
    check("私网/回环判定 True: %s" % priv, V.is_private_ip(priv))
for pub in ("8.8.8.8", "1.2.3.4", "2606:4700::1"):
    check("公网判定 False: %s" % pub, not V.is_private_ip(pub))
check("非法 IP 不抛异常", V.is_private_ip("not-an-ip") is False)

# ---------- 5) multipart 解析（手写最小实现，兼容无 cgi 的 3.13+） ----------
boundary = b"BOUND"
body = (b"--BOUND\r\nContent-Disposition: form-data; name=\"f\"; filename=\"x.png\"\r\n\r\nBINARYDATA\r\n"
        b"--BOUND\r\nContent-Disposition: form-data; name=\"root\"\r\n\r\nmyroot\r\n"
        b"--BOUND--\r\n")
files, fields = V.parse_multipart(body, boundary)
check("multipart 解析出文件", files and files[0][0] == "f" and files[0][2] == b"BINARYDATA", files)
check("multipart 解析出字段", fields.get("root") == "myroot", fields)

# ---------- 6) 历史版本键无碰撞（旧方案 a/b__c.md 与 a__b/c.md 同键） ----------
k1 = V._version_key("a/b/c.md")
k2 = V._version_key("a__b/c.md")
check("版本键对不同路径不碰撞", k1 != k2, (k1, k2))
check("版本键含可读前缀", "c" in k1, k1)

# ---------- 7) 共享路径收集（无环境变量 → 空） ----------
os.environ.pop("TRIM_DATA_SHARE_PATHS", None)
check("无共享路径环境变量时返回空", V.collect_share_paths() == [])

print("\nRESULT(security): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
