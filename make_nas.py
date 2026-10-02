#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 vditor-fpk 衍生通用 Linux 部署版 vditor-nas/。

设计原则：**唯一源是 `vditor-fpk/app`**（所有开发与回归测试都在这里进行），
通用版只是「共享文件 + NAS 专属模板」的组装产物，不再手工维护——
从根本上消除「两份 server.py 必须逐字节一致」的漂移隐患。

- 共享文件（每次从源整份覆盖）：`server.py`、`mobile_api.py`、`vd_util.py`、`index.html`、`vditor/`
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

SHARED_FILES = ["server.py", "mobile_api.py", "vd_util.py", "index.html"]
SHARED_DIRS = ["vditor"]


def check_imports_covered():
    """守护：源目录里新增的 .py 模块不能漏进 SHARED_FILES。

    背景：1.2.0 新增 `mobile_api.py` 时忘了加进 SHARED_FILES，
    生成的 nas 版 `import mobile_api` 直接 ModuleNotFoundError 起不来，
    而第4 步的 filecmp 自检**查不出来**（它只比对「已经在列表里」的文件，
    对「本该在却没在」的文件是盲的）。

    做法：扫源码里 `import <本地模块>`，凡解析到同目录 .py 的都必须已登记。
    """
    import re
    local = set()
    for f in os.listdir(SRC_APP):
        if f.endswith(".py"):
            local.add(f[:-3])
    if not local:
        return []
    # server.py 可能用 sys.path.insert 自举，这里只取纯 import 形式
    text = ""
    for f in os.listdir(SRC_APP):
        if f.endswith(".py"):
            with open(os.path.join(SRC_APP, f), "r", encoding="utf-8") as fh:
                text += fh.read()
    imported = set()
    for m in re.finditer(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.M):
        if m.group(1) in local:
            imported.add(m.group(1))
    for m in re.finditer(r"^\s*from\s+([A-Za-z_][A-Za-z0-9_]*)\s+import", text, re.M):
        if m.group(1) in local:
            imported.add(m.group(1))
    missing = sorted(imported - set(n[:-3] for n in SHARED_FILES))
    return missing


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
    missing = check_imports_covered()
    if missing:
        print("  FAIL  以下模块被 import 但未登记进 SHARED_FILES：%s"
              % ", ".join(missing))
        print("        （生成的 nas 版会 ModuleNotFoundError 起不来，请补进 SHARED_FILES）")
        bad += 1
    print("\n%s  ->  %s\n%s" % (SRC_APP, OUT, "OK 已生成" if not bad else "有 %d 项校验失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
