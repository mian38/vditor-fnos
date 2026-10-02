#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vditor NAS 轻量服务器（安全增强版 · 多分区）
- 静态托管当前目录（index.html + vditor 前端资源，/vditor 公开）
- 文档分区：每个指定文件夹独立为一个“分区(root)”，分别列出其下 .md 文件
  * 来源优先级：VDITOR_DOC_DIRS(name::path 逗号分隔) → TRIM_DATA_SHARE_PATHS(飞牛访问权限)
    → 单目录回退(VDITOR_DOC_DIR / TRIM_PKGVAR/docs / BASE_DIR/docs)
- 访问控制（外网安全）：
  * 密码登录(PBKDF2-HMAC-SHA256)，HttpOnly+SameSite 会话 Cookie
  * 每客户端 IP 暴力破解锁定的登录失败计数 + 失败延迟 + 常量时间比较
  * 会话绑定真实 IP、空闲(30min)/绝对(8h)超时
  * 除登录/首次设置/公开静态资源外，所有 API 与上传文件均需登录
- 端口 / 监听地址 / 文档目录 / 密码 通过环境变量或配置目录配置

用法:
    python3 server.py
环境变量:
    VDITOR_PORT        监听端口 (默认 9000)
    VDITOR_HOST        监听地址 (默认 0.0.0.0)
    VDITOR_DOC_DIRS    多分区定义: 名称::路径,名称::路径 (优先)
    VDITOR_DOC_DIR     单目录回退 (默认 docs)
    VDITOR_DOC_NAME    单目录回退时的分区显示名 (默认 我的文档)
    TRIM_DATA_SHARE_PATHS  飞牛“访问权限”授权的文件夹路径(JSON数组或逗号/换行分隔)
    VDITOR_UPLOAD_DIR  上传文件存放目录
    VDITOR_PASSWORD    明文密码(部署时预设，推荐仅用于自动部署；否则用首次设置页)
    VDITOR_PWHASH      预置 PBKDF2 哈希(salt$iters$hash)，优先级高于 VDITOR_PASSWORD
    VDITOR_CONFIG      配置目录(存放 pwhash 文件)，默认 TRIM_PKGETC 或 BASE_DIR
    VDITOR_TRUST_PROXY 置 1 时信任 X-Forwarded-For 取真实客户端 IP(用于反暴力与绑定)
    VDITOR_TRUST_PROXY_STRICT 置 1 时进一步要求直连来源为私有/回环网段才信任 XFF(防伪造,见 client_ip)
"""

import os
import re
import sys
import json
import time
import uuid
import hmac
import hashlib
import secrets
import shutil
import ipaddress
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote

# 自举：把本文件所在目录放进 sys.path，保证同目录的 vd_util.py 一定可被 import。
# 正常以 `python3 server.py` 启动时解释器会自动加入脚本目录，但被 `python3 -c "import server"`、
# `-m` 或第三方拉起方式启动时不会，届时整站会因 ImportError 起不来。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 无副作用的工具与常量统一取自 vd_util（纯函数，不共享可变状态）。
# 只导入本模块真正用到的名字——多导入会掩盖死代码，也会让人误以为本模块依赖它们。
from vd_util import (
    MAX_BODY_BYTES, MAX_UPLOAD_BYTES, UPLOAD_NAME_RE, VERSIONS_DIRNAME,
    DEFAULT_UPLOAD_DENY, normalize_ext_list, is_denied_upload, split_ext_tokens,
    _FILES_CACHE, _FILES_TTL, _UPLOAD_INDEX, _UPLOAD_INDEX_TTL,
    upload_headers, static_headers, trusted_forwarded_proto,
    invalidate_files_cache, invalidate_upload_index,
    is_private_ip, slugify, collect_share_paths, guess_mime,
    is_static_denied, is_public_static, safe_join,
    parse_multipart, _version_key, _legacy_version_key,
    _folder_note_path, _doc_asset_dir, _in_doc_folder,
)

# 移动端 API（/api/m/）的响应包/错误码/参数校验等纯逻辑，同样独立成模块，
# 避免把与 Web 端无关的响应格式代码混进 Handler。
import mobile_api as M


# 应用版本（与安装包 manifest 保持一致；每次发布同步更新）
APP_VERSION = "1.2.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------- 配置 ----------------
def load_config():
    cfg = {"PORT": "9000", "HOST": "0.0.0.0"}
    env_file = os.path.join(BASE_DIR, "config.env")
    if os.path.isfile(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    port = int(os.environ.get("VDITOR_PORT", cfg.get("PORT", "9000")))
    host = os.environ.get("VDITOR_HOST", cfg.get("HOST", "0.0.0.0"))
    return host, port

HOST, PORT = load_config()

UPLOAD_DIR = os.environ.get("VDITOR_UPLOAD_DIR") or os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

CONFIG_DIR = os.environ.get("VDITOR_CONFIG") or os.environ.get("TRIM_PKGETC") or BASE_DIR
os.makedirs(CONFIG_DIR, exist_ok=True)

# ---------------- 运行时设置（持久化于 settings.json，可由 WebUI 修改）----------------
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
LOGIN_LOG_FILE = os.path.join(CONFIG_DIR, "login_log.json")
EXCLUDED_FILE = os.path.join(CONFIG_DIR, "excluded.json")  # 被隐藏（删除）的分区路径列表
LOG_LOCK = threading.Lock()  # 保护 login_log.json 的并发读写

def _bool_default_true(name):
    """安全相关开关默认开启：除非环境变量显式置为 0/false/no，否则为 True。"""
    v = (os.environ.get(name) or "").strip().lower()
    if v in ("0", "false", "no"):
        return False
    return True
DEFAULT_SETTINGS = {
    "trust_proxy": _bool_default_true("VDITOR_TRUST_PROXY"),  # 信任 X-Forwarded-For 取真实客户端 IP（默认开启）
    "secure_cookie": _bool_default_true("VDITOR_SECURE_COOKIE"),  # 强制 Cookie 带 Secure（全站 HTTPS，默认开启）
    "autosave_interval": 60,   # 自动保存间隔（秒），默认 1 分钟
    "versioning": True,        # 是否启用文件历史版本
    "max_versions": 50,        # 每个文件保留的最大历史版本数
    "page_title": "Vditor 在线 Markdown 编辑器",  # 网页标题
    "favicon": "",             # 网页图标：空=默认；local=本应用上传图标；或填远程 URL
    "clear_on_uninstall": False,  # 卸载时是否清除全部软件数据（密码/设置/历史版本），默认保留便于重装恢复
    "upload_max_mb": 256,      # 单个上传文件大小上限（MB）
    "upload_deny": DEFAULT_UPLOAD_DENY,  # 不允许上传的文件扩展名黑名单（逗号分隔；默认放行其余全部）
    "upload_accept": "",       # 【已废弃·仅降级兼容】1.1.2 的白名单字段，1.1.3 起不再参与校验
    # ------------------------------------------------------------------
    # API 接口对外输出数据（/api/m/* 数据接口）。**默认关闭**。
    # 这是给「后续开发本应用移动版」用的调试开关：开启后移动端数据接口才会真正
    # 返回文档内容；关闭时只回元信息、不给数据（详见 docs/MOBILE_API.md §7）。
    # 仅用于开发调试，日常使用请保持关闭——文档正文属于私密数据。
    # 环境变量 VDITOR_API_OUTPUT=1 可覆盖默认值（便于无人值守调试）；
    # 一旦在设置页保存过，以 settings.json 为准。
    # ------------------------------------------------------------------
    "api_output": (os.environ.get("VDITOR_API_OUTPUT", "").strip().lower() in ("1", "true", "yes")),
}

def load_settings():
    s = dict(DEFAULT_SETTINGS)
    has_deny_key = False      # settings.json 里是否出现过 upload_deny 这个键（区分"没配过"与"配成空"）
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                for k in DEFAULT_SETTINGS:
                    if k in d:
                        s[k] = d[k]
                        if k == "upload_deny":
                            has_deny_key = True
        except Exception:
            pass
    # 类型归一化，避免 WebUI 传入字符串导致逻辑异常
    try:
        s["autosave_interval"] = max(10, int(float(s.get("autosave_interval") or 60)))
    except Exception:
        s["autosave_interval"] = 60
    try:
        s["max_versions"] = max(1, int(float(s.get("max_versions") or 50)))
    except Exception:
        s["max_versions"] = 50
    s["trust_proxy"] = bool(s.get("trust_proxy"))
    s["secure_cookie"] = bool(s.get("secure_cookie"))
    s["versioning"] = bool(s.get("versioning", True))
    s["clear_on_uninstall"] = bool(s.get("clear_on_uninstall"))
    # 【默认关闭】未显式配置时务必为 False——避免"配置项缺失"被当成开启。
    # 用 `is True` 而非 bool() 兜底：即便上层误传字符串 "0"/"false"，也判为关闭。
    s["api_output"] = (s.get("api_output") is True)
    try:
        s["upload_max_mb"] = min(512, max(1, int(float(s.get("upload_max_mb") or 256))))
    except Exception:
        s["upload_max_mb"] = 256
    # 上传黑名单（1.1.3 起唯一校验依据）。
    # 「键是否出现过」而非「值是否为空」来决定用不用默认值——否则用户在设置页把黑名单
    # 全部删掉（值=空串）会被悄悄还原成默认清单，导致"删除条目"这个操作对全量删除无效。
    #   键不存在（≤1.1.2 的老配置 / 全新安装）→ 填默认黑名单；
    #   键存在且非空              → 用配置值；
    #   键存在但为空（用户主动清空）→ 空黑名单，即不限制任何格式。
    # 旧白名单 upload_accept 一并保留但不参与校验（仅供降级到 1.1.2 时仍能还原）。
    _deny = normalize_ext_list(s.get("upload_deny")) if has_deny_key else normalize_ext_list(DEFAULT_UPLOAD_DENY)
    s["upload_deny"] = ",".join(_deny)
    s["upload_accept"] = (s.get("upload_accept") or "").strip()
    return s

SETTINGS = load_settings()

# ---------------- 被隐藏（用户删除）的分区 ----------------
def load_excluded():
    if not os.path.isfile(EXCLUDED_FILE):
        return set()
    try:
        with open(EXCLUDED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {os.path.abspath(str(x)) for x in data if str(x).strip()}
    except Exception:
        pass
    return set()

EXCLUDED_PATHS = load_excluded()

def save_excluded():
    try:
        with open(EXCLUDED_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(EXCLUDED_PATHS), f, ensure_ascii=False, indent=2)
        try:
            os.chmod(EXCLUDED_FILE, 0o600)
        except OSError:
            pass
        return True
    except OSError:
        return False

def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(SETTINGS, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(SETTINGS_FILE, 0o600)
        except OSError:
            pass
        return True
    except OSError:
        return False

# ---------------- 安全常量 ----------------
PBKDF2_ITERS = 200000
IDLE_TIMEOUT = 1800        # 会话空闲超时（秒）30 分钟
ABS_TIMEOUT = 28800        # 会话绝对超时（秒）8 小时
MAX_FAIL = 5               # 锁定前最大失败次数
LOCK_WINDOW = 900          # 失败计数滑动窗口（秒）15 分钟
LOCK_DURATION = 900        # 锁定时长（秒）15 分钟
FAIL_DELAY = 0.15          # 登录失败人为延迟（秒），拖慢爆破

# ---------------- 密码哈希 ----------------
def make_pwhash(pw):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ITERS)
    return "%s$%d$%s$%s" % (
        "pbkdf2_sha256", PBKDF2_ITERS,
        salt.hex(), dk.hex(),
    )

def verify_pwhash(stored, pw):
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iters)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False

def load_pwhash():
    # 优先级：VDITOR_PWHASH > VDITOR_PASSWORD > pwhash 文件
    env_hash = os.environ.get("VDITOR_PWHASH", "").strip()
    if env_hash and "$" in env_hash:
        return env_hash, False  # (hash, needs_setup)
    env_pw = os.environ.get("VDITOR_PASSWORD", "").strip()
    if env_pw:
        return make_pwhash(env_pw), False
    pf = os.path.join(CONFIG_DIR, "pwhash")
    if os.path.isfile(pf):
        try:
            with open(pf, "r", encoding="utf-8") as f:
                h = f.read().strip()
            if h and "$" in h:
                return h, False
        except OSError:
            pass
    return None, True  # 需要首次设置密码

PWHASH, NEEDS_SETUP = load_pwhash()

def save_pwhash(h):
    pf = os.path.join(CONFIG_DIR, "pwhash")
    try:
        with open(pf, "w", encoding="utf-8") as f:
            f.write(h)
        try:
            os.chmod(pf, 0o600)
        except OSError:
            pass
        return True
    except OSError:
        return False

# ---------------- 会话与暴力防护（内存态）----------------
SESSIONS = {}        # token -> {ip, created, last}
FAIL_LOG = {}        # ip -> {fails, first, locked_until}

def client_ip(handler):
    """取真实客户端 IP。

    默认：开启「信任反向代理」后采纳 X-Forwarded-For 第一段（校验为合法 IP），
    以支持经反向代理 / 内网穿透访问时正确识别客户端（登录日志、防爆破计数、会话绑定、局域网判定）。
    注意 XFF 由客户端可伪造，故「信任反向代理」务必只在**确实经过可信代理**时开启。
    若需更强的防伪造（直连公网时他人伪造 XFF 可绕过登录锁定、或伪造私有 IP 绕过 Secure Cookie 要求），
    可设 VDITOR_TRUST_PROXY_STRICT=1：届时仅当**直连来源为私有 / 回环网段**（确为本机 / 局域网代理）才采纳 XFF。
    """
    direct = handler.client_address[0]
    if SETTINGS["trust_proxy"]:
        xff = handler.headers.get("X-Forwarded-For", "")
        if xff:
            first = xff.split(",")[0].strip()
            strict = os.environ.get("VDITOR_TRUST_PROXY_STRICT") == "1"
            if (not strict) or is_private_ip(direct):
                try:
                    ipaddress.ip_address(first)
                    return first
                except ValueError:
                    pass  # XFF 非法，回退直连地址
    return direct

# ---------------- 登录日志（持久化于 CONFIG_DIR/login_log.json）----------------
def record_login_event(kind, ip, detail=""):
    """kind: 'login_ok' / 'login_fail' / 'setup' / 'logout' / 'pw_change'"""
    with LOG_LOCK:
        try:
            entries = []
            if os.path.isfile(LOGIN_LOG_FILE):
                try:
                    with open(LOGIN_LOG_FILE, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                except Exception:
                    entries = []
            if not isinstance(entries, list):
                entries = []
            entries.append({"t": int(time.time()), "kind": kind, "ip": ip, "detail": detail})
            if len(entries) > 500:  # 仅保留最近 500 条
                entries = entries[-500:]
            with open(LOGIN_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False)
        except OSError:
            pass

def load_login_log(limit=200):
    try:
        if not os.path.isfile(LOGIN_LOG_FILE):
            return []
        with open(LOGIN_LOG_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            return []
        return entries[-limit:][::-1]  # 倒序（最新在前）
    except Exception:
        return []

def get_session(handler):
    _sweep_sessions()
    token = None
    c = handler.headers.get("Cookie", "")
    m = re.search(r"vditor_sid=([^;]+)", c or "")
    if m:
        token = m.group(1).strip()
    if not token or token not in SESSIONS:
        return None
    s = SESSIONS[token]
    now = time.time()
    ip = client_ip(handler)
    # IP 绑定 + 超时校验
    if s["ip"] != ip or (now - s["last"]) > IDLE_TIMEOUT or (now - s["created"]) > ABS_TIMEOUT:
        SESSIONS.pop(token, None)
        return None
    s["last"] = now
    return token

def start_session(handler):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {
        "ip": client_ip(handler),
        "created": time.time(),
        "last": time.time(),
    }
    return token

def end_session(handler):
    c = handler.headers.get("Cookie", "")
    m = re.search(r"vditor_sid=([^;]+)", c or "")
    if m:
        SESSIONS.pop(m.group(1).strip(), None)

def _fail_entry(ip):
    """取该 IP 的失败计数条目；已超出滑动窗口则视为全新条目（并顺手清掉旧条目）。
    窗口判定集中在这里，避免 is_locked / record_failure 各写一遍而出现口径不一致。"""
    s = FAIL_LOG.get(ip)
    if s is not None and (time.time() - s.get("first", 0)) > LOCK_WINDOW:
        FAIL_LOG.pop(ip, None)
        return None
    return s

def is_locked(ip):
    s = _fail_entry(ip)
    return bool(s) and s.get("locked_until", 0) > time.time()

def record_failure(ip):
    now = time.time()
    s = _fail_entry(ip)
    if s is None:
        s = {"fails": 0, "first": now, "locked_until": 0}
        FAIL_LOG[ip] = s
    s["fails"] += 1
    if s["fails"] >= MAX_FAIL:
        s["locked_until"] = now + LOCK_DURATION
    return s

def record_success(ip):
    FAIL_LOG.pop(ip, None)

_LAST_SWEEP = [0.0]

def _sweep_sessions():
    """定期清理过期会话与失败计数，避免内存无上限增长（时间门限：5 分钟一次）。
    原本仅在「再次访问同一 token/IP」时才清理，长期运行会持续膨胀。"""
    now = time.time()
    if now - _LAST_SWEEP[0] < 300:
        return
    _LAST_SWEEP[0] = now
    for t in list(SESSIONS.keys()):
        s = SESSIONS.get(t)
        if not s or (now - s.get("last", 0)) > IDLE_TIMEOUT or (now - s.get("created", 0)) > ABS_TIMEOUT:
            SESSIONS.pop(t, None)
    for ip in list(FAIL_LOG.keys()):
        s = FAIL_LOG.get(ip) or {}
        if s.get("locked_until", 0) <= now and (now - s.get("first", 0)) > LOCK_WINDOW:
            FAIL_LOG.pop(ip, None)
    for t in list(MTOKENS.keys()):
        s = MTOKENS.get(t)
        if not s or (now - s.get("last", 0)) > IDLE_TIMEOUT or (now - s.get("created", 0)) > ABS_TIMEOUT:
            MTOKENS.pop(t, None)
    # 兜底硬上限：异常情况（大量不同 IP / 会话）下也不让字典无限膨胀
    if len(SESSIONS) > 5000:
        for t in sorted(SESSIONS, key=lambda k: SESSIONS[k].get("last", 0), reverse=True)[2000:]:
            SESSIONS.pop(t, None)
    if len(MTOKENS) > 2000:
        for t in sorted(MTOKENS, key=lambda k: MTOKENS[k].get("last", 0), reverse=True)[800:]:
            MTOKENS.pop(t, None)
    if len(FAIL_LOG) > 10000:
        for ip in sorted(FAIL_LOG, key=lambda k: FAIL_LOG[k].get("first", 0), reverse=True)[5000:]:
            FAIL_LOG.pop(ip, None)

# ---------------- 移动端 Token 会话（/api/m/，与 Web Cookie 会话物理隔离）----------------
# 单独签发而非复用 Cookie 会话：便于按客户端维度限流与吊销（MOBILE_API.md §6 第 1 项）。
# 超时口径与 Web 端保持一致（空闲 30 分钟 / 绝对 8 小时）。
MTOKENS = {}       # token -> {ip, created, last, agent}


def get_mtoken(handler):
    """从 Authorization: Bearer <token> 取移动端 token；无效/过期返回 None。

    同时刷新 `last`（滑动空闲计时）。不做 IP 绑定之外的额外限制——
    手机端常在蜂窝/Wi-Fi 间切换，绑定 IP 会造成大量误失效。
    """
    _sweep_sessions()
    raw = handler.headers.get("Authorization", "") or ""
    m = re.match(r"^\s*Bearer\s+(\S+)\s*$", raw)
    if not m:
        return None
    token = m.group(1)
    s = MTOKENS.get(token)
    if not s:
        return None
    now = time.time()
    if (now - s["last"]) > IDLE_TIMEOUT or (now - s["created"]) > ABS_TIMEOUT:
        MTOKENS.pop(token, None)
        return None
    s["last"] = now
    return token


def start_mtoken(handler):
    token = secrets.token_urlsafe(32)
    MTOKENS[token] = {
        "ip": client_ip(handler),
        "created": time.time(),
        "last": time.time(),
        "agent": (handler.headers.get("User-Agent", "") or "")[:120],
    }
    return token


def mtoken_left(token):
    """返回该 token 的剩余有效期 (空闲, 绝对)，单位秒；供客户端提前判断何时续期。"""
    s = MTOKENS.get(token) or {}
    if not s:
        return 0, 0
    now = time.time()
    idle = max(0, int(IDLE_TIMEOUT - (now - s["last"])))
    absolute = max(0, int(ABS_TIMEOUT - (now - s["created"])))
    return idle, absolute

# ---------------- 文档分区 ----------------
FOLDERS_FILE = os.path.join(CONFIG_DIR, "folders.json")


def load_managed_folders():
    if not os.path.isfile(FOLDERS_FILE):
        return []
    try:
        with open(FOLDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict) and x.get("path")]
    except Exception:
        pass
    return []


def save_managed_folders(lst):
    try:
        with open(FOLDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def build_doc_roots():
    roots = []
    dirs_env = os.environ.get("VDITOR_DOC_DIRS", "").strip()
    if dirs_env:
        # 显式多分区（name::path 逗号分隔），优先级最高，可在任意部署下使用
        for item in dirs_env.split(","):
            item = item.strip()
            if not item:
                continue
            if "::" in item:
                name, path = item.split("::", 1)
                name, path = name.strip(), path.strip()
            else:
                path = item
                name = os.path.basename(path.rstrip("/")) or "文档"
            if path:
                roots.append((name, path))
    else:
        # 飞牛：访问权限/共享工作区/手动配置目录
        for name, path in collect_share_paths():
            roots.append((name, path))
    # 应用内手动管理文件夹（WebUI 中添加，持久化）始终并入
    for f in load_managed_folders():
        p = (f.get("path") or "").strip()
        if not p:
            continue
        name = (f.get("name") or "").strip() or (os.path.basename(p.rstrip("/")) or "文档")
        roots.append((name, p))
    if not roots:
        # 回退：单目录（运行时数据 docs 或 BASE_DIR/docs）
        default = os.environ.get("VDITOR_DOC_DIR")
        if not default:
            base = os.environ.get("TRIM_PKGVAR")
            default = os.path.join(base, "docs") if base else os.path.join(BASE_DIR, "docs")
        name = os.environ.get("VDITOR_DOC_NAME", "我的文档")
        roots.append((name, default))
    # 去重（按绝对路径），生成最终分区列表
    out = []
    seen = set()
    for name, path in roots:
        abspath = os.path.abspath(path)
        if abspath in seen:
            continue
        seen.add(abspath)
        rid = slugify(name)
        if rid in {r["id"] for r in out}:
            rid = "%s-%d" % (rid, len(out))
        try:
            os.makedirs(abspath, exist_ok=True)
        except OSError:
            pass
        out.append({"id": rid, "name": name, "path": abspath})
    # 过滤掉用户已隐藏（删除）的分区路径
    return [r for r in out if r["path"] not in EXCLUDED_PATHS]


DOC_ROOTS = build_doc_roots()
ROOT_MAP = {r["id"]: r for r in DOC_ROOTS}


def reload_doc_roots():
    global DOC_ROOTS, ROOT_MAP
    DOC_ROOTS = build_doc_roots()
    ROOT_MAP = {r["id"]: r for r in DOC_ROOTS}
    invalidate_files_cache()      # 分区变化 → 文件列表缓存失效
    invalidate_upload_index()

# ---------------- 文件历史版本 ----------------
def _migrate_to_folder_note(root_path, rel):
    """把旧式扁平文档 <...>/<stem>.md 迁移为 <...>/<stem>/<stem>.md（含历史版本目录），
    使每个文档独占一个同名文件夹、上传物得以与文档同放。返回迁移后的相对路径。"""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or not rel.lower().endswith(".md"):
        return rel
    fp = os.path.join(root_path, rel)
    # 已是「同名文件夹」结构（<...>/<stem>/<stem>.md）则**绝不**再迁移，
    # 否则每次打开都会再套一层，多次卸载重装后会叠成 <stem>/<stem>/…/<stem>.md。
    stem = os.path.splitext(os.path.basename(fp))[0]
    if stem and os.path.basename(os.path.dirname(fp)) == stem:
        return rel
    new_fp = _folder_note_path(fp)
    if new_fp == fp or os.path.exists(new_fp) or not os.path.isfile(fp):
        return rel
    try:
        os.makedirs(os.path.dirname(new_fp), exist_ok=True)
        os.rename(fp, new_fp)
        new_rel = os.path.relpath(new_fp, root_path).replace(os.sep, "/")
        old_v, new_v = _version_dir(root_path, rel), _version_dir(root_path, new_rel)
        if os.path.isdir(old_v) and not os.path.exists(new_v):
            try:
                os.rename(old_v, new_v)
            except OSError:
                pass
        return new_rel
    except OSError:
        return rel


def _build_upload_index():
    """扫描各分区，建立 <uuid>.<ext> → 完整路径 的索引（一次扫描，30 秒内复用）。"""
    m = {}
    for r in DOC_ROOTS:
        base = r["path"]
        if not os.path.isdir(base):
            continue
        for root2, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d != VERSIONS_DIRNAME]
            for n in names:
                if UPLOAD_NAME_RE.match(n):
                    m.setdefault(n, os.path.join(root2, n))
    _UPLOAD_INDEX["t"] = time.time()
    _UPLOAD_INDEX["map"] = m
    return m


def _find_uploaded(name):
    """按文件名在各文档文件夹中查找上传物（供「相对链接」回退解析；文件名是唯一 uuid）。"""
    if not UPLOAD_NAME_RE.match(name or ""):
        return None
    idx = _UPLOAD_INDEX
    if idx["map"] is None or (time.time() - idx["t"]) > _UPLOAD_INDEX_TTL:
        _build_upload_index()
    fp = _UPLOAD_INDEX["map"].get(name)
    if fp and os.path.isfile(fp):
        return fp
    legacy = os.path.join(UPLOAD_DIR, name)
    return legacy if os.path.isfile(legacy) else None


BACKUP_MAX_BYTES = 512 * 1024 * 1024  # 一键恢复上传的 .tar.gz 大小上限（512MB）

FAVICON_MAX_BYTES = 4 * 1024 * 1024      # 网页图标上传上限（4MB；正常图标仅几 KB）

def _version_dir(root_path, rel):
    """版本存储目录：<root>/.vditor_versions/<key>/（首次访问时把旧键目录迁移过来）。"""
    vroot = os.path.join(root_path, VERSIONS_DIRNAME)
    new_dir = os.path.join(vroot, _version_key(rel))
    old_dir = os.path.join(vroot, _legacy_version_key(rel))
    if not os.path.isdir(new_dir) and os.path.isdir(old_dir):
        try:
            os.makedirs(vroot, exist_ok=True)
            os.rename(old_dir, new_dir)     # 懒迁移：保留既有历史版本
        except OSError:
            return old_dir
    return new_dir

def save_file_version(root_path, rel, content_bytes):
    """覆盖写之前把旧内容快照为一个历史版本；仅在启用且内容发生变化时记录。"""
    if not SETTINGS.get("versioning"):
        return
    try:
        vdir = _version_dir(root_path, rel)
        os.makedirs(vdir, exist_ok=True)
        ts = int(time.time() * 1000)  # 毫秒时间戳，保证同一秒内不冲突
        with open(os.path.join(vdir, "%d.md" % ts), "wb") as f:
            f.write(content_bytes)
        # 仅保留最近 max_versions 个
        files = sorted(
            [x for x in os.listdir(vdir) if x.endswith(".md") and x[:-3].isdigit()],
            key=lambda x: int(x[:-3]),
        )
        excess = len(files) - int(SETTINGS.get("max_versions", 50))
        for old in files[:excess]:
            try:
                os.remove(os.path.join(vdir, old))
            except OSError:
                pass
    except OSError:
        pass

def list_file_versions(root_path, rel):
    vdir = _version_dir(root_path, rel)
    out = []
    if not os.path.isdir(vdir):
        return out
    for n in os.listdir(vdir):
        if not n.endswith(".md"):
            continue
        try:
            ts = int(n[:-3])
        except ValueError:
            continue
        try:
            st = os.stat(os.path.join(vdir, n))
            out.append({"ts": ts, "mtime": int(st.st_mtime), "size": st.st_size})
        except OSError:
            continue
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out

def _version_path(root_path, rel, ts):
    """历史版本文件路径；`ts` 非法时返回 None（调用方按「版本不存在」处理）。

    【为何不能裸写 int(ts)】ts 来自客户端 JSON / URL 参数，可能是 "abc"、None、[1]、NaN 等。
    裸 int() 抛出的 ValueError / TypeError 会一路冒泡到 socketserver，
    结果是**连接被直接断开、客户端收不到任何响应**，stderr 还打整段 traceback。
    与 `_content_length` / `_read_body` 同一思路：非法输入在唯一入口归一掉。
    """
    try:
        n = int(ts)
    except (TypeError, ValueError):
        return None
    return os.path.join(_version_dir(root_path, rel), "%d.md" % n)

def read_version(root_path, rel, ts):
    vfp = _version_path(root_path, rel, ts)
    if not vfp or not os.path.isfile(vfp):
        return None
    try:
        with open(vfp, "rb") as f:
            return f.read()
    except OSError:
        return None

def delete_version(root_path, rel, ts):
    vfp = _version_path(root_path, rel, ts)
    if not vfp or not os.path.isfile(vfp):
        return False
    try:
        os.remove(vfp)
        return True
    except OSError:
        return False

# ---------------- 响应安全头 / 缓存策略 ----------------
SEC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; "
        # 允许外链图片（图床等），否则外部图片会被浏览器 CSP 拦截无法显示
        "img-src 'self' data: blob: https: http:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "connect-src 'self'"
    ),
}

# ---------------- 请求体读取（统一入口，避免各处重复且遗漏异常处理） ----------------
# Content-Length 完全由客户端控制，既可能非法（abc / 空 / -1）也可能缺失。
# 历史上各处理函数各自 int() 解析，非法值会让 ValueError 冒泡到 socketserver，
# 导致连接被直接断开（客户端收到空响应）并向 stderr 打整段 traceback。
# 现统一收敛到本函数：任何异常都归一为 0，交由调用方按"空请求"处理。
def _content_length(handler):
    try:
        n = int(handler.headers.get("Content-Length", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _read_body(handler, limit):
    """按 Content-Length 读取请求体，**不超过 limit 字节**。
    缺失 / 非法 / 超限一律返回 b""（调用方据此回4xx），绝不抛异常、绝不无上限读入内存。"""
    n = _content_length(handler)
    if n <= 0 or n > limit:
        return b""
    return handler.rfile.read(n)


class Handler(BaseHTTPRequestHandler):
    server_version = "VditorNAS/2.0"
    protocol_version = "HTTP/1.1"

    def _build_headers(self, headers=None):
        """合并「安全头 + 本次附加头 + 待发 Cookie」，并清空待发队列。
        抽出成公共方法，避免 _send / _send_file / 304 三条路径各写一遍而漏掉 Set-Cookie。"""
        h = dict(SEC_HEADERS)
        if headers:
            h.update(headers)
        cookie = getattr(self, "_pending_cookie", None)
        if cookie:
            h["Set-Cookie"] = cookie
            self._pending_cookie = None
        return h

    def _send(self, code, body=b"", headers=None):
        h = self._build_headers(headers)
        self.send_response(code)
        for k, v in h.items():
            self.send_header(k, v)
        if "Content-Length" not in h:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _send_file(self, fp, headers=None):
        """流式返回文件（不整体读入内存），并按 ETag / Last-Modified 支持 304。"""
        try:
            st = os.stat(fp)
        except OSError:
            self._send(404, b"Not Found")
            return
        h = self._build_headers(headers)
        etag = h.get("ETag")
        lm = h.get("Last-Modified")
        inm = self.headers.get("If-None-Match") or ""
        ims = self.headers.get("If-Modified-Since") or ""
        if (etag and inm and etag in [x.strip() for x in inm.split(",")]) or \
           (lm and ims and ims == lm and not inm):
            self.send_response(304)
            for k in ("ETag", "Last-Modified", "Cache-Control"):
                if h.get(k):
                    self.send_header(k, h[k])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        h["Content-Length"] = str(st.st_size)
        self.send_response(200)
        for k, v in h.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            with open(fp, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 64 * 1024)

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, {"Content-Type": "application/json; charset=utf-8"})

    def _https_required_error(self):
        """安全策略要求 HTTPS（Secure Cookie）但当前为 HTTP 连接时，返回明确错误；
        返回 None 表示允许登录。局域网私有网段直连 HTTP 仍放行（见 _send_cookie）。"""
        proto = trusted_forwarded_proto(self)   # 仅本机/局域网代理可信，防伪造绕过
        if proto == "https":
            return None
        lan = is_private_ip(client_ip(self))
        if SETTINGS.get("secure_cookie") and not lan:
            return ("当前为 HTTP 连接，但安全策略要求使用 HTTPS（Secure Cookie 无法在 HTTP 下生效）。"
                    "请通过 HTTPS（如反向代理 / 域名）访问本应用后再登录。")
        return None

    def _transport_warning(self):
        """当前传输是否处于明文 HTTP。返回警告文案，**不阻断**请求。

        【为何移动端不能用 _https_required_error 拦截】
        那条策略是为了让 **Cookie** 带上 `Secure` 标记——HTTP 下浏览器会拒发该Cookie，
        属于「浏览器会话」的问题。而 `/api/m/` 走 `Authorization: Bearer <token>`，
        **完全不使用 Cookie**，该策略在这里不适用。

        更关键的是它会误伤反向代理 / 内网穿透：Cloudflare 隧道等由代理终止 TLS、
        回源走本机 HTTP，若代理未透传 `X-Forwarded-Proto`（或隧道部署在非本机网络命名空间），
        `trusted_forwarded_proto` 拿不到 https，就会把**实际已加密**的公网访问判成明文并拒绝登录——
        表现为 App 端「持续转圈 / 无法登录」。

        故此处只做提示：客户端可在界面上提醒用户，公网访问建议用 HTTPS。
        """
        if trusted_forwarded_proto(self) == "https":
            return ""
        if is_private_ip(client_ip(self)):
            return ""      # 局域网直连明文，属预期用法
        return "当前连接为明文 HTTP，密码与令牌在传输中未加密。建议通过 HTTPS 域名访问。"

    def _send_cookie(self, token):
        parts = ["vditor_sid=%s" % token, "HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=%d" % ABS_TIMEOUT]
        # Secure 仅当「强制 Cookie Secure 标记」开启且非局域网时附加。
        # 关闭该选项后，无论当前连接是 HTTP 还是 HTTPS，Cookie 都不带 Secure，
        # 从而允许公网 HTTP 登录后正常使用（不会因浏览器拒绝发送 Secure Cookie 而 401）。
        lan = is_private_ip(client_ip(self))
        if SETTINGS["secure_cookie"] and not lan:
            parts.append("Secure")
        self._pending_cookie = "; ".join(parts)

    def _clear_cookie(self):
        self._pending_cookie = "vditor_sid=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"

    def _require_auth(self):
        """返回 True 表示已登录；否则已发送 401 并 return False"""
        if get_session(self) is None:
            self._send_json({"error": "unauthenticated", "code": 401}, 401)
            return False
        return True

    # ---------------- 移动端 API 公共设施（/api/m/）----------------

    # 受「API 数据输出」开关控制的接口（这些会返回文档/分区/附件等实际数据）。
    # **不受控**的接口：health（探活）、auth/*（登录/登出/会话）——
    # 把它们也关掉的话，调试者连「服务是否在线、能否登录」都无法确认，
    # 开关就失去了调试价值。见 docs/MOBILE_API.md §7。
    _M_DATA_PATHS = frozenset((
        "/api/m/roots", "/api/m/files", "/api/m/file",
        "/api/m/file/versions", "/api/m/file/version",
        "/api/m/file/versions/restore", "/api/m/file/assets",
        "/api/m/upload", "/api/m/settings/upload",
    ))
    # 附件读取按名字动态拼接，无法进 frozenset，单独用前缀判定。
    # （此前 do_GET 里另写了一遍等价判定，两处容易漂移，现统一收敛到本函数。）
    _M_DATA_PREFIX = "/api/m/asset/"

    def _m_output_off(self, path):
        """判断当前请求是否因「API 数据输出」开关关闭而应被拦截。

        **鉴权优先于开关**：未登录时照常回 INVALID_TOKEN，
        只有"已登录但开关关闭"才回 API_OUTPUT_DISABLED——
        否则任何人都能探测出「这台机器有没有开 API 输出」，属于信息泄露。

        返回 True 时**已发送响应**，调用方须立即 return。
        """
        if path not in self._M_DATA_PATHS and not path.startswith(self._M_DATA_PREFIX):
            return False
        if SETTINGS.get("api_output") is True:
            return False
        # 未鉴权：交给后续 _m_require 处理，这里不抢答
        if not get_mtoken(self):
            return False
        self._m_send(M.fail("API_OUTPUT_DISABLED"))
        return True

    def _m_send(self, resp):
        """把 mobile_api 构造的响应包发出去（自动剥掉内部字段并取对应 HTTP 状态码）。"""
        self._send_json(M.strip_internal(resp), M.http_status(resp))

    def _m_require(self):
        """移动端鉴权：无有效 Bearer Token 时回 INVALID_TOKEN 并返回 None。

        只认 `Authorization: Bearer` 头——移动端数据接口一律走该方式，
        不接受 `?token=`（URL 会被日志/历史记录留存，不安全）。
        """
        tok = get_mtoken(self)
        if not tok:
            if NEEDS_SETUP:
                self._m_send(M.fail("NEED_SETUP"))
            else:
                self._m_send(M.fail("INVALID_TOKEN"))
            return None
        return tok

    def _m_file_item(self, root_id, root_path, name, fp, has_versions=None):
        """构造单个文档的列表项（规范 §4.2 items 元素）。

        `word_count` 不在服务端计算——Web 端顶栏是按**预览渲染后的可见字数**统计的
        （见 index.html 的 countReaderWords），服务端无法复现该口径，
        故列表接口不下发该字段，由端上在需要时另行取值或留空（避免给出虚高数值）。
        """
        try:
            st = os.stat(fp)
            size, mtime = st.st_size, int(st.st_mtime)
        except OSError:
            size, mtime = 0, 0
        rel = os.path.relpath(fp, root_path).replace(os.sep, "/")
        if has_versions is None:
            has_versions = bool(list_file_versions(root_path, rel))
        return {
            "id": M.doc_id(rel),
            "name": name,
            "path": rel,
            "root": root_id,
            "size": size,
            "updated_at": M.iso(mtime),
            "is_dir": False,
            "has_versions": has_versions,
        }

    def _m_doc_detail(self, root_id, root, fp):
        """构造文档详情（规范 §4.3 data），含附件列表。"""
        rel = self._rel(root["path"], fp)
        try:
            st = os.stat(fp)
            size, mtime = st.st_size, int(st.st_mtime)
        except OSError:
            size, mtime = 0, 0
        content = ""
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            pass
        created = mtime
        # 版本号 = 历史版本条数 + 1（与 Web 端「版本」语义一致：当前内容算第 N 版）
        versions = list_file_versions(root["path"], rel)
        # 附件：与文档同名的那个文件夹里除 .md 以外的文件
        assets = []
        adir = _doc_asset_dir(root["path"], rel)
        if adir and os.path.isdir(adir):
            for n in sorted(os.listdir(adir)):
                full = os.path.join(adir, n)
                if not os.path.isfile(full) or n.lower().endswith(".md"):
                    continue
                ext = n.rsplit(".", 1)[-1].lower() if "." in n else ""
                try:
                    asz = os.stat(full).st_size
                except OSError:
                    asz = 0
                assets.append({"name": n, "url": quote(n), "size": asz, "ext": ext})
        return {
            "id": M.doc_id(rel),
            "name": os.path.basename(fp),
            "path": rel,
            "root": root_id,
            "content": content,
            "size": size,
            "created_at": M.iso(created),
            "updated_at": M.iso(mtime),
            "version": len(versions) + 1,
            "assets": assets,
        }

    def _m_asset(self, name):
        """读取移动端上传的附件（规范 §4.9 返回的 url 对应此路由）。

        复用 Web 端的 `_find_uploaded`（按 uuid 文件名在各文档文件夹回退查找）与
        `upload_headers`（强制下载 + CSP sandbox）——**不另写一套定位或安全头逻辑**。
        """
        if not self._m_require():
            return
        nm = unquote(name or "")
        fp = _find_uploaded(nm)
        if not fp:
            self._m_send(M.fail("NOT_FOUND", "附件不存在"))
            return
        # 走 _send_file 而非「读全量再 _send」：附件上限可达 512MB，
        # 整体读入内存会瞬间打满 RSS（Web 端 /uploads/ 走的也是这条流式路径）。
        # upload_headers 不带 ETag，故不会触发 304 分支，行为与原先一致。
        self._send_file(fp, upload_headers(fp))

    def _m_resolve_doc(self, root_id, rel):
        """把 (root, path) 解析为 (root_dict, 绝对路径, 归一化相对路径)。非法返回 None。"""
        root = self._find_root(root_id)
        if not root or not rel:
            return None
        fp = self._safe_doc(root_id, rel)
        if not fp:
            return None
        return root, fp, self._rel(root["path"], fp)

    def _m_doc_target(self, data, code="FORBIDDEN", msg="root 或 path 无效"):
        """从请求体取出 root / path 并解析成文档目标，失败时**已发出响应**并返回 None。

        新建 / 保存 / 删除 / 回滚 / 附件列表五个接口都要走这段样板，此前各写一遍共 5 份。
        `code` 保留由调用方指定，是因为这些接口历史上返回的错误码并不统一
        （多数是 FORBIDDEN，`_m_list_assets` 是 BAD_REQUEST）——
        统一码会改变对外行为、破坏既有客户端，故此处只收敛**重复代码**、不动错误码。
        """
        root_id = M.take_str(data, "root", maxlen=128) or ""
        rel = M.take_str(data, "path", maxlen=1024) or ""
        got = self._m_resolve_doc(root_id, rel)
        if not got:
            self._m_send(M.fail(code, msg))
            return None
        return (root_id,) + got

    # ---------------- GET /api/m/* ----------------

    def _m_get(self, path, qs):
        """移动端 GET 路由分发。返回 True 表示已处理。"""
        # 数据输出开关（默认关闭）：在路由分发前统一拦截，避免逐个接口漏判
        if self._m_output_off(path):
            return True
        if path == "/api/m/health":
            self._m_send(M.ok({
                "status": "ok",
                "app": M.APP_ID,
                "version": APP_VERSION,
                "api_version": M.API_VERSION,
                "time": M.iso(time.time()),
                "setup_completed": not NEEDS_SETUP,
            }))
            return True

        # 【已移除】/api/m/editor —— 它只为已废弃的 Android 端 WebView 编辑器页
        # （m.html）提供页面下发，不是数据接口。App 下线后页面与路由一并删除；
        # `/api/m/*` 的**数据接口全部保留**（见 docs/MOBILE_API.md）。

        if path == "/api/m/auth/session":
            tok = self._m_require()
            if not tok:
                return True
            idle_left, abs_left = mtoken_left(tok)
            self._m_send(M.ok({
                "authenticated": True,
                "idle_expires_in": idle_left,
                "abs_expires_in": abs_left,
                "setup_completed": not NEEDS_SETUP,
            }))
            return True

        if path == "/api/m/roots":
            if not self._m_require():
                return True
            self._m_send(M.ok({"roots": [
                {"id": r["id"], "name": r["name"], "path": r["path"],
                 "hidden": False, "exists": os.path.isdir(r["path"])}
                for r in DOC_ROOTS]}))
            return True

        if path == "/api/m/files":
            if not self._m_require():
                return True
            self._m_get_files(qs)
            return True

        if path == "/api/m/file":
            if not self._m_require():
                return True
            self._m_get_file(qs)
            return True

        if path == "/api/m/file/versions":
            if not self._m_require():
                return True
            self._m_get_versions(qs)
            return True

        if path == "/api/m/file/version":
            if not self._m_require():
                return True
            self._m_get_version_content(qs)
            return True

        if path == "/api/m/settings/upload":
            if not self._m_require():
                return True
            deny = normalize_ext_list(SETTINGS.get("upload_deny", DEFAULT_UPLOAD_DENY))
            self._m_send(M.ok({
                "max_mb": M.take_int(SETTINGS, "upload_max_mb", 256, 1, 512),
                "min_mb": 1,
                "max_mb_limit": 512,
                "deny_exts": deny,
                "default_deny_exts": list(DEFAULT_UPLOAD_DENY),
            }))
            return True

        return False

    def _m_get_files(self, qs):
        root_id = (qs.get("root") or [""])[0]
        sub = (qs.get("path") or [""])[0].strip("/")
        root = self._find_root(root_id)
        if not root:
            self._m_send(M.fail("BAD_REQUEST", "root 无效，请先调用 /api/m/roots 获取分区列表"))
            return
        limit, offset = M.take_paging(qs)
        base = os.path.join(root["path"], sub) if sub else root["path"]
        if not os.path.isdir(base):
            self._m_send(M.ok({"items": [], "total": 0, "limit": limit, "offset": offset}))
            return
        items = []
        for n in sorted(os.listdir(base)):
            full = os.path.join(base, n)
            if os.path.isdir(full):
                if n == VERSIONS_DIRNAME or _in_doc_folder(root["path"],
                                                            self._rel(root["path"], full)):
                    continue    # 文档同名文件夹不作为独立条目暴露
                items.append({
                    "id": M.doc_id(self._rel(root["path"], full)),
                    "name": n, "path": self._rel(root["path"], full),
                    "root": root_id, "size": 0, "updated_at": M.iso(os.path.getmtime(full)),
                    "is_dir": True, "has_versions": False,
                })
            elif n.lower().endswith(".md"):
                items.append(self._m_file_item(root_id, root["path"], n, full))
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        self._m_send(M.ok({
            "items": items[offset:offset + limit],
            "total": len(items), "limit": limit, "offset": offset,
        }))

    def _m_get_file(self, qs):
        root_id = (qs.get("root") or [""])[0]
        rel = (qs.get("path") or [""])[0]
        got = self._m_resolve_doc(root_id, rel)
        if not got:
            self._m_send(M.fail("BAD_REQUEST", "root 或 path 无效"))
            return
        root, fp, _ = got
        if not os.path.isfile(fp):
            # 允许只给 stem（不带 .md），与 Web 端一致
            alt = fp + ".md"
            if os.path.isfile(alt):
                fp = alt
            else:
                self._m_send(M.fail("NOT_FOUND", "文档不存在"))
                return
        # 旧式扁平文档：打开即迁移为同名文件夹结构（与 Web 端一致）
        fp = os.path.join(root["path"], _migrate_to_folder_note(root["path"],
                                                                self._rel(root["path"], fp)))
        if not os.path.isfile(fp):
            self._m_send(M.fail("NOT_FOUND", "文档不存在"))
            return
        self._m_send(M.ok(self._m_doc_detail(root_id, root, fp)))

    def _m_get_versions(self, qs):
        root_id = (qs.get("root") or [""])[0]
        rel = (qs.get("path") or [""])[0]
        got = self._m_resolve_doc(root_id, rel)
        if not got:
            self._m_send(M.fail("BAD_REQUEST", "root 或 path 无效"))
            return
        root, _fp, rel_stored = got
        items = []
        for v in list_file_versions(root["path"], rel_stored):
            items.append({
                "version": v["ts"],
                "created_at": M.iso(v["ts"] / 1000.0),
                "size": v["size"],
                "source": "auto",
                "comment": "",
            })
        # 按时间**倒序**（最新在前）——与 Web 端历史面板的阅读顺序一致。
        # list_file_versions 返回的是目录内的原始顺序，不保证新→旧。
        items.sort(key=lambda x: x["version"], reverse=True)
        # 【双键下发】`items` 与 `versions` 同时给出。
        # 起因：1.2.0 端上读`versions`、本接口回 `items`，字段名不一致导致
        # 移动端历史版本列表**永远为空**（而浏览器端正常，因为它走 /api/version/*）。
        # 保留 `items` 兼容既有调用与测试，同时给出 `versions` 让端上直接可用。
        self._m_send(M.ok({"items": items, "versions": items, "total": len(items)}))

    def _m_get_version_content(self, qs):
        """取某个历史版本的内容，供移动端做「与当前对比」（1.2.0 新增）。

        权限校验与 `_m_get_versions` 完全一致：必须先经 `_m_resolve_doc`，
        该函数内部用 `_safe_doc` 把路径限制在所属分区内，越界/不存在一律拒绝。
        """
        root_id = (qs.get("root") or [""])[0]
        rel = (qs.get("path") or [""])[0]
        got = self._m_resolve_doc(root_id, rel)
        if not got:
            self._m_send(M.fail("FORBIDDEN", "root 或 path 无效"))
            return
        root, _fp, rel_stored = got
        raw_ts = (qs.get("version") or [""])[0]
        try:
            ts = int(raw_ts)
        except (TypeError, ValueError):
            self._m_send(M.fail("BAD_REQUEST", "version 必须为整数（毫秒时间戳）"))
            return
        data = read_version(root["path"], rel_stored, ts)
        if data is None:
            self._m_send(M.fail("NOT_FOUND", "该历史版本不存在"))
            return
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = data.decode("utf-8", "replace")
        self._m_send(M.ok({
            "version": ts,
            "created_at": M.iso(ts / 1000.0),
            "size": len(data),
            "content": content,
        }))

    # ---------------- 移动端 POST/PUT/DELETE ----------------

    def _m_post(self, path):
        """移动端 POST 路由分发。返回 True 表示已处理。"""
        if path == "/api/m/auth/login":
            self._m_login()
            return True
        if path == "/api/m/auth/logout":
            # 登出必须**幂等**：token 已失效（含重复登出、超时后登出）同样回 ok，
            # 客户端语义上「没有有效会话」就是「已登出」，不该当成错误。
            # 因此这里不用 _m_require()（它会先回 401），改为自行判断。
            tok = get_mtoken(self)
            if tok:
                MTOKENS.pop(tok, None)
            self._m_send(M.ok({"logged_out": True}))
            return True
        if not self._m_require():
            return True
        # 数据输出开关（默认关闭）。置于鉴权之后：login/logout 不受影响，
        # 且未登录请求仍按 INVALID_TOKEN 处理。
        if self._m_output_off(path):
            return True
        if path == "/api/m/file":
            self._m_new_file()
            return True
        if path == "/api/m/file/versions/restore":
            self._m_restore_version()
            return True
        if path == "/api/m/upload":
            self._m_upload()
            return True
        if path == "/api/m/file/assets":
            self._m_list_assets()
            return True
        return False

    def _m_put(self, path):
        if path != "/api/m/file":
            return False
        if not self._m_require():
            return True
        if self._m_output_off(path):
            return True
        self._m_save_file()
        return True

    def _m_delete(self, path):
        if path != "/api/m/file":
            return False
        if not self._m_require():
            return True
        if self._m_output_off(path):
            return True
        self._m_delete_file()
        return True

    def _m_login(self):
        if NEEDS_SETUP:
            self._m_send(M.fail("NEED_SETUP"))
            return
        ip = client_ip(self)
        if is_locked(ip):
            self._m_send(M.fail("RATE_LIMITED", "登录失败次数过多，请稍后再试"))
            return
        data = self._json_body("密码格式不正确")
        if data is None:
            return
        pwd = M.take_str(data, "password", required=False, default="", maxlen=256)
        if pwd is None:
            self._m_send(M.fail("BAD_REQUEST", "密码格式不正确"))
            return
        # 【勿改回 _https_required_error()】移动端用 Bearer Token 而非 Cookie，
        # 该策略只对浏览器会话成立；且会误伤 Cloudflare 隧道等「代理终止 TLS、回源 HTTP」
        # 的部署，把已加密的公网访问判成明文而拒登。详见 _transport_warning 注释。
        warn = self._transport_warning()
        time.sleep(FAIL_DELAY)      # 失败延迟：削弱暴力破解的时间差
        if not verify_pwhash(PWHASH, pwd):
            record_failure(ip)
            self._m_send(M.fail("FORBIDDEN", "密码错误"))
            return
        record_success(ip)
        tok = start_mtoken(self)
        idle_left, abs_left = mtoken_left(tok)
        payload = {
            "token": tok,
            "expires_in": abs_left,
            "idle_expires_in": idle_left,
        }
        if warn:
            payload["warning"] = warn
        self._m_send(M.ok(payload))

    def _m_new_file(self):
        data = self._json_body()
        if data is None:
            return
        root_id = M.take_str(data, "root", maxlen=128) or ""
        rel = M.take_str(data, "path", maxlen=1024) or ""
        content = M.take_str(data, "content", required=False, default="", maxlen=MAX_BODY_BYTES)
        if content is None:
            self._m_send(M.fail("BAD_REQUEST", "path 或 content 非法"))
            return
        got = self._m_doc_target(data, "FORBIDDEN", "父路径非法")
        if not got:
            return
        root_id, root, fp, _rel_stored = got
        fp = _folder_note_path(fp)
        if os.path.exists(fp):
            self._m_send(M.fail("CONFLICT", "同名文档已存在"))
            return
        try:
            if os.path.dirname(fp):
                os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            invalidate_files_cache()
        except OSError as e:
            self._m_send(M.fail("SERVER_ERROR", "写入失败：%s" % e))
            return
        self._m_send(M.ok(self._m_doc_detail(root_id, root, fp)))

    def _m_save_file(self):
        data = self._json_body()
        if data is None:
            return
        content = M.take_str(data, "content", required=False, default="", maxlen=MAX_BODY_BYTES)
        if content is None:
            self._m_send(M.fail("BAD_REQUEST", "path 或 content 非法"))
            return
        got = self._m_doc_target(data, "FORBIDDEN", "路径非法")
        if not got:
            return
        root_id, root, fp, rel_stored = got
        # 乐观锁：if_version 与服务端当前版本不一致则拒写，避免多端互相覆盖
        if "if_version" in data:
            want = data.get("if_version")
            cur = len(list_file_versions(root["path"], rel_stored)) + 1
            try:
                want_i = int(want)
            except (TypeError, ValueError):
                self._m_send(M.fail("BAD_REQUEST", "if_version 必须为整数"))
                return
            if want_i != cur:
                self._m_send(M.fail("FORBIDDEN", "文档已被其他端修改（版本 %d，本地 %d）" % (cur, want_i)))
                return
        try:
            if os.path.dirname(fp):
                os.makedirs(os.path.dirname(fp), exist_ok=True)
            if os.path.isfile(fp):
                try:
                    with open(fp, "rb") as f:
                        prev = f.read()
                    if prev and prev != content.encode("utf-8"):
                        save_file_version(root["path"], rel_stored, prev)
                except OSError:
                    pass
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            invalidate_files_cache()
        except OSError as e:
            self._m_send(M.fail("SERVER_ERROR", "保存失败：%s" % e))
            return
        self._m_send(M.ok(self._m_doc_detail(root_id, root, fp)))

    def _m_delete_file(self):
        data = self._json_body()
        if data is None:
            return
        got = self._m_doc_target(data, "FORBIDDEN", "路径非法")
        if not got:
            return
        root_id, root, fp, rel_stored = got
        if not os.path.isfile(fp):
            self._m_send(M.fail("NOT_FOUND", "文档不存在"))
            return
        try:
            os.remove(fp)
            # 同名文件夹（含全部上传物与历史版本）一并清理
            adir = _doc_asset_dir(root["path"], rel_stored)
            if adir and os.path.isdir(adir):
                shutil.rmtree(adir, ignore_errors=True)
            vdir = _version_dir(root["path"], rel_stored)
            if os.path.isdir(vdir):
                shutil.rmtree(vdir, ignore_errors=True)
            invalidate_files_cache()
            invalidate_upload_index()
        except OSError as e:
            self._m_send(M.fail("SERVER_ERROR", "删除失败：%s" % e))
            return
        self._m_send(M.ok({"deleted": True, "root": root_id, "path": rel_stored}))

    def _m_restore_version(self):
        data = self._json_body()
        if data is None:
            return
        got = self._m_doc_target(data, "FORBIDDEN", "路径非法")
        if not got:
            return
        root_id, root, fp, rel_stored = got
        try:
            want = int(data.get("version"))
        except (TypeError, ValueError):
            self._m_send(M.fail("BAD_REQUEST", "version 必须为整数"))
            return
        content = read_version(root["path"], rel_stored, want)
        if content is None:
            self._m_send(M.fail("NOT_FOUND", "该版本不存在"))
            return
        try:
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    prev = f.read()
                if prev and prev != content:
                    save_file_version(root["path"], rel_stored, prev)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content.decode("utf-8"))
            invalidate_files_cache()
        except OSError as e:
            self._m_send(M.fail("SERVER_ERROR", "回滚失败：%s" % e))
            return
        self._m_send(M.ok(self._m_doc_detail(root_id, root, fp)))

    def _m_list_assets(self):
        data = self._json_body()
        if data is None:
            return
        got = self._m_doc_target(data, "BAD_REQUEST", "root 或 path 无效")
        if not got:
            return
        root_id, root, _fp, rel_stored = got
        detail = self._m_doc_detail(root_id, root, os.path.join(root["path"], rel_stored))
        self._m_send(M.ok({"assets": detail["assets"]}))

    def _m_upload(self):
        """附件上传。与 Web 端共用黑名单判定、大小上限与安全响应头（不另写一套校验）。"""
        limit_mb = M.take_int(SETTINGS, "upload_max_mb", 256, 1, 512)
        body = _read_body(self, min(MAX_UPLOAD_BYTES, limit_mb * 1024 * 1024))
        if not body:
            self._m_send(M.fail("BAD_REQUEST", "请求体为空或超过大小上限"))
            return
        ctype = self.headers.get("Content-Type", "")
        bm = re.search(r"boundary=([^;]+)", ctype)
        if "multipart/form-data" not in ctype.lower() or not bm:
            self._m_send(M.fail("BAD_REQUEST", "需 multipart/form-data 且须带 boundary"))
            return
        boundary = bm.group(1).strip().strip('"').encode("utf-8")
        files, fields = parse_multipart(body, boundary)
        if not files:
            self._m_send(M.fail("BAD_REQUEST", "缺少文件字段 file"))
            return
        # 单文件接口：取第一个（field 名为 file）
        _field, fname, fdata = files[0]
        root_id = (fields.get("root") or "")[:128]
        doc_rel = (fields.get("path") or "")[:1024]
        base_name = os.path.basename(fname or "")
        ext = base_name.rsplit(".", 1)[-1].lower() if "." in base_name else ""
        if not base_name or not ext:
            self._m_send(M.fail("BAD_REQUEST", "文件名或扩展名非法"))
            return
        deny = normalize_ext_list(SETTINGS.get("upload_deny", DEFAULT_UPLOAD_DENY))
        # is_denied_upload 收的是**文件名**（内部做 splitext 取扩展名），
        # 传裸扩展名会因splitext("exe") 得到空扩展名而漏判放行——必须传完整文件名。
        if is_denied_upload(base_name, deny):
            self._m_send(M.fail("DENIED_EXT", "「.%s」在不允许上传的文件格式列表中" % ext))
            return
        # 落盘位置：有 path 则进该文档的同名文件夹，否则进全局 uploads
        if root_id and doc_rel:
            got = self._m_resolve_doc(root_id, doc_rel)
            if not got:
                self._m_send(M.fail("BAD_REQUEST", "root 或 path 无效"))
                return
            root, _fp, rel_stored = got
            adir = _doc_asset_dir(root["path"], rel_stored)
            target_dir = adir if adir else os.path.join(root["path"], os.path.dirname(rel_stored))
        else:
            target_dir = UPLOAD_DIR
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as e:
            self._m_send(M.fail("SERVER_ERROR", "创建目录失败：%s" % e))
            return
        stored = "%s.%s" % (uuid.uuid4().hex, ext)
        fp = os.path.join(target_dir, stored)
        try:
            with open(fp, "wb") as f:
                f.write(fdata)
        except OSError as e:
            self._m_send(M.fail("SERVER_ERROR", "写入失败：%s" % e))
            return
        invalidate_upload_index()
        self._m_send(M.ok({
            "name": stored,
            "url": "/api/m/asset/" + stored,
            "ext": ext,
            "size": len(fdata),
            "insert_text": "![](" + stored + ")",
        }))

    # ---------------- GET ----------------
    def do_GET(self):
        self._pending_cookie = None
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path.startswith("/api/m/"):
            # 附件读取：与上传接口对称，需鉴权（附件可能含私密内容）。
            # 同样受「API 数据输出」开关约束——附件正文本身就是文档数据。
            if path.startswith("/api/m/asset/"):
                if self._m_output_off(path):
                    return
                self._m_asset(path[len(self._M_DATA_PREFIX):])
                return
            if self._m_get(path, qs):
                return
            self._m_send(M.fail("NOT_FOUND", "接口不存在"))
            return

        # 公开：鉴权状态 / 首次设置状态
        if path == "/api/auth/check":
            self._send_json({"authenticated": get_session(self) is not None,
                             "needsSetup": NEEDS_SETUP})
            return
        if path == "/api/setup/status":
            self._send_json({"needsSetup": NEEDS_SETUP})
            return

        # 受限：文档/文件 API（需登录）
        if path == "/api/files":
            if not self._require_auth(): return
            self._api_list_files()
            return
        if path == "/api/file":
            if not self._require_auth(): return
            self._api_read_file(qs)
            return
        if path == "/api/folders":
            if not self._require_auth(): return
            self._api_folders()
            return

        if path == "/api/settings":
            if not self._require_auth(): return
            self._send_json(self._api_settings_get())
            return
        if path == "/api/settings/export":
            if not self._require_auth(): return
            self._api_settings_export()
            return
        if path == "/api/login-log":
            if not self._require_auth(): return
            self._send_json({"entries": load_login_log()})
            return
        if path == "/api/versions":
            if not self._require_auth(): return
            self._api_list_versions(qs)
            return
        if path == "/api/version/diff":
            if not self._require_auth(): return
            self._api_version_diff(qs)
            return
        if path == "/api/backup":
            if not self._require_auth(): return
            self._api_backup()
            return

        if path == "/api/doc/info":
            if not self._require_auth(): return
            self._api_doc_info(qs)
            return
        if path == "/api/doc/assets":
            if not self._require_auth(): return
            self._api_doc_assets(qs)
            return
        if path == "/favicon.ico":
            self._send_favicon()
            return

        if path == "/":
            path = "/index.html"

        # 安全策略要求 HTTPS 时，非局域网 HTTP 访问不再返回应用页面：
        # 登录守卫只在「收到请求后」判断，此时密码已在明文链路上传输过，故需从前端页面层面拦截，
        # 让用户根本不会在不安全连接上输入密码。
        if path == "/index.html":
            https_err = self._https_required_error()
            if https_err:
                page = ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
                        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                        "<title>需要 HTTPS 访问</title></head>"
                        "<body style=\"font-family:system-ui,sans-serif;padding:40px;line-height:1.8;color:#24292e\">"
                        "<h2 style=\"margin:0 0 12px\">需要 HTTPS 访问</h2><p>%s</p></body></html>" % https_err)
                self._send(403, page.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"})
                return

        # 已上传 / 被引用的文件（需登录）
        if path.startswith("/uploads/"):
            if not self._require_auth(): return
            rest = path[len("/uploads/"):].lstrip("/")
            fp = None
            if "/" in rest:
                # /uploads/<分区id>/<分区内相对路径> → 与文档同目录的图片 / 音频等
                rid, sub = rest.split("/", 1)
                root = self._find_root(rid)
                if root and sub:
                    fp = safe_join(root["path"], sub)
            else:
                # 兼容旧式：/uploads/<文件名>（早期文档中已引用的上传物）
                fp = safe_join(UPLOAD_DIR, rest)
            if fp and os.path.isfile(fp):
                self._send_file(fp, upload_headers(fp))   # 内联/下载策略 + 沙箱，防存储型 XSS
            else:
                self._send(404, b"Not Found")
            return

        # 上传物的「相对链接」回退解析：文档内以文件名（uuid.ext）引用图片 / 音频时，
        # 页面以相对路径请求 / <uuid>.<ext>，这里按文件名在各文档文件夹中查找后返回。
        if UPLOAD_NAME_RE.match(path.lstrip("/")):
            if not self._require_auth(): return
            fp = _find_uploaded(path.lstrip("/"))
            if fp and os.path.isfile(fp):
                self._send_file(fp, upload_headers(fp))   # 同上，按类型决定内联或强制下载
            else:
                self._send(404, b"Not Found")
            return

        # 公开静态资源：**白名单**（/index.html、/vditor/**、/ui/**），其余一律 404；
        # 叠加 is_static_denied 兜底（源码 / 配置 / 密钥 / 点文件永不外泄）。
        if is_public_static(path):
            fp = safe_join(BASE_DIR, path)
            if fp and os.path.isfile(fp) and not is_static_denied(fp):
                self._send_file(fp, static_headers(fp))  # ETag/Last-Modified → 支持 304
                return
        self._send(404, b"Not Found")

    def do_HEAD(self):
        self.do_GET()

    def do_PUT(self):
        """移动端保存文档（规范 §4.5，PUT /api/m/file）。Web 端无PUT，此方法仅服务移动端。"""
        self._pending_cookie = None
        parsed = urlparse(self.path)
        p = parsed.path
        if not p.startswith("/api/m/"):
            self._send_json({"ok": False, "error": "not found"}, 404)
            return
        if _content_length(self) > MAX_BODY_BYTES:
            self.close_connection = True
            self._m_send(M.fail("TOO_LARGE", "请求体过大"))
            return
        if not self._m_put(p):
            self._m_send(M.fail("NOT_FOUND", "接口不存在"))

    def do_DELETE(self):
        """移动端删除文档（规范 §4.6）。"""
        self._pending_cookie = None
        parsed = urlparse(self.path)
        p = parsed.path
        if not p.startswith("/api/m/"):
            self._send_json({"ok": False, "error": "not found"}, 404)
            return
        if _content_length(self) > MAX_BODY_BYTES:
            self.close_connection = True
            self._m_send(M.fail("TOO_LARGE", "请求体过大"))
            return
        if not self._m_delete(p):
            self._m_send(M.fail("NOT_FOUND", "接口不存在"))

    # ---------------- POST ----------------
    def do_POST(self):
        self._pending_cookie = None
        parsed = urlparse(self.path)
        p = parsed.path

        # 移动端 API：独立前缀，独立鉴权与响应包（在统一体积上限判断之内先行分流）
        if p.startswith("/api/m/"):
            limit = min(MAX_UPLOAD_BYTES, int(SETTINGS.get("upload_max_mb", 256)) * 1024 * 1024) \
                if p == "/api/m/upload" else MAX_BODY_BYTES
            if _content_length(self) > limit:
                self.close_connection = True
                self._m_send(M.fail("TOO_LARGE", "请求体过大（上限 %d MB）" % (limit // (1024 * 1024))))
                return
            if self._m_post(p):
                return
            self._m_send(M.fail("NOT_FOUND", "接口不存在"))
            return

        # 统一的请求体上限：先于任何处理判断，超大请求直接 413（避免读入内存造成 DoS）
        clen = _content_length(self)
        if p == "/api/upload":
            limit = min(MAX_UPLOAD_BYTES, int(SETTINGS.get("upload_max_mb", 256)) * 1024 * 1024)
        elif p == "/api/backup/restore":
            limit = BACKUP_MAX_BYTES
        elif p == "/api/favicon":
            limit = FAVICON_MAX_BYTES
        else:
            limit = MAX_BODY_BYTES
        if clen > limit:
            self.close_connection = True
            self._send_json({"ok": False, "error": "请求体过大（上限 %d MB）" % (limit // (1024 * 1024))}, 413)
            return

        # 登录 / 登出 / 首次设置：无需先登录
        if p == "/api/login":
            self._handle_login()
            return
        if p == "/api/logout":
            record_login_event("logout", client_ip(self), "")
            end_session(self)
            self._clear_cookie()
            self._send_json({"ok": True})
            return
        if p == "/api/setup":
            self._handle_setup()
            return

        # 以下接口均需登录
        if not self._require_auth(): return

        if p == "/api/settings":
            self._api_settings_update()
            return
        if p == "/api/settings/import":
            self._api_settings_import()
            return
        if p == "/api/backup/restore":
            self._api_backup_restore()
            return
        if p == "/api/change-password":
            self._api_change_password()
            return
        if p == "/api/version/restore":
            self._api_restore_version()
            return
        if p == "/api/version/delete":
            self._api_delete_version()
            return
        if p == "/api/save":
            self._api_save(parsed)
            return
        if p == "/api/new":
            self._api_new(parsed)
            return
        if p == "/api/upload":
            self._handle_upload()
            return
        if p == "/api/folders":
            self._api_folders_update()
            return
        if p == "/api/doc/delete":
            self._api_doc_delete()
            return
        if p == "/api/export-zip":
            self._api_export_zip()
            return
        if p == "/api/favicon":
            self._handle_favicon_upload()
            return
        self._send_json({"msg": "not found", "code": 404, "data": {}}, 404)

    # ---------------- 鉴权处理 ----------------
    def _handle_login(self):
        ip = client_ip(self)
        err = self._https_required_error()
        if err:
            record_login_event("login_blocked_http", ip, "")
            self._send_json({"ok": False, "error": err}, 403)
            return
        if is_locked(ip):
            self._send_json({"ok": False, "error": "账号已被锁定，请 %d 分钟后再试" % (LOCK_DURATION // 60)}, 423)
            return
        data = self._json_body("请求格式错误")
        if data is None:
            return
        pw = data.get("password", "")
        ok = (PWHASH is not None) and verify_pwhash(PWHASH, pw)
        if ok:
            record_success(ip)
            record_login_event("login_ok", ip, "")
            token = start_session(self)
            self._send_cookie(token)
            self._send_json({"ok": True})
        else:
            record_failure(ip)
            record_login_event("login_fail", ip, "")
            time.sleep(FAIL_DELAY)  # 人为延迟，拖慢爆破
            self._send_json({"ok": False, "error": "密码错误"}, 401)

    def _handle_setup(self):
        global PWHASH, NEEDS_SETUP
        ip = client_ip(self)
        err = self._https_required_error()
        if err:
            self._send_json({"ok": False, "error": err}, 403)
            return
        # 仅当尚未设置密码时允许首次设置；已设置后该接口不可用（改密需登录后另做）
        if not NEEDS_SETUP and PWHASH is not None:
            self._send_json({"ok": False, "error": "已初始化，无法重复设置"}, 403)
            return
        data = self._json_body("请求格式错误")
        if data is None:
            return
        pw = data.get("password", "")
        if not pw or len(pw) < 6:
            self._send_json({"ok": False, "error": "密码至少 6 位"}, 400)
            return
        h = make_pwhash(pw)
        if not save_pwhash(h):
            self._send_json({"ok": False, "error": "写入密码文件失败"}, 500)
            return
        PWHASH = h
        NEEDS_SETUP = False
        record_login_event("setup", ip, "")
        token = start_session(self)
        self._send_cookie(token)
        self._send_json({"ok": True})

    def _handle_upload(self):
        ctype = self.headers.get("Content-Type", "")
        m = re.search(r"boundary=([^;]+)", ctype)
        if not m:
            self._send_json({"msg": "bad request", "code": 1, "data": {}}, 400)
            return
        boundary = m.group(1).strip().strip('"').encode("utf-8")
        succ_map = {}
        err_files = []
        try:
            # 上限与 do_POST 的判定一致（单请求取「单文件上限」与「硬上限」的较小者）；
            # 非法 / 缺失 Content-Length 时得到 b""，后续解析自然失败并回错，不会抛异常。
            body = _read_body(self, min(MAX_UPLOAD_BYTES, int(SETTINGS.get("upload_max_mb", 256)) * 1024 * 1024))
            files, fields = parse_multipart(body, boundary)
            # 上传物与文档放在一起：存进「当前文档所在目录」（每文档一个同名文件夹）；未指定则用分区根。
            root = self._find_root((fields.get("root") or "").strip())
            if root is None:
                root = DOC_ROOTS[0] if DOC_ROOTS else None
            if root is None:
                raise RuntimeError("未配置任何文档分区，无法上传")
            doc_rel = (fields.get("path") or "").strip().replace("\\", "/").lstrip("/")
            dest = _doc_asset_dir(root["path"], doc_rel)
            if not dest:
                raise RuntimeError("非法路径")
            os.makedirs(dest, exist_ok=True)
            dest_rel = os.path.dirname(doc_rel)
            max_bytes = int(SETTINGS.get("upload_max_mb", 256)) * 1024 * 1024
            # 注意用 .get(k, default) 而非 `or default`：用户主动把黑名单清空时值为空串，
            # `or` 会把它悄悄还原成默认清单，使"删除全部条目"失效。空串即"不限制"。
            deny = SETTINGS.get("upload_deny", DEFAULT_UPLOAD_DENY)
            for field, fname, content in files:
                ext = os.path.splitext(fname)[1].lower()
                if len(ext) > 10:
                    ext = ""
                # 格式黑名单（唯一校验依据）：仅拒绝命中黑名单的类型，其余一律放行。
                # 另：即便放行，html/js 等类型仍由 upload_headers 强制下载 + CSP 沙箱，
                # 不会被浏览器当作可执行脚本运行（纵深防御）。
                if is_denied_upload(fname, deny):
                    err_files.append(fname)
                    continue
                if len(content) > max_bytes:
                    err_files.append(fname)
                    continue
                store = uuid.uuid4().hex + ext
                out = os.path.join(dest, store)
                with open(out, "wb") as f:
                    f.write(content)
                # 返回相对 md 文件的链接（文件名）——上传物与文档同目录，导出后可直接离线打开
                succ_map[fname] = store
            invalidate_upload_index()
        except Exception as e:
            self._send_json({"msg": str(e), "code": 1, "data": {"errFiles": err_files, "succMap": succ_map}})
            return
        self._send_json({"msg": "", "code": 0, "data": {"errFiles": err_files, "succMap": succ_map}})

    # ---------------- 文档管理（多分区）----------------
    def _read_json(self):
        """读取并解析 JSON 请求体，**保证返回 dict**（非法则抛异常，由 `_json_body` 统一回 400）。

        【为何必须在这里卡一道】调用方（20 处 `_json_body`）一律按 dict 使用（`data.get(...)`），
        而 `json.loads` 对 `[1,2]`、`"str"`、`123`、`null` 这类**合法 JSON 但顶层非对象**
        的输入同样解析成功，返回 list / str / int / None，随后 `data.get()` 抛
        AttributeError 并冒泡到 socketserver——连接被直接断开，客户端收不到任何响应。
        与该模块既有的 `_content_length` / `_read_body` 同一思路：非法输入在唯一入口归一。
        """
        raw = _read_body(self, MAX_BODY_BYTES)
        if not raw:
            return {}
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("JSON 顶层必须是对象")
        return obj

    def _json_body(self, err="bad json"):
        """读取 JSON 请求体；解析失败时就地回 400 并返回 None。
        抽出成公共方法，避免 11 处「try _read_json / except 回 400」样板各自复制。"""
        try:
            return self._read_json()
        except Exception:
            self._send_json({"ok": False, "error": err}, 400)
            return None

    def _find_root(self, root_id):
        return ROOT_MAP.get(root_id)

    def _safe_doc(self, root_id, rel):
        root = self._find_root(root_id)
        if not root or not rel:
            return None
        rel = rel.lstrip("/")
        if not rel.lower().endswith(".md"):
            rel = rel + ".md"
        return safe_join(root["path"], rel)

    def _rel(self, root_path, fp):
        return os.path.relpath(fp, root_path).replace(os.sep, "/")

    # ---------------- 文件夹管理（应用内指定可访问文件夹）----------------
    def _send_folders(self, ok=True):
        managed_paths = {os.path.abspath(x.get("path", "")) for x in load_managed_folders()}
        self._send_json({
            "ok": ok,
            "roots": [{"id": r["id"], "name": r["name"], "path": r["path"],
                      "managed": os.path.abspath(r["path"]) in managed_paths} for r in DOC_ROOTS],
            "managed": load_managed_folders(),
            "excluded": sorted(EXCLUDED_PATHS),
        })

    def _api_folders(self):
        self._send_folders()

    def _api_folders_update(self):
        data = self._json_body()
        if data is None:
            return
        action = data.get("action")
        lst = load_managed_folders()
        if action == "add":
            name = (data.get("name") or "").strip()
            path = (data.get("path") or "").strip()
            if not path:
                self._send_json({"ok": False, "error": "路径不能为空"}, 400)
                return
            ap = os.path.abspath(path)
            EXCLUDED_PATHS.discard(ap)  # 若曾被隐藏则恢复
            managed_paths = {os.path.abspath(x.get("path", "")) for x in lst}
            root_paths = {os.path.abspath(r["path"]) for r in DOC_ROOTS}
            if ap not in managed_paths and ap not in root_paths:
                if not name:
                    name = os.path.basename(path.rstrip("/")) or "文档"
                lst.append({"name": name, "path": path})
                if not save_managed_folders(lst):
                    self._send_json({"ok": False, "error": "保存失败"}, 500)
                    return
            reload_doc_roots()
            self._send_folders()
        elif action == "remove":
            path = (data.get("path") or "").strip()
            if not path:
                self._send_json({"ok": False, "error": "路径不能为空"}, 400)
                return
            ap = os.path.abspath(path)
            newlst = [x for x in lst if os.path.abspath(x.get("path", "")) != ap]
            if len(newlst) == len(lst):
                # 系统分区或已隐藏分区：加入排除列表（隐藏）
                EXCLUDED_PATHS.add(ap)
                if not save_excluded():
                    self._send_json({"ok": False, "error": "保存失败"}, 500)
                    return
            else:
                if not save_managed_folders(newlst):
                    self._send_json({"ok": False, "error": "保存失败"}, 500)
                    return
            reload_doc_roots()
            self._send_folders()
        elif action == "restore":
            path = (data.get("path") or "").strip()
            if not path:
                self._send_json({"ok": False, "error": "路径不能为空"}, 400)
                return
            EXCLUDED_PATHS.discard(os.path.abspath(path))
            if not save_excluded():
                self._send_json({"ok": False, "error": "保存失败"}, 500)
                return
            reload_doc_roots()
            self._send_folders()
        else:
            self._send_json({"ok": False, "error": "未知操作"}, 400)

    def _api_list_files(self):
        now = time.time()
        cached = _FILES_CACHE["data"]
        if cached is not None and (now - _FILES_CACHE["t"]) < _FILES_TTL:
            self._send_json(cached)
            return
        roots = []
        for r in DOC_ROOTS:
            files = []
            base = r["path"]
            if os.path.isdir(base):
                for root, dirs, names in os.walk(base):
                    # 排除历史版本目录，避免“我的文档”误显示历史版本文件
                    if VERSIONS_DIRNAME in dirs:
                        dirs.remove(VERSIONS_DIRNAME)
                    for n in names:
                        if n.lower().endswith(".md"):
                            full = os.path.join(root, n)
                            try:
                                st = os.stat(full)
                                files.append({
                                    "root": r["id"],
                                    "name": n,
                                    "path": self._rel(base, full),
                                    "mtime": int(st.st_mtime),
                                    "size": st.st_size,
                                })
                            except OSError:
                                continue
            files.sort(key=lambda x: x["name"].lower())
            roots.append({
                "id": r["id"], "name": r["name"], "path": base,
                "exists": os.path.isdir(base), "files": files,
            })
        payload = {"roots": roots}
        _FILES_CACHE["t"] = time.time()
        _FILES_CACHE["data"] = payload
        self._send_json(payload)

    def _api_read_file(self, qs):
        root_id = (qs.get("root") or [""])[0]
        rel = (qs.get("path") or [""])[0]
        fp = self._safe_doc(root_id, rel)
        root = self._find_root(root_id)
        if not fp or not root or not os.path.isfile(fp):
            self._send_json({"error": "not found"}, 404)
            return
        # 旧式扁平文档：打开即迁移为「每文档一个同名文件夹」，使上传物与文档同放
        new_rel = _migrate_to_folder_note(root["path"], self._rel(root["path"], fp))
        fp = os.path.join(root["path"], new_rel)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            self._send_json({"error": str(e)}, 500)
            return
        self._send_json({"root": root_id, "path": new_rel,
                         "name": os.path.basename(fp), "content": content})

    def _api_save(self, parsed):
        data = self._json_body()
        if data is None:
            return
        root_id = data.get("root", "")
        rel = data.get("path", "")
        content = data.get("content", "")
        fp = self._safe_doc(root_id, rel)
        root = self._find_root(root_id)
        if not fp or not root:
            self._send_json({"ok": False, "error": "invalid path"}, 400)
            return
        rel_stored = self._rel(root["path"], fp)
        try:
            parent = os.path.dirname(fp)
            if parent:
                os.makedirs(parent, exist_ok=True)
            # 覆盖写之前，把旧内容快照为历史版本（内容有变化才记录）
            if os.path.isfile(fp):
                try:
                    with open(fp, "rb") as f:
                        prev = f.read()
                    if prev and prev != content.encode("utf-8"):
                        save_file_version(root["path"], rel_stored, prev)
                except OSError:
                    pass
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            invalidate_files_cache()
            st = os.stat(fp)
            self._send_json({"ok": True, "root": root_id, "path": rel_stored,
                             "abspath": os.path.abspath(fp), "mtime": int(st.st_mtime)})
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    def _api_new(self, parsed):
        data = self._json_body()
        if data is None:
            return
        root_id = data.get("root", "")
        rel = data.get("path", "")
        root = self._find_root(root_id)
        fp = self._safe_doc(root_id, rel)
        if not fp or not root:
            self._send_json({"ok": False, "error": "invalid path"}, 400)
            return
        # 每文档独立文件夹：<...>/<stem>.md → <...>/<stem>/<stem>.md（便于上传物随文档一起打包导出）
        fp = _folder_note_path(fp)
        if os.path.exists(fp):
            self._send_json({"ok": False, "error": "exists"}, 409)
            return
        try:
            if os.path.dirname(fp):
                os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write("")
            invalidate_files_cache()
            self._send_json({"ok": True, "root": root_id, "path": self._rel(root["path"], fp)})
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    # ---------------- 设置 / 安全 / 版本 / 备份 ----------------
    def _safe_doc_rel(self, root, rel):
        fp = self._safe_doc(root["id"], rel)
        if not fp:
            return None
        return self._rel(root["path"], fp)

    def _api_settings_get(self):
        return {
            "settings": dict(SETTINGS),
            "envLocked": {
                "trust_proxy": "VDITOR_TRUST_PROXY" in os.environ,
                "secure_cookie": "VDITOR_SECURE_COOKIE" in os.environ,
            },
        }

    def _apply_int_setting(self, data, key, lo, hi, label, errs, state):
        """整型设置字段的统一校验：夹到 [lo, hi]、非数字则记错、值变则标记变更。
        抽出成公共方法，避免 autosave_interval / max_versions / upload_max_mb 三处重复同一段逻辑。"""
        if key not in data:
            return False
        try:
            v = min(hi, max(lo, int(float(data[key]))))
        except (TypeError, ValueError):
            errs.append("%s 必须为数字" % label)
            return False
        if state.get(key) != v:
            state[key] = v
            return True
        return False

    def _apply_settings(self, data):
        """统一校验并应用设置字段，返回 (changed, errors)。供 WebUI 保存与配置导入复用。"""
        changed = False
        errs = []
        if not isinstance(data, dict):
            return changed, ["配置格式无效"]
        # api_output：**仅用于开发调试**的 API 数据输出开关（默认关闭）。
        # 与 trust_proxy/secure_cookie 等同走布尔校验与同一条持久化路径，
        # 保证「前端配置项 / 后端校验 / 持久化」三者行为一致。
        for k in ("trust_proxy", "secure_cookie", "versioning", "clear_on_uninstall",
                  "api_output"):
            if k in data:
                if isinstance(data[k], bool):
                    if SETTINGS.get(k) != data[k]:
                        SETTINGS[k] = data[k]; changed = True
                else:
                    errs.append("%s 必须为布尔值" % k)
        # 三个整型字段：范围不同、报错文案不同，故仅抽取校验骨架
        changed |= self._apply_int_setting(data, "autosave_interval", 10, 1 << 30,
                                          "autosave_interval", errs, SETTINGS)
        changed |= self._apply_int_setting(data, "max_versions", 1, 1 << 30,
                                          "max_versions", errs, SETTINGS)
        changed |= self._apply_int_setting(data, "upload_max_mb", 1, 512,
                                          "upload_max_mb（1–512）", errs, SETTINGS)
        for k, limit in (("page_title", 60), ("favicon", 2000)):
            if k in data:
                v = (data[k] or "").strip()[:limit]
                if SETTINGS.get(k) != v:
                    SETTINGS[k] = v; changed = True
        if "upload_deny" in data:
            raw = data["upload_deny"]
            if isinstance(raw, (list, tuple)):
                raw = ",".join(str(x) for x in raw)
            raw = (raw or "").strip()
            clean = normalize_ext_list(raw)
            # 逐项回显被丢弃的非法条目（避免用户输入了却毫无反馈）。
            # 切分口径与 normalize_ext_list 共用 split_ext_tokens，避免两处规则漂移。
            dropped = []
            for p in split_ext_tokens(raw):
                t = p.strip().lstrip(".").lower()
                if t and t not in clean:
                    dropped.append(p.strip())
            if dropped:
                errs.append("以下扩展名不合法（需字母开头，仅含字母 / 数字 / 连字符，1–12 位）：" + "、".join(dropped[:8]))
            v = ",".join(clean)
            if SETTINGS.get("upload_deny") != v:
                SETTINGS["upload_deny"] = v; changed = True
        if "upload_accept" in data:
            # 【已废弃】1.1.2 的白名单字段：仅原样保存以备降级，不再参与任何校验。
            v = (data["upload_accept"] or "").strip()
            if SETTINGS.get("upload_accept") != v:
                SETTINGS["upload_accept"] = v; changed = True
        return changed, errs

    def _apply_and_reply(self, data, changed_key=None):
        """校验 → 持久化 → 回包。设置页保存与配置导入走的是同一条链路，
        差别只在回包里是否附带变更标记，故收敛到这里，避免两处各写一遍。

        `changed_key` 非空时，回包里额外带上 `{changed_key: changed}`
        （导入接口历史上一直接 `imported`，保留以免破坏既有调用方）。
        """
        changed, errs = self._apply_settings(data)
        if errs:
            self._send_json({"ok": False, "error": "; ".join(errs)})
            return
        if changed:
            save_settings()
        body = {"ok": True, "settings": dict(SETTINGS)}
        if changed_key:
            body[changed_key] = changed
        self._send_json(body)

    def _api_settings_update(self):
        data = self._json_body()
        if data is None:
            return
        self._apply_and_reply(data)

    def _api_settings_export(self):
        keys = (
            "trust_proxy", "secure_cookie", "versioning", "max_versions",
            "autosave_interval", "page_title", "favicon", "clear_on_uninstall",
            "upload_max_mb", "upload_deny", "upload_accept", "api_output",
        )
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
        data = self._json_body()
        if data is None:
            return
        # 兼容两种入参：直接传 settings 对象，或 {"settings": {...}}
        if isinstance(data, dict) and isinstance(data.get("settings"), dict):
            data = data["settings"]
        self._apply_and_reply(data, "imported")

    def _api_change_password(self):
        global PWHASH
        data = self._json_body("请求格式错误")
        if data is None:
            return
        old = data.get("old_password", "")
        new = data.get("new_password", "")
        confirm = data.get("confirm_password", new)
        if not PWHASH:
            self._send_json({"ok": False, "error": "尚未设置密码"}, 400)
            return
        if not verify_pwhash(PWHASH, old):
            self._send_json({"ok": False, "error": "原密码错误"}, 403)
            return
        if len(new) < 6:
            self._send_json({"ok": False, "error": "新密码至少 6 位"}, 400)
            return
        if new != confirm:
            self._send_json({"ok": False, "error": "两次输入不一致"}, 400)
            return
        h = make_pwhash(new)
        if not save_pwhash(h):
            self._send_json({"ok": False, "error": "写入密码文件失败"}, 500)
            return
        PWHASH = h
        SESSIONS.clear()  # 改密后强制所有会话重新登录
        record_login_event("pw_change", client_ip(self), "")
        self._send_json({"ok": True})

    def _api_list_versions(self, qs):
        root_id = (qs.get("root") or [""])[0]
        rel = (qs.get("path") or [""])[0]
        root = self._find_root(root_id)
        if not root:
            self._send_json({"error": "invalid root"}, 400)
            return
        rel = self._safe_doc_rel(root, rel)
        if not rel:
            self._send_json({"error": "invalid path"}, 400)
            return
        self._send_json({
            "root": root_id, "path": rel,
            "storage_path": _version_dir(root["path"], rel),
            "versions": list_file_versions(root["path"], rel),
        })

    def _api_version_diff(self, qs):
        import difflib
        root_id = (qs.get("root") or [""])[0]
        rel = (qs.get("path") or [""])[0]
        try:
            ts = int((qs.get("ts") or [0])[0])
        except Exception:
            ts = 0
        root = self._find_root(root_id)
        if not root:
            self._send_json({"error": "invalid root"}, 400); return
        rel = self._safe_doc_rel(root, rel)
        if not rel:
            self._send_json({"error": "invalid path"}, 400); return
        vers = list_file_versions(root["path"], rel)
        if not any(v["ts"] == ts for v in vers):
            self._send_json({"error": "version not found"}, 404); return
        # 上一（更早）版本：小于 ts 中最大者
        older = None
        for v in sorted(vers, key=lambda x: x["ts"]):
            if v["ts"] < ts:
                older = v
        new_content = read_version(root["path"], rel, ts)
        if new_content is None:
            self._send_json({"error": "version not found"}, 404); return
        old_content = read_version(root["path"], rel, older["ts"]) if older else b""
        new_lines = new_content.decode("utf-8", "replace").splitlines()
        old_lines = old_content.decode("utf-8", "replace").splitlines()
        diff = list(difflib.unified_diff(old_lines, new_lines,
                                        fromfile="上一版本", tofile="该版本", lineterm=""))
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        self._send_json({"ts": ts, "prev_ts": older["ts"] if older else None,
                         "diff": diff, "added": added, "removed": removed})

    def _api_restore_version(self):
        data = self._json_body()
        if data is None:
            return
        root_id = data.get("root", "")
        rel = data.get("path", "")
        ts = data.get("ts", 0)
        root = self._find_root(root_id)
        if not root:
            self._send_json({"ok": False, "error": "invalid root"}, 400)
            return
        rel = self._safe_doc_rel(root, rel)
        if not rel:
            self._send_json({"ok": False, "error": "invalid path"}, 400)
            return
        content = read_version(root["path"], rel, ts)
        if content is None:
            self._send_json({"ok": False, "error": "版本不存在"}, 404)
            return
        fp = safe_join(root["path"], rel)
        if not fp:
            self._send_json({"ok": False, "error": "invalid path"}, 400)
            return
        # 恢复前先快照当前内容，避免覆盖丢失
        if os.path.isfile(fp):
            try:
                with open(fp, "rb") as f:
                    cur = f.read()
                save_file_version(root["path"], rel, cur)
            except OSError:
                pass
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as f:
                f.write(content)
            self._send_json({"ok": True, "content": content.decode("utf-8", "replace"),
                             "path": rel, "root": root_id})
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    def _api_delete_version(self):
        data = self._json_body()
        if data is None:
            return
        root_id = data.get("root", "")
        rel = data.get("path", "")
        ts = data.get("ts", 0)
        root = self._find_root(root_id)
        if not root:
            self._send_json({"ok": False, "error": "invalid root"}, 400)
            return
        rel = self._safe_doc_rel(root, rel)
        if not rel:
            self._send_json({"ok": False, "error": "invalid path"}, 400)
            return
        ok = delete_version(root["path"], rel, ts)
        self._send_json({"ok": ok, "versions": list_file_versions(root["path"], rel)})


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

    def _api_doc_assets(self, qs):
        """文档所在文件夹内、除文档自身以外的文件（图片 / 音频等），用于判断「是否需打包导出」。"""
        root = self._find_root((qs.get("root") or [""])[0])
        if not root:
            self._send_json({"error": "invalid root"}, 400); return
        rel = self._safe_doc_rel(root, (qs.get("path") or [""])[0])
        if not rel:
            self._send_json({"error": "invalid path"}, 400); return
        base = _doc_asset_dir(root["path"], rel)
        files = []
        if base and os.path.isdir(base):
            doc_name = os.path.basename(rel)
            for r2, dirs, names in os.walk(base):
                for n in names:
                    full = os.path.join(r2, n)
                    rrel = os.path.relpath(full, base).replace(os.sep, "/")
                    if rrel != doc_name:
                        files.append(rrel)
        self._send_json({"count": len(files), "files": files[:100]})

    def _api_export_zip(self):
        """把文档所在文件夹整体打成 zip（含 md 与上传的图片 / 音频）；若传入 html 则一并放入。"""
        data = self._json_body()
        if data is None:
            return
        root = self._find_root(data.get("root", ""))
        if not root:
            self._send_json({"ok": False, "error": "invalid root"}, 400); return
        rel = self._safe_doc_rel(root, data.get("path", ""))
        if not rel:
            self._send_json({"ok": False, "error": "invalid path"}, 400); return
        base = _doc_asset_dir(root["path"], rel)
        if not base or not os.path.isdir(base):
            self._send_json({"ok": False, "error": "目录不存在"}, 404); return
        stem = os.path.splitext(os.path.basename(rel))[0] or "document"
        import io as _io
        import zipfile as _zipfile
        buf = _io.BytesIO()
        with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as z:
            for r2, dirs, names in os.walk(base):
                for n in names:
                    full = os.path.join(r2, n)
                    rrel = os.path.relpath(full, base).replace(os.sep, "/")
                    z.write(full, arcname="%s/%s" % (stem, rrel))
            html = data.get("html")
            if isinstance(html, str) and html:
                z.writestr("%s/%s.html" % (stem, stem), html)
        out = buf.getvalue()
        ascii_stem = stem.encode("ascii", "ignore").decode() or "document"
        self._send(200, out, {
            "Content-Type": "application/zip",
            "Content-Disposition": "attachment; filename=\"%s.zip\"; filename*=UTF-8''%s.zip" % (
                ascii_stem, quote(stem)),
        })

    def _api_doc_delete(self):
        data = self._json_body()
        if data is None:
            return
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
            # 若 .vditor_versions 目录已空，一并清理，避免残留空目录
            parent = os.path.dirname(vdir)
            if os.path.isdir(parent) and not os.listdir(parent):
                try:
                    os.rmdir(parent)
                except OSError:
                    pass
            invalidate_files_cache()
            self._send_json({"ok": True})
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    def _send_favicon(self):
        """/favicon.ico 是**未鉴权**即可访问的公开路径，必须自己兜住所有 IO 异常——
        否则图标文件被删 / 权限异常时 OSError 会冒泡到 socketserver，连接被直接断开。"""
        import glob
        try:
            matches = sorted(glob.glob(os.path.join(CONFIG_DIR, "favicon.*")))
        except OSError:
            matches = []
        if not matches:
            self._send(204, b"")
            return
        try:
            with open(matches[0], "rb") as f:
                data = f.read()
        except OSError:
            self._send(204, b"")
            return
        self._send(200, data, {"Content-Type": guess_mime(matches[0])})

    def _handle_favicon_upload(self):
        ctype = self.headers.get("Content-Type", "")
        m = re.search(r"boundary=([^;]+)", ctype)
        if not m:
            self._send_json({"ok": False, "error": "bad request"}, 400); return
        boundary = m.group(1).strip().strip('"').encode("utf-8")
        try:
            files, _fields = parse_multipart(_read_body(self, FAVICON_MAX_BYTES), boundary)
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

    def _api_backup(self):
        import tarfile as _tarfile
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix="vditor-backup-", suffix=".tar.gz")
        os.close(fd)
        # try/finally：打包或发送途中一旦抛异常，临时文件也必须删掉，
        # 否则每次失败都在系统临时目录留一份几百 MB 的 .tar.gz。
        try:
            self._build_backup(tmp, _tarfile)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _build_backup(self, tmp, _tarfile):
        """把配置与文档打包进临时文件并流式返回（拆分出来以便用 try/finally 兜住清理）。"""
        with _tarfile.open(tmp, mode="w:gz") as tar:
            # ① 应用配置：配置目录下全部文件（Web 设置 / 文件夹列表 / 密码哈希 / 登录日志 / 图标等）
            if os.path.isdir(CONFIG_DIR):
                for nm in sorted(os.listdir(CONFIG_DIR)):
                    fp = os.path.join(CONFIG_DIR, nm)
                    if os.path.isfile(fp):
                        tar.add(fp, arcname="config/" + nm)
            # ② 各分区内容：全部 Markdown 文档 + 历史版本缓存 + 上传的图片/音频等
            for r in DOC_ROOTS:
                base = r["path"]
                if not os.path.isdir(base):
                    continue
                for root2, dirs, names in os.walk(base):
                    for n in names:
                        full = os.path.join(root2, n)
                        try:
                            rel = self._rel(base, full)
                        except OSError:
                            continue
                        top = rel.split("/", 1)[0]
                        # 收录：文档(.md)、历史版本目录、以及「文档文件夹」内的上传物（图片 / 音频等）
                        if not (top == VERSIONS_DIRNAME or n.lower().endswith(".md")
                                or _in_doc_folder(base, rel)):
                            continue
                        try:
                            tar.add(full, arcname="docs/%s/%s" % (r["id"], rel))
                        except OSError:
                            continue
        # 流式返回（不把整个备份包读入内存）
        self._send_file(tmp, {
            "Content-Type": "application/gzip",
            "Content-Disposition": "attachment; filename=vditor-backup-%s.tar.gz" % time.strftime("%Y%m%d-%H%M%S"),
            "Cache-Control": "no-store",
        })

    def _api_backup_restore(self):
        """从上传的 .tar.gz 备份一键恢复：应用配置 + 文档 + 历史版本 + 上传物（覆盖同名文件）。"""
        global SETTINGS, PWHASH, NEEDS_SETUP, EXCLUDED_PATHS
        length = _content_length(self)
        if length <= 0:
            self._send_json({"ok": False, "error": "空请求"}, 400); return
        if length > BACKUP_MAX_BYTES:
            self._send_json({"ok": False, "error": "备份文件过大（上限 %d MB）" % (BACKUP_MAX_BYTES // (1024 * 1024))}, 413); return
        import io as _io
        import tarfile as _tarfile
        import tempfile
        ctype = self.headers.get("Content-Type", "")
        tmp = None
        if "multipart/form-data" in ctype:
            # 兼容旧式 multipart 上传（整体读入内存）
            m = re.search(r"boundary=([^;]+)", ctype)
            if not m:
                self._send_json({"ok": False, "error": "bad request"}, 400); return
            boundary = m.group(1).strip().strip('"').encode("utf-8")
            try:
                files, _fields = parse_multipart(_read_body(self, BACKUP_MAX_BYTES), boundary)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 400); return
            if not files:
                self._send_json({"ok": False, "error": "未收到文件"}, 400); return
            content = files[0][2]
            try:
                tar = _tarfile.open(fileobj=_io.BytesIO(content), mode="r:gz")
            except Exception as e:
                self._send_json({"ok": False, "error": "不是有效的 .tar.gz 备份：%s" % e}, 400); return
        else:
            # 推荐路径：直接把 .tar.gz 作为请求体，**流式落盘**（不占内存）
            fd, tmp = tempfile.mkstemp(prefix="vditor-restore-", suffix=".tar.gz")
            remaining = length
            try:
                with os.fdopen(fd, "wb") as f:
                    while remaining > 0:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                tar = _tarfile.open(tmp, mode="r:gz")
            except Exception as e:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                self._send_json({"ok": False, "error": "不是有效的 .tar.gz 备份：%s" % e}, 400); return
        # try/finally：解包循环里出现任何异常（含 tarfile 自身的 ReadError）
        # 都要删掉临时文件，否则每次失败都在系统临时目录留一份几百 MB 的包。
        try:
            n_cfg, n_doc = self._extract_backup(tar)
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        # 恢复后热重载配置与分区
        SETTINGS = load_settings()
        PWHASH, NEEDS_SETUP = load_pwhash()
        EXCLUDED_PATHS = load_excluded()
        reload_doc_roots()
        invalidate_files_cache()
        invalidate_upload_index()
        self._send_json({"ok": True, "config": n_cfg, "docs": n_doc})

    def _extract_backup(self, tar):
        """把备份包内的 config/ 与 docs/ 解回原位置，返回 (配置数, 文档数)。"""
        n_cfg = n_doc = 0
        with tar:
            for m2 in tar.getmembers():
                if not m2.isfile():
                    continue
                name = m2.name.replace("\\", "/").lstrip("/")
                if ".." in name.split("/"):
                    continue  # 防目录穿越
                if name.startswith("config/"):
                    base, rel = CONFIG_DIR, name[len("config/"):]
                    is_cfg = True
                elif name.startswith("docs/"):
                    rest = name[len("docs/"):]
                    if "/" not in rest:
                        continue
                    rid, rel = rest.split("/", 1)
                    root = self._find_root(rid)
                    if not root or not rel:
                        continue
                    base = root["path"]
                    is_cfg = False
                else:
                    continue
                dest = safe_join(base, rel)
                if not dest:
                    continue
                try:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    src = tar.extractfile(m2)
                    if src is None:
                        continue
                    with open(dest, "wb") as f:
                        shutil.copyfileobj(src, f, 1024 * 1024)   # 流式写出，不整体读入内存
                    n_cfg += 1 if is_cfg else 0
                    n_doc += 0 if is_cfg else 1
                except OSError:
                    continue
        return n_cfg, n_doc

    def log_message(self, fmt, *args):
        sys.stderr.write("[vditor-nas] %s - %s\n" % (self.address_string(), fmt % args))


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 56)
    print(" Vditor NAS 已启动（安全增强版）")
    print(" 监听地址 : http://%s:%d" % (HOST, PORT))
    print(" 本机访问 : http://127.0.0.1:%d" % PORT)
    print(" 资源目录 : %s" % BASE_DIR)
    print(" 上传目录 : %s" % UPLOAD_DIR)
    print(" 文档分区 :")
    for r in DOC_ROOTS:
        print("   - [%s] %s" % (r["name"], r["path"]))
    if NEEDS_SETUP:
        print(" 安全提示 : 首次访问需设置管理员密码（/api/setup）")
    else:
        print(" 访问控制 : 已启用密码登录")
    if not SETTINGS["trust_proxy"]:
        print(" 代理提示 : 若经反向代理/内网穿透，请在『设置』中开启“信任代理(X-Forwarded-For)”，以正确识别客户端 IP")
    print(" 按 Ctrl+C 停止")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭...")
        server.shutdown()


if __name__ == "__main__":
    main()
