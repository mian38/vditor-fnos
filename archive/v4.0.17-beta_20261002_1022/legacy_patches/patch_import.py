#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Make _api_settings_import accept both {settings:{...}} and raw settings object."""
PATH = "vditor-nas/server.py"
with open(PATH, "r", encoding="utf-8") as f:
    s = f.read()

OLD = '''    def _api_settings_import(self):
        try:
            data = self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": "bad json"}, 400)
            return
        changed, errs = self._apply_settings(data)'''

NEW = '''    def _api_settings_import(self):
        try:
            data = self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": "bad json"}, 400)
            return
        # 兼容两种入参：直接传 settings 对象，或 {"settings": {...}}
        if isinstance(data, dict) and isinstance(data.get("settings"), dict):
            data = data["settings"]
        changed, errs = self._apply_settings(data)'''

n = s.count(OLD)
assert n == 1, "occurrences=%d" % n
s = s.replace(OLD, NEW)
with open(PATH, "w", encoding="utf-8") as f:
    f.write(s)
import py_compile
py_compile.compile(PATH, doraise=True)
print("patched import + compiled OK")
