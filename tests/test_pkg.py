#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_pkg.py —— 安装包结构校验（不构建，直接校验源码树 + 可选真实 fpk）

校验「打包输入」完整性（manifest / app/server.py / app/index.html / app/vd_util.py /
cmd/* / config/* / wizard/* / LICENSE / ICON.PNG）与版本号一致性；若 releases/ 下存在
已构建的 .fpk，则进一步抽取校验其内外层结构与「包内 manifest 版本 == 源码 manifest」。

替代旧 test_smoke_pkg.py：不再逐资源 200/404（改由 test_core.py 端到端覆盖），
也不依赖已删除的自研 build_fpk.py（改校验官方 fnpack.exe 的产物或源码树直接校验）。

直接运行：python test_pkg.py
"""
import os, sys, io, re, tarfile, glob

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(BASE, "vditor-fpk")
MF = os.path.join(PKG, "manifest")
SRV = os.path.join(PKG, "app", "server.py")

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


def manifest_version(path):
    with io.open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("version="):
                return ln.strip().split("=", 1)[1].strip()
    return ""


def app_version(path):
    txt = io.open(path, encoding="utf-8").read()
    m = re.search(r'APP_VERSION = "([^"]+)"', txt)
    return m.group(1) if m else ""


print("== 安装包结构测试 ==")
MV = manifest_version(MF)
SV = app_version(SRV)
print("版本 manifest=%s server=%s" % (MV, SV))

# ---------- 1) 源码树（打包输入）完整性 ----------
for need in ("manifest", os.path.join("app", "server.py"),
             os.path.join("app", "index.html"), os.path.join("app", "vd_util.py"),
             "LICENSE", "ICON.PNG"):
    p = os.path.join(PKG, need)
    check("源码树含 %s" % need, os.path.isfile(p), p)
for d in ("cmd", "config", "wizard"):
    dp = os.path.join(PKG, d)
    check("源码树含目录 %s（非空）" % d, os.path.isdir(dp) and bool(os.listdir(dp)), dp)

# ---------- 2) 版本一致性（与 test_version 互补：此处聚焦打包产物） ----------
check("manifest 与 server 版本一致", bool(MV) and MV == SV, (MV, SV))

# ---------- 3) 若已构建 fpk 存在，校验真实产物 ----------
fps = sorted(glob.glob(os.path.join(BASE, "releases", "*.fpk")),
             key=os.path.getmtime, reverse=True)
if not fps:
    print("  (跳过) releases/ 无 .fpk，未做真实产物校验")
else:
    fpk = fps[0]
    print("校验真实产物: %s" % os.path.basename(fpk))
    with tarfile.open(fpk, "r:gz") as t:
        outer = t.getnames()
        app_bytes = t.extractfile("app.tgz").read()
        pk_mf = t.extractfile("manifest").read().decode("utf-8")
    for need in ("manifest", "app.tgz", "LICENSE", "cmd", "config", "wizard", "ICON.PNG"):
        check("外层含 %s" % need, need in outer, need)
    with tarfile.open(None, "r:gz", fileobj=io.BytesIO(app_bytes)) as ti:
        inner = ti.getnames()
    # 内层无 app/ 前缀，按后缀匹配关键文件
    check("内层含 server.py", any(n.endswith("server.py") for n in inner), inner[:5])
    check("内层含 index.html", any(n.endswith("index.html") for n in inner), inner[:5])
    check("内层含 vd_util.py", any(n.endswith("vd_util.py") for n in inner), inner[:5])
    m = re.search(r"version\s*=\s*(\S+)", pk_mf)
    pkver = m.group(1) if m else ""
    check("包内 manifest 版本 == 源码 manifest 版本", pkver == MV,
          "包内=%s 源码=%s（若不一致请重新 fnpack 构建）" % (pkver, MV))

print("\nRESULT(pkg): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
