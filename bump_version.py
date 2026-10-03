#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""版本号一键同步：把新版本号写入所有需要同步的位置，避免漏改。

同步位置（仅两处源码；测试已改为动态读取版本，无需同步）：
  - vditor-fpk/manifest            : version=<旧>            → version=<新>
  - vditor-fpk/app/server.py       : APP_VERSION = "<旧>"    → "<新>"

用法：
    python3 bump_version.py 1.2.0            # 执行
    python3 bump_version.py 1.2.0 --dry-run  # 只显示将要做的改动

注意：`manifest` 的 changelog 是**单行**多条目拼接（新版本条目需前置），且有中文冒号，
本脚本不改它——执行后会提示你手动补 `changelog=<新版本>：...`。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8", newline="").write(s)


def sub_once(path, old, new, dry):
    """精确替换且断言只命中一次（已是新值则跳过）。"""
    if not os.path.isfile(path):
        print("  SKIP  不存在：%s" % os.path.relpath(path, HERE))
        return True
    s = read(path)
    if new != old and new in s and old not in s:
        print("  SKIP  已是目标值：%s" % os.path.relpath(path, HERE))
        return True
    n = s.count(old)
    if n != 1:
        print("  FAIL  %s 中待替换串出现 %d 次（应为 1）：%r" % (os.path.relpath(path, HERE), n, old))
        return False
    if not dry:
        write(path, s.replace(old, new, 1))
    print("  %s  %s" % ("DRY  " if dry else "OK   ", os.path.relpath(path, HERE)))
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    new = args[0].strip()
    if not new:
        raise SystemExit("新版本号不能为空")

    # 从 manifest 读取当前版本
    mf = os.path.join(HERE, "vditor-fpk", "manifest")
    old = ""
    for line in read(mf).split("\n"):
        if line.startswith("version="):
            old = line.strip().split("=", 1)[1].strip()
            break
    if not old:
        raise SystemExit("未能从 manifest 读取当前版本")
    if old == new:
        raise SystemExit("新版本号与当前一致（%s），无需修改" % old)

    print("版本：%s → %s%s\n" % (old, new, "（dry-run）" if dry else ""))
    ok = True
    ok &= sub_once(mf, "version=%s" % old, "version=%s" % new, dry)
    for p in ("vditor-fpk/app/server.py",):
        ok &= sub_once(os.path.join(HERE, p), 'APP_VERSION = "%s"' % old, 'APP_VERSION = "%s"' % new, dry)

    print()
    if not ok:
        raise SystemExit("有替换失败项，未全部完成")
    if not dry:
        print("请手动补 manifest 的 changelog（单行、新条目前置）：")
        print("  changelog=%s：<本次更新说明>%s：..." % (new, old))
        print("完成后建议：./fnpack.exe build -d vditor-fpk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
