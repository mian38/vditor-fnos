#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""从 vditor-fpk 衍生通用 Linux 部署版 vditor-nas/。

设计原则：**唯一源是 `vditor-fpk/app`**（所有开发与回归测试都在这里进行），
通用版只是「共享文件 + NAS 专属模板」的组装产物，不再手工维护——
从根本上消除「两份 server.py 必须逐字节一致」的漂移隐患。

- 共享文件（每次从源整份覆盖）：`server.py`、`index.html`、`vditor/`
- NAS 专属模板（`nas-template/`）：`config.env`、`install.sh`、`uninstall.sh`、`README.md`、`LICENSE`

用法：
    python3 make_nas.py                 # 生成到 ./vditor-nas
    python3 make_nas.py <out_dir>       # 生成到指定目录
"""
import os
import shutil
import sys
import filecmp

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_APP = os.path.join(HERE, "vditor-fpk", "app")
TPL = os.path.join(HERE, "nas-template")
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "vditor-nas")

SHARED_FILES = ["server.py", "vd_util.py", "index.html"]
SHARED_DIRS = ["vditor"]


def main():
    if not os.path.isdir(SRC_APP):
        raise SystemExit("缺少源目录：%s" % SRC_APP)
    os.makedirs(OUT, exist_ok=True)

    # 1) 共享文件 / 目录：整份覆盖（源即真理）
    for n in SHARED_FILES:
        src = os.path.join(SRC_APP, n)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT, n))
            print("  copy  %s" % n)
    for d in SHARED_DIRS:
        src = os.path.join(SRC_APP, d)
        dst = os.path.join(OUT, d)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print("  copy  %s/" % d)

    # 2) NAS 专属模板
    if os.path.isdir(TPL):
        for n in sorted(os.listdir(TPL)):
            s = os.path.join(TPL, n)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(OUT, n))
                print("  tpl   %s" % n)

    # 3) 运行期目录 + 清掉可能残留的字节码缓存
    for d in ("docs", "uploads"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    pyc = os.path.join(OUT, "__pycache__")
    if os.path.isdir(pyc):
        shutil.rmtree(pyc, ignore_errors=True)

    # 4) 一致性自检
    bad = 0
    for n in SHARED_FILES:
        a, b = os.path.join(SRC_APP, n), os.path.join(OUT, n)
        if os.path.isfile(a) and not filecmp.cmp(a, b, shallow=False):
            print("  FAIL  %s 与源不一致" % n)
            bad += 1
    print("\n%s  ->  %s\n%s" % (SRC_APP, OUT, "OK 已生成" if not bad else "有 %d 项校验失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
