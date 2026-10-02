#!/usr/bin/env python3
# -*- coding: utf-8 -*-
SRC = r"C:\Users\13379\WorkBuddy\2026-10-01-14-38-51\vditor-nas\server.py"
with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit("ASSERT FAIL: expected %d of:\n%r\nfound %d" % (count, old[:90], n))
    s = s.replace(old, new, count)

# a) 首次保存时不要为“空文件”快照出一个空历史版本
rep(
'''                    if prev != content.encode("utf-8"):
                        save_file_version(root["path"], rel_stored, prev)''',
'''                    if prev and prev != content.encode("utf-8"):
                        save_file_version(root["path"], rel_stored, prev)''')

# b) 删除文档后，若 .vditor_versions 已空则一并清理
rep(
'''            if os.path.isfile(fp):
                os.remove(fp)
            vdir = _version_dir(root["path"], rel)
            if os.path.isdir(vdir):
                shutil.rmtree(vdir)
            self._send_json({"ok": True})''',
'''            if os.path.isfile(fp):
                os.remove(fp)
            vdir = _version_dir(root["path"], rel)
            if os.path.isdir(vdir):
                shutil.rmtree(vdir)
            # 若 .vditor_versions 目录已空，一并清理，避免残留空目录
            parent = os.path.dirname(vdir)
            if os.path.isdir(parent) and not os.listdir(parent):
                try:
                    os.rmdir(parent)
                except OSError:
                    pass
            self._send_json({"ok": True})''')

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

import py_compile
py_compile.compile(SRC, doraise=True)
print("OK server.py patched (v4.0.7 extras) & compiles.")
