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
    python3 tools/bump_version.py 1.2.0 --dry-run  # 只显示将要做的改动

注意：`manifest` 的 changelog 是**单行**多条目拼接（新版本条目需前置），且有中文冒号，
本脚本不改它——执行后会提示你手动补 `changelog=<新版本>：...`。
"""
import io
import os
import re
import sys

# 脚本位于 tools/ 下，故仓库根为本文件的上一级目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = ROOT  # 保持变量名不变，仅语义为仓库根

# 三位=正式版；四位=测试版（第四段为 beta 序号）。见AGENTS.md §1 / §0.1。
VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$")


def is_beta(ver):
    """该版本号是否为测试版（四段式）。用于拦住「误把 beta 当正式版发布」。"""
    m = VER_RE.match(ver)
    return bool(m and m.group(4) is not None)


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
    # 1.5.0 起格式收敛为「三位正式版/ 四位测试版」，不再接受 beta/alpha/rc 等字母后缀。
    if not VER_RE.match(new):
        raise SystemExit(
            "版本号格式非法：%r\n"
            "  正式版：x.y.z（如 1.5.0）\n"
            "  测试版：x.y.z.N（如 1.5.0.3，第四段为 beta 序号）\n"
            "  不再接受 1.5.0beta3 / 1.5.0-beta.3 / 1.5.0-rc1 等字母后缀形式。" % new)

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
        if is_beta(new):
            print()
            print("⚠️  %s 是**测试版（四位版本号）**。" % new)
            print("   禁止对外发布：不要打 tag、不要建 GitHub Release、不要上传 fpk。")
            print("   正式发布需去掉第四段（如 1.5.0），且必须由人类明确下达「发布 vX.Y.Z」。")
        else:
            print()
            print("ℹ️  %s 是三位正式版，但仍**必须由人类明确下达「发布 vX.Y.Z」**"
                  "才能打 tag / 建 Release / 上传。" % new)
        print("完成后建议：./fnpack.exe build -d vditor-fpk")
        if is_beta(new):
            print("  归档文件名请用：com.mian38.vditor_%s.fpk" % new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
