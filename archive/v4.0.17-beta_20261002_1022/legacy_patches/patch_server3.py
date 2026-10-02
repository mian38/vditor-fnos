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

# 1) 新增：HTTPS 强制要求时禁止 HTTP 登录的判定方法
rep(
'''    def _send_cookie(self, token):''',
'''    def _https_required_error(self):
        """安全策略要求 HTTPS（Secure Cookie）但当前为 HTTP 连接时，返回明确错误；
        返回 None 表示允许登录。局域网私有网段直连 HTTP 仍放行（见 _send_cookie）。"""
        proto = (self.headers.get("X-Forwarded-Proto", "") or "").lower()
        if proto == "https":
            return None
        lan = is_private_ip(client_ip(self))
        if SETTINGS.get("secure_cookie") and not lan:
            return ("当前为 HTTP 连接，但安全策略要求使用 HTTPS（Secure Cookie 无法在 HTTP 下生效）。"
                    "请通过 HTTPS（如反向代理 / 域名）访问本应用后再登录。")
        return None

    def _send_cookie(self, token):''')

# 2) 登录接口：HTTP 且要求 HTTPS 时直接禁止
rep(
'''    def _handle_login(self):
        ip = client_ip(self)
        if is_locked(ip):''',
'''    def _handle_login(self):
        ip = client_ip(self)
        err = self._https_required_error()
        if err:
            record_login_event("login_blocked_http", ip, "")
            self._send_json({"ok": False, "error": err}, 403)
            return
        if is_locked(ip):''')

# 3) 首次设置接口：同样防护
rep(
'''    def _handle_setup(self):
        global PWHASH, NEEDS_SETUP
        ip = client_ip(self)
        # 仅当尚未设置密码时允许首次设置；已设置后该接口不可用（改密需登录后另做）''',
'''    def _handle_setup(self):
        global PWHASH, NEEDS_SETUP
        ip = client_ip(self)
        err = self._https_required_error()
        if err:
            self._send_json({"ok": False, "error": err}, 403)
            return
        # 仅当尚未设置密码时允许首次设置；已设置后该接口不可用（改密需登录后另做）''')

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

import py_compile
py_compile.compile(SRC, doraise=True)
print("OK server.py patched (HTTPS guard) & compiles.")
for tok in ("_https_required_error", "当前为 HTTP 连接", "login_blocked_http"):
    print(tok, "->", tok in s)
