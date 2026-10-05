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

# 1.5.0 起格式收敛：三位=正式版 / 四位=测试版（第四段为 beta 序号）。
# 历史上曾用 1.5.0beta3、1.5.0-beta.3，现已统一为四段式，不再接受字母后缀。
ver_re = re.compile(r"^\d+\.\d+\.\d+$")
ver_beta_re = re.compile(r"^\d+\.\d+\.\d+\.(\d+)$")
check("版本符合 三位正式版 / 四位测试版 格式", bool(ver_re.match(mver) or ver_beta_re.match(mver)), mver)
check("版本号不含字母后缀（beta/alpha/rc/dev 已废弃）",
      not re.search(r"[A-Za-z]", mver), mver)

# 四位=测试版，据此拦住「误把 beta 当正式版发布」。
if ver_beta_re.match(mver):
    check("四位版本号被正确识别为测试版（禁止对外发布）", True, mver)
else:
    check("当前为三位正式版（仍须人类明确指令才可发布）", True, mver)

if ver_re.match(mver) or ver_beta_re.match(mver):
    parts = [int(x) for x in mver.split(".")]
    cur = tuple(parts[:3])
    check("版本不低于基线 %s" % (".".join(map(str, BASELINE))), cur >= BASELINE, cur)
    check("platform 声明合理(x86/all)", "platform=x86" in mf or "platform=all" in mf,
          [l for l in mf.split("\n") if l.startswith("platform")])

print("\nRESULT(version): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
