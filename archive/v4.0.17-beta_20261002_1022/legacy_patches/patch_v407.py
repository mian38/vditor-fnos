#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io as _io, sys, re

SRC = r"C:\Users\13379\WorkBuddy\2026-10-01-14-38-51\vditor-nas\server.py"
with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit("ASSERT FAIL: expected %d occurrence(s) of:\n%r\nfound %d" % (count, old[:80], n))
    s = s.replace(old, new, count)

# 1) version bump
rep('APP_VERSION = "4.0.6"', 'APP_VERSION = "4.0.7"')

# 2) import shutil
rep("import mimetypes\nimport ipaddress",
    "import mimetypes\nimport shutil\nimport ipaddress")

# 3) DEFAULT_SETTINGS: add page_title + favicon
rep(
'''    "max_versions": 50,        # 每个文件保留的最大历史版本数
}''',
'''    "max_versions": 50,        # 每个文件保留的最大历史版本数
    "page_title": "Vditor 在线 Markdown 编辑器",  # 网页标题
    "favicon": "",             # 网页图标：空=默认；local=本应用上传图标；或填远程 URL
}''')

# 4) _apply_settings: page_title + favicon
rep(
'''                errs.append("max_versions 必须为数字")
        return changed, errs''',
'''                errs.append("max_versions 必须为数字")
        if "page_title" in data:
            v = (data["page_title"] or "").strip()
            if len(v) > 60:
                v = v[:60]
            if SETTINGS.get("page_title") != v:
                SETTINGS["page_title"] = v; changed = True
        if "favicon" in data:
            v = (data["favicon"] or "").strip()
            if len(v) > 2000:
                v = v[:2000]
            if SETTINGS.get("favicon") != v:
                SETTINGS["favicon"] = v; changed = True
        return changed, errs''')

# 5) settings export keys
rep(
'        keys = ("trust_proxy", "secure_cookie", "versioning", "max_versions", "autosave_interval")',
'        keys = ("trust_proxy", "secure_cookie", "versioning", "max_versions", "autosave_interval", "page_title", "favicon")')

# 6) save returns abspath
rep(
'            self._send_json({"ok": True, "root": root_id, "path": rel_stored, "mtime": int(st.st_mtime)})',
'            self._send_json({"ok": True, "root": root_id, "path": rel_stored,\n                             "abspath": os.path.abspath(fp), "mtime": int(st.st_mtime)})')

# 7) insert new methods before _api_backup
NEW_METHODS = '''
    def _api_doc_info(self, qs):
        root_id = (qs.get("root") or [""])[0]
        rel = (qs.get("path") or [""])[0]
        root = self._find_root(root_id)
        if not root:
            self._send_json({"error": "invalid root"}, 400); return
        rel = self._safe_doc_rel(root, rel)
        if not rel:
            self._send_json({"error": "invalid path"}, 400); return
        fp = safe_join(root["path"], rel)
        if not fp or not os.path.isfile(fp):
            self._send_json({"exists": False, "path": rel, "abspath": (fp or "")}); return
        st = os.stat(fp)
        vers = list_file_versions(root["path"], rel)
        self._send_json({"exists": True, "path": rel, "abspath": fp,
                         "size": st.st_size, "mtime": int(st.st_mtime),
                         "versions": vers, "version_count": len(vers)})

    def _api_doc_delete(self):
        try:
            data = self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": "bad json"}, 400); return
        root_id = data.get("root", "")
        rel = data.get("path", "")
        root = self._find_root(root_id)
        if not root:
            self._send_json({"ok": False, "error": "invalid root"}, 400); return
        rel = self._safe_doc_rel(root, rel)
        if not rel:
            self._send_json({"ok": False, "error": "invalid path"}, 400); return
        fp = safe_join(root["path"], rel)
        if not fp:
            self._send_json({"ok": False, "error": "invalid path"}, 400); return
        try:
            if os.path.isfile(fp):
                os.remove(fp)
            vdir = _version_dir(root["path"], rel)
            if os.path.isdir(vdir):
                shutil.rmtree(vdir)
            self._send_json({"ok": True})
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    def _send_favicon(self):
        import glob
        matches = sorted(glob.glob(os.path.join(CONFIG_DIR, "favicon.*")))
        if matches:
            fp = matches[0]
            with open(fp, "rb") as f:
                data = f.read()
            self._send(200, data, {"Content-Type": guess_mime(fp)})
        else:
            self._send(204, b"")

    def _handle_favicon_upload(self):
        length = int(self.headers.get("Content-Length", 0))
        ctype = self.headers.get("Content-Type", "")
        m = re.search(r"boundary=([^;]+)", ctype)
        if not m:
            self._send_json({"ok": False, "error": "bad request"}, 400); return
        boundary = m.group(1).strip().strip('"').encode("utf-8")
        try:
            files = parse_multipart(self.rfile.read(length), boundary)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 400); return
        if not files:
            self._send_json({"ok": False, "error": "未收到文件"}, 400); return
        _field, fname, content = files[0]
        ext = os.path.splitext(fname)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".ico", ".gif", ".svg", ".webp"):
            ext = ".png"
        out = os.path.join(CONFIG_DIR, "favicon" + ext)
        try:
            with open(out, "wb") as f:
                f.write(content)
            for old in os.listdir(CONFIG_DIR):
                if old.startswith("favicon.") and old != os.path.basename(out):
                    try: os.remove(os.path.join(CONFIG_DIR, old))
                    except OSError: pass
            self._send_json({"ok": True, "favicon": "local"})
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

'''
rep("    def _api_backup(self):\n        import io as _io", NEW_METHODS + "    def _api_backup(self):\n        import io as _io")

# 8) do_GET: doc info + favicon route
rep(
'''        if path == "/":
            path = "/index.html"''',
'''        if path == "/api/doc/info":
            if not self._require_auth(): return
            self._api_doc_info(qs)
            return
        if path == "/favicon.ico":
            self._send_favicon()
            return

        if path == "/":
            path = "/index.html"''')

# 9) do_POST: doc delete + favicon upload route
rep(
'''        self._send_json({"msg": "not found", "code": 404, "data": {}}, 404)''',
'''        if p == "/api/doc/delete":
            self._api_doc_delete()
            return
        if p == "/api/favicon":
            self._handle_favicon_upload()
            return
        self._send_json({"msg": "not found", "code": 404, "data": {}}, 404)''')

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

# sanity: compile
import py_compile
py_compile.compile(SRC, doraise=True)
print("OK: server.py patched & compiles. APP_VERSION check:")
print("4.0.7" in s, "| doc_info" in s, "| doc_delete" in s, "| favicon" in s, "| abspath" in s)
