#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_version.py —— 版本号一致性（动态读取，不写死）

校验 manifest 与 server.py 的 APP_VERSION 一致、符合语义化版本、且不低于历史基线。
替代旧 test_v406/test_v407 中写死的版本断言（升版即假红的根因）。

直接运行：python test_version.py
"""
import os, sys, io, re

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MF = os.path.join(BASE, "vditor-fpk", "manifest")
SRV = os.path.join(BASE, "vditor-fpk", "app", "server.py")
BASELINE = (1, 2, 0)  # 1.2.0 起统一版本线

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


def read(p):
    return io.open(p, encoding="utf-8").read()


print("== 版本号一致性测试 ==")

mf = read(MF)
srv = read(SRV)
mver = ""
for ln in mf.split("\n"):
    if ln.startswith("version="):
        mver = ln.strip().split("=", 1)[1].strip()
        break
sm = re.search(r'APP_VERSION = "([^"]+)"', srv)
sver = sm.group(1) if sm else ""

check("manifest version 可解析", bool(mver), mver)
check("server APP_VERSION 可解析", bool(sver), sver)
check("manifest 与 server 版本一致", mver == sver, (mver, sver))

ver_re = re.compile(r"^\d+\.\d+\.\d+$")
check("版本符合 语义化版本", bool(ver_re.match(mver)), mver)

if ver_re.match(mver):
    cur = tuple(map(int, mver.split(".")))
    check("版本不低于基线 %s" % (".".join(map(str, BASELINE))), cur >= BASELINE, cur)
    check("platform 声明合理(x86/all)", "platform=x86" in mf or "platform=all" in mf,
          [l for l in mf.split("\n") if l.startswith("platform")])

print("\nRESULT(version): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
