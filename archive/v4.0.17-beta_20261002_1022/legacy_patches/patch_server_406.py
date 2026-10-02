#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch vditor-nas/server.py for v4.0.6: items 4 + 5 + version bump."""
import io, sys

PATH = "vditor-nas/server.py"
with open(PATH, "r", encoding="utf-8") as f:
    s = f.read()

def repl(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, "expected %d occurrence(s) of block, found %d" % (count, n)
    s = s.replace(old, new)

# 1) version bump
repl('APP_VERSION = "4.0.5"', 'APP_VERSION = "4.0.6"')

# 2) _api_list_files: prune .vditor_versions (item 4)
repl(
'''            if os.path.isdir(base):
                for root, dirs, names in os.walk(base):
                    for n in names:
                        if n.lower().endswith(".md"):''',
'''            if os.path.isdir(base):
                for root, dirs, names in os.walk(base):
                    # 排除历史版本目录，避免“我的文档”误显示历史版本文件
                    if VERSIONS_DIRNAME in dirs:
                        dirs.remove(VERSIONS_DIRNAME)
                    for n in names:
                        if n.lower().endswith(".md"):''')

# 3) _api_backup: prune .vditor_versions too (consistency)
repl(
'''                for root2, dirs, names in os.walk(base):
                    for n in names:
                        if not n.lower().endswith(".md"):
                            continue''',
'''                for root2, dirs, names in os.walk(base):
                    # 备份时同样排除历史版本目录
                    if VERSIONS_DIRNAME in dirs:
                        dirs.remove(VERSIONS_DIRNAME)
                    for n in names:
                        if not n.lower().endswith(".md"):
                            continue''')

# 4) refactor settings update -> _apply_settings + export + import (item 5)
OLD_SETTINGS = '''    def _api_settings_update(self):
        try:
            data = self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": "bad json"}, 400)
            return
        changed = False
        for k in ("trust_proxy", "secure_cookie", "versioning"):
            if k in data and isinstance(data[k], bool):
                SETTINGS[k] = data[k]; changed = True
        if "autosave_interval" in data:
            try:
                v = max(10, int(float(data["autosave_interval"])))
                SETTINGS["autosave_interval"] = v; changed = True
            except Exception:
                pass
        if "max_versions" in data:
            try:
                v = max(1, int(float(data["max_versions"])))
                SETTINGS["max_versions"] = v; changed = True
            except Exception:
                pass
        if changed:
            save_settings()
        self._send_json({"ok": True, "settings": dict(SETTINGS)})'''

NEW_SETTINGS = '''    def _apply_settings(self, data):
        """统一校验并应用设置字段，返回 (changed, errors)。供 WebUI 保存与配置导入复用。"""
        changed = False
        errs = []
        if not isinstance(data, dict):
            return changed, ["配置格式无效"]
        for k in ("trust_proxy", "secure_cookie", "versioning"):
            if k in data:
                if isinstance(data[k], bool):
                    if SETTINGS.get(k) != data[k]:
                        SETTINGS[k] = data[k]; changed = True
                else:
                    errs.append("%s 必须为布尔值" % k)
        if "autosave_interval" in data:
            try:
                v = max(10, int(float(data["autosave_interval"])))
                if SETTINGS.get("autosave_interval") != v:
                    SETTINGS["autosave_interval"] = v; changed = True
            except Exception:
                errs.append("autosave_interval 必须为数字")
        if "max_versions" in data:
            try:
                v = max(1, int(float(data["max_versions"])))
                if SETTINGS.get("max_versions") != v:
                    SETTINGS["max_versions"] = v; changed = True
            except Exception:
                errs.append("max_versions 必须为数字")
        return changed, errs

    def _api_settings_update(self):
        try:
            data = self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": "bad json"}, 400)
            return
        changed, errs = self._apply_settings(data)
        if errs:
            self._send_json({"ok": False, "error": "; ".join(errs)})
            return
        if changed:
            save_settings()
        self._send_json({"ok": True, "settings": dict(SETTINGS)})

    def _api_settings_export(self):
        keys = ("trust_proxy", "secure_cookie", "versioning", "max_versions", "autosave_interval")
        payload = {
            "app": "vditor-nas",
            "version": APP_VERSION,
            "settings": {k: SETTINGS.get(k) for k in keys},
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(200, body, {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Disposition": "attachment; filename=vditor-settings.json",
        })

    def _api_settings_import(self):
        try:
            data = self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": "bad json"}, 400)
            return
        changed, errs = self._apply_settings(data)
        if errs:
            self._send_json({"ok": False, "error": "; ".join(errs)})
            return
        if changed:
            save_settings()
        self._send_json({"ok": True, "imported": changed, "settings": dict(SETTINGS)})'''
repl(OLD_SETTINGS, NEW_SETTINGS)

# 5) do_GET route for export
repl(
'''        if path == "/api/settings":
            if not self._require_auth(): return
            self._send_json(self._api_settings_get())
            return''',
'''        if path == "/api/settings":
            if not self._require_auth(): return
            self._send_json(self._api_settings_get())
            return
        if path == "/api/settings/export":
            if not self._require_auth(): return
            self._api_settings_export()
            return''')

# 6) do_POST route for import
repl(
'''        if p == "/api/settings":
            self._api_settings_update()
            return''',
'''        if p == "/api/settings":
            self._api_settings_update()
            return
        if p == "/api/settings/import":
            self._api_settings_import()
            return''')

with open(PATH, "w", encoding="utf-8") as f:
    f.write(s)

# sanity: compile
import py_compile
py_compile.compile(PATH, doraise=True)
print("patched + compiled OK")
