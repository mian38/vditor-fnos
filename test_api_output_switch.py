#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「API 接口对外输出数据」开关的专项测试。

覆盖用户要求的三条一致性：
1. **默认关闭**：全新配置下数据接口不输出数据
2. **前端配置项 ↔ 后端校验**：经 /api/settings 打开后，同一进程内立即生效
3. **配置持久化**：写入 settings.json，重启后仍保持开启

同时校验「不受控接口」（health / auth/*）在关闭态下依旧可用——
否则调试者连服务是否在线都无法确认，开关就失去了调试价值。
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(APP_DIR, "vditor-fpk", "app")
PORT = 8944
PASSWORD = "switch-pass-2026"

PASS = 0
FAIL = 0
FAILED_ITEMS = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS %-8s %s" % (name, ""))
    else:
        FAIL += 1
        FAILED_ITEMS.append("%s %s" % (name, detail))
        print("  FAIL %-8s %s  %s" % (name, detail, ""))


def wait_port(port, timeout=20):
    for _ in range(int(timeout / 0.15)):
        try:
            s = socket.create_connection(("127.0.0.1", port), 0.3)
            s.close()
            return True
        except OSError:
            time.sleep(0.15)
    return False


class Client:
    def __init__(self):
        self.base = "http://127.0.0.1:%d" % PORT
        self.token = ""
        self.cookie = ""

    def _req(self, path, data=None, method=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.base + path, data=body, method=method)
        if body:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()
                setc = r.headers.get("Set-Cookie")
                if setc:
                    self.cookie = setc.split(";")[0]
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"_raw": raw[:200].decode("utf-8", "replace")}


def start(cfg, docs, api_output_env=None):
    """启动服务端。api_output_env 为 None 表示不设环境变量（走默认）。"""
    env = dict(os.environ)
    env.update({
        "VDITOR_CONFIG": cfg,
        "VDITOR_DOC_DIR": docs,
        "VDITOR_DOC_NAME": "我的文档",
        "VDITOR_PORT": str(PORT),
        "VDITOR_PASSWORD": PASSWORD,
        "VDITOR_SECURE_COOKIE": "0",
        "VDITOR_TRUST_PROXY": "0",
        "PYTHONIOENCODING": "utf-8",
    })
    if api_output_env is not None:
        env["VDITOR_API_OUTPUT"] = api_output_env
    else:
        env.pop("VDITOR_API_OUTPUT", None)
    p = subprocess.Popen([sys.executable, "-u", "server.py"], cwd=APP, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if not wait_port(PORT):
        out = p.stdout.read() if p.stdout else ""
        print("SERVER FAILED TO START:\n" + out[-2000:])
        sys.exit(1)
    return p


def stop(p):
    p.terminate()
    try:
        p.wait(timeout=6)
    except Exception:
        p.kill()
    time.sleep(0.5)


def purge(path):
    """Windows 上刚 terminate 的进程句柄释放有延迟，需重试。"""
    for _ in range(6):
        if not os.path.exists(path):
            return True
        try:
            shutil.rmtree(path)
        except OSError:
            time.sleep(0.3)
    return not os.path.exists(path)


def web_login(c):
    """/api/settings 需 Web Cookie 会话才能读，先登录。"""
    return c._req("/api/login", {"password": PASSWORD}, method="POST")


def main():
    tmp = tempfile.mkdtemp(prefix="vtswitch_")
    cfg = os.path.join(tmp, "cfg")
    docs = os.path.join(tmp, "docs")
    os.makedirs(cfg, exist_ok=True)
    os.makedirs(docs, exist_ok=True)
    ok_cleanup = False
    try:
        # ============ 阶段 1：默认关闭 ============
        print("\n== 1. 默认状态（不设 VDITOR_API_OUTPUT）==")
        p = start(cfg, docs)
        c = Client()
        web_login(c)
        code, r = c._req("/api/settings")
        check("设置里带 api_output 字段", "api_output" in (r.get("settings") or {}),
              str(list((r.get("settings") or {}).keys()))[:160])
        check("默认值为 False",
              (r.get("settings") or {}).get("api_output") is False,
              repr((r.get("settings") or {}).get("api_output")))

        code, r = c._req("/api/m/health")
        check("关闭态：health 仍可用（探活不受影响）",
              code == 200 and r.get("ok") and
              (r.get("data") or {}).get("status") == "ok", str(r)[:160])

        # 移动端登录（auth 不受开关影响）
        code, r = c._req("/api/m/auth/login", {"password": PASSWORD}, method="POST")
        check("关闭态：仍可登录（auth 不受影响）", code == 200 and r.get("ok"), str(r)[:160])
        c.token = (r.get("data") or {}).get("token", "")
        check("登录拿到 token", bool(c.token), str(r)[:160])

        # 数据接口应被拦截
        for name, path, method, body in [
            ("roots", "/api/m/roots", None, None),
            ("files", "/api/m/files?root=x", None, None),
            ("file", "/api/m/file?root=x&path=y", None, None),
            ("versions", "/api/m/file/versions?root=x&path=y", None, None),
            ("settings/upload", "/api/m/settings/upload", None, None),
            ("upload", "/api/m/upload", "POST", {}),
        ]:
            code, r = c._req(path, body, method)
            check("关闭态：%s 不输出数据" % name,
                  r.get("ok") is False and r.get("error") == "API_OUTPUT_DISABLED",
                  "code=%s err=%s" % (code, r.get("error")))

        # 未登录时不得泄露开关状态（应先回 INVALID_TOKEN）
        saved = c.token
        c.token = ""
        code, r = c._req("/api/m/roots")
        check("关闭态：未登录访问数据接口回 INVALID_TOKEN（不泄露开关）",
              r.get("error") == "INVALID_TOKEN", str(r)[:160])
        c.token = saved
        stop(p)

        # ============ 阶段 2：经设置页开启 → 立即生效 ============
        print("\n== 2. 开启开关（走 /api/settings，与前端同一条路径）==")
        p = start(cfg, docs)
        c = Client()
        # 需 Web Cookie 会话才能改设置
        code, r = c._req("/api/login", {"password": PASSWORD}, method="POST")
        check("Web 端登录", code == 200 and r.get("ok") is not False, str(r)[:160])
        code, r = c._req("/api/settings", {"api_output": True}, method="POST")
        check("保存 api_output=true 成功", code == 200 and r.get("ok") is True, str(r)[:160])
        check("响应回显 api_output=true",
              (r.get("settings") or {}).get("api_output") is True,
              repr((r.get("settings") or {}).get("api_output")))

        # 同一进程内立即生效（无需重启）
        code, r = c._req("/api/m/auth/login", {"password": PASSWORD}, method="POST")
        c.token = (r.get("data") or {}).get("token", "")
        code, r = c._req("/api/m/roots")
        check("开启后同一进程内立即生效：roots 返回数据",
              code == 200 and r.get("ok") and isinstance((r.get("data") or {}).get("roots"), list),
              str(r)[:200])

        # 布尔校验：非布尔值应被拒（保证前端不会写入脏值）
        code, r = c._req("/api/settings", {"api_output": "yes"}, method="POST")
        check("非布尔值被拒（前端传字符串不会污染配置）",
              code == 200 and r.get("ok") is False and "布尔" in (r.get("error") or ""),
              str(r)[:200])
        code, r = c._req("/api/settings")
        check("被拒后配置未变（仍为 true）",
              (r.get("settings") or {}).get("api_output") is True,
              repr((r.get("settings") or {}).get("api_output")))
        stop(p)

        # ============ 阶段 3：持久化（重启后仍开启）============
        print("\n== 3. 持久化：重启后仍保持开启 ==")
        p = start(cfg, docs)        # 不设环境变量，纯靠 settings.json
        c = Client()
        web_login(c)
        code, r = c._req("/api/settings")
        check("重启后 api_output 仍为 true（已持久化）",
              (r.get("settings") or {}).get("api_output") is True,
              repr((r.get("settings") or {}).get("api_output")))
        code, r = c._req("/api/m/auth/login", {"password": PASSWORD}, method="POST")
        c.token = (r.get("data") or {}).get("token", "")
        code, r = c._req("/api/m/roots")
        check("重启后数据接口可用", code == 200 and r.get("ok"), str(r)[:160])

        # 关回去，验证可恢复
        code, r = c._req("/api/login", {"password": PASSWORD}, method="POST")
        code, r = c._req("/api/settings", {"api_output": False}, method="POST")
        check("可关闭", code == 200 and r.get("ok") is True, str(r)[:160])
        code, r = c._req("/api/m/roots")
        check("关闭后数据接口重新被拦截",
              r.get("error") == "API_OUTPUT_DISABLED", str(r)[:160])
        stop(p)

        # ============ 阶段 4：settings.json 落盘内容 ============
        print("\n== 4. 落盘内容 ==")
        sf = os.path.join(cfg, "settings.json")
        check("settings.json 存在", os.path.isfile(sf), sf)
        with open(sf, "r", encoding="utf-8") as f:
            disk = json.load(f)
        check("落盘含 api_output 键", "api_output" in disk, str(list(disk.keys()))[:160])
        check("落盘值为 false（最后一步关掉了）", disk.get("api_output") is False,
              repr(disk.get("api_output")))

        # ============ 阶段 5：环境变量可覆盖默认（调试便利）============
        print("\n== 5. 环境变量覆盖默认 ==")
        cfg2 = os.path.join(tmp, "cfg2")
        os.makedirs(cfg2, exist_ok=True)
        p = start(cfg2, docs, api_output_env="1")
        c = Client()
        web_login(c)
        code, r = c._req("/api/settings")
        check("VDITOR_API_OUTPUT=1 时默认开启",
              (r.get("settings") or {}).get("api_output") is True,
              repr((r.get("settings") or {}).get("api_output")))
        stop(p)
        ok_cleanup = True
    finally:
        stop(p) if "p" in dir() else None
        if purge(tmp):
            print("\n临时目录已清理")
        else:
            print("\n!! 临时目录清理失败: %s" % tmp)

    print("\n" + "=" * 60)
    print("RESULT(api output switch): passed=%d failed=%d" % (PASS, FAIL))
    if FAILED_ITEMS:
        print("失败项：")
        for it in FAILED_ITEMS:
            print("  - " + it)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
