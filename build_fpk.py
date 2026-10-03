#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""
可复现地构建飞牛 FnOS 安装包 com.mian38.vditor.fpk。

.fpk 实际是一个 gzip 压缩的 tar，内部结构：
  外层 tar.gz 包含：app.tgz, LICENSE, cmd/, config/, wizard/, manifest, ICON.PNG, ICON_256.PNG
  其中 app.tgz 是 app/ 目录内容（index.html, server.py, ui/, vditor/）的 tar.gz

用法：
  python3 build_fpk.py                 # 输出到 vditor-fpk/com.mian38.vditor.fpk
  python3 build_fpk.py <out.fpk>       # 指定输出路径
"""
import os
import sys
import io
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "vditor-fpk")


def pkg_version():
    """从 manifest 读取版本号，用于输出文件名末尾追加版本，便于回滚。"""
    mp = os.path.join(PKG, "manifest")
    if os.path.isfile(mp):
        with open(mp, encoding="utf-8") as f:
            for line in f:
                if line.startswith("version="):
                    return line.strip().split("=", 1)[1].strip() or "0.0.0"
    return "0.0.0"


OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "releases", "com.mian38.vditor_%s.fpk" % pkg_version())

EXCLUDE = {"app", ".git", "__pycache__", "build_fpk.py"}


def make_app_tgz(app_dir):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        for root, dirs, names in os.walk(app_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for n in sorted(names):
                fp = os.path.join(root, n)
                if n == "__pycache__":
                    continue
                arc = os.path.relpath(fp, app_dir).replace(os.sep, "/")
                tar.add(fp, arcname=arc)
    return buf.getvalue()


def build():
    app_dir = os.path.join(PKG, "app")
    if not os.path.isdir(app_dir):
        raise SystemExit("缺少 app/ 目录：%s" % app_dir)
    app_tgz = make_app_tgz(app_dir)

    # 外层 tar.gz
    with tarfile.open(OUT, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        # 1) app.tgz 作为整体加入
        ti = tarfile.TarInfo("app.tgz")
        ti.size = len(app_tgz)
        ti.mode = 0o644
        tar.addfile(ti, io.BytesIO(app_tgz))
        # 2) 其余顶层条目（排除 app 与无关项）
        for name in sorted(os.listdir(PKG)):
            if name in EXCLUDE:
                continue
            fp = os.path.join(PKG, name)
            arc = name
            tar.add(fp, arcname=arc)
    print("已生成：%s  (%d 字节)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    build()
