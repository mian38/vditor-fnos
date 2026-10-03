#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_cli.py —— 生命周期脚本（cmd/*、app/bin/vditor）静态与语法校验

这些 bash 脚本负责 fnOS 安装/升级/卸载/重置密码，属「静默失效」高发区：
语法错误只在真机执行时才暴露。本测试用 `bash -n` 做语法检查 + 关键函数存在性检查，
不实际执行（避免改动系统），覆盖旧 test_*.py 中对脚本的零散断言。

直接运行：python test_cli.py
"""
import os, sys, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "vditor-fpk", "app")
CMD = os.path.join(BASE, "vditor-fpk", "cmd")
BIN = os.path.join(APP, "bin", "vditor")

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra)


def bash_syntax_ok(path):
    if not os.path.isfile(path):
        return False
    try:
        r = subprocess.run(["bash", "-n", path], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


print("== 生命周期脚本测试 ==")

scripts = []
for root, _, names in os.walk(CMD):
    for n in names:
        scripts.append(os.path.join(root, n))
scripts.append(BIN)
scripts = sorted(set(scripts))

for s in scripts:
    name = os.path.relpath(s, BASE)
    check("语法正确: %s" % name, bash_syntax_ok(s))
    txt = read(s)
    check("含 shebang: %s" % name, txt.startswith("#!/bin/bash") or txt.startswith("#!/usr/bin/env bash"),
          txt[:20].replace("\n", " "))
    check("启用 nounset(set -u): %s" % name, "set -u" in txt)

# 关键能力存在性
main = read(os.path.join(CMD, "main"))
check("main 含 start/stop/status", all(k in main for k in ("start)", "stop)", "status)")))
check("main 缺失 python3 时明确报错", "未找到 python3" in main or "请在飞牛" in main)

reset = read(BIN)
check("vditor 终端工具含 reset-password", "reset-password" in reset)
check("vditor 终端工具含 help", "help" in reset)

install_init = read(os.path.join(CMD, "install_init"))
check("install_init 检查 python3", "python3" in install_init)

print("\nRESULT(cli): passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
