#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vditor 应用 —— 无副作用的工具与常量（从 server.py 抽出）。

这里只放**纯函数与常量**：不读写任何可变模块状态（SETTINGS / SESSIONS / DOC_ROOTS / PWHASH 等
仍留在 server.py）。因此可被安全地直接 import，不存在「两个模块各持一份状态」的隐患。
"""
import os
import re
import json
import time
import hashlib
import ipaddress
import mimetypes
from urllib.parse import unquote

EXTRA_MIME = {
    ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
    ".svg": "image/svg+xml", ".woff": "font/woff", ".woff2": "font/woff2",
    ".ttf": "font/ttf", ".json": "application/json", ".wasm": "application/wasm",
    ".map": "application/json",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
    ".m4a": "audio/mp4", ".webm": "audio/webm", ".flac": "audio/flac",
}


# 禁止作为公开静态资源返回的文件（防止后端源码、密码哈希与配置被直接下载）。
# 说明：CONFIG_DIR 在 fnOS 下指向 etc 目录，但裸跑（python3 server.py）时会回退到
# BASE_DIR，此时 settings.json / pwhash 等会落在站点根下，必须显式拒绝。
STATIC_DENY_NAMES = {
    "config.env", "settings.json", "login_log.json",
    "folders.json", "excluded.json", "pwhash",
}


STATIC_DENY_EXTS = (".py", ".pyc", ".env")


MAX_BODY_BYTES = 64 * 1024 * 1024        # 普通 JSON 接口请求体上限


MAX_UPLOAD_BYTES = 512 * 1024 * 1024     # 上传接口请求体硬上限（单个文件大小设置最大可设 512MB）


CACHE_MAX_AGE = 300                      # 静态资源缓存秒数（配合 ETag/Last-Modified 校验）


UPLOAD_MAX_AGE = 31536000                # 上传物按 uuid 命名（内容不变），可长期缓存


# 上传物响应策略：可安全内联展示的类型（图片 / 音视频 / PDF）直接返回；
# 其余（含 html / js / xml 等可执行内容）一律强制下载并加 CSP sandbox，
# 避免「上传的 HTML 被同源打开 → 执行脚本 → 调用本应用 API」的存储型 XSS。
UPLOAD_INLINE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg",
    ".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac", ".webm",
    ".mp4", ".m4v", ".ogv", ".mov", ".pdf",
}


UPLOAD_SANDBOX_EXTS = {".svg"}           # .svg 需内联（<img>），但顶层打开禁止执行脚本


UPLOAD_NAME_RE = re.compile(r"^[0-9a-f]{32}\.[A-Za-z0-9][A-Za-z0-9-]{0,11}$")

# ---------- 上传格式黑名单（1.1.3 起为唯一校验依据） ----------
# 语义反转说明：1.1.2 用的是「白名单」（upload_accept，留空=不限制）。1.1.3 改为
# 「黑名单」（upload_deny）——默认放行一切，仅拒绝下列高风险扩展名；用户可在设置
# 界面自由追加 / 删除条目。旧字段 upload_accept 保留在 settings.json 中但不再参与
# 校验，仅为降级兼容。
#
# 为什么不用白名单：白名单一旦漏配就会误拦正常文件（1.1.2 实测故障的根因之一，见
# CHANGELOG 1.1.3），且用户需自行长期维护一份不断增长的清单。
DEFAULT_UPLOAD_DENY = (
    # Windows 可执行 / 脚本 / 加载项
    "exe,dll,com,bat,cmd,scr,pif,cpl,msi,msp,mst,jar,lnk,scf,hta,reg,appref-ms,"
    # 各类脚本与解释器代码
    "js,jse,vbs,vbe,wsf,wsh,ps1,psm1,sh,bash,zsh,csh,ksh,fish,py,pyc,pyo,rb,pl,pm,"
    "php,phtml,php3,php4,php5,phar,cgi,asp,aspx,ashx,asmx,cer,jsp,jspx,cfm,cfc,"
    # 可在浏览器或本地直接执行 / 主动加载的内容
    "html,htm,xhtml,shtml,svg,svgz,xml,xsl,xslht,mhtml,mht,swf,crx,xpi,apk"
)

# 扩展名书写规范：字母开头，仅含字母 / 数字 / 连字符，长度 1–12。
# 连字符必须支持——真实扩展名里存在 appref-ms、x-zmachine 等含 '-' 的类型，
# 1.1.3 初版漏掉它导致默认清单里的 appref-ms 被判非法、进而使「恢复默认」后无法保存。
# 长度上限与 UPLOAD_NAME_RE 的后缀段保持一致。
_EXT_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,11}$")


# 扩展名列表可能来自多种书写习惯：半角/全角逗号、分号、空格。
# 统一归一化成半角逗号再切分——抽成函数供 normalize_ext_list 与服务端的
# 「逐项回显非法条目」共用，避免两处分头维护导致口径漂移。
# 分隔符集合与 1.1.3 及之前完全一致（逗号 / 分号 / 空格），**不引入换行**：
# 换行此前会被并进 token 导致该项判非法，新加会静默改变既有解析结果。
_SEP_RE = re.compile(r"[，,; ]+")


def split_ext_tokens(raw):
    """把原始输入按逗号/ 分号 / 空格 / 换行切成扩展名 token 列表（保留原始大小写与前导点）。"""
    return [t for t in _SEP_RE.split(str(raw or "")) if t]


def normalize_ext_list(raw):
    """把用户填写的扩展名列表规范化成「小写、去点、去空项、去重」的有序列表。

    支持逗号 / 空格 / 分号 / 中文逗号分隔，允许带点（.EXE 与 exe 等价）。
    非法项（空、非字母数字、超长）直接丢弃。
    """
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        parts = []
        for x in raw:
            parts.extend(split_ext_tokens(x))
    else:
        parts = split_ext_tokens(raw)
    out, seen = [], set()
    for p in parts:
        t = p.strip().lstrip(".").lower()
        if not t or not _EXT_TOKEN_RE.match(t) or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def is_denied_upload(filename, deny_raw):
    """上传黑名单判定（唯一校验依据）。

    deny_raw 为用户配置的扩展名列表（逗号分隔字符串，或已规范化的列表 / 集合）。
    返回被拒绝的扩展名（小写、不含点）；未命中返回空串。
    无扩展名、或黑名单为空时一律放行。
    """
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    if not ext:
        return ""
    if isinstance(deny_raw, (list, tuple, set)):
        deny = {str(x).strip().lstrip(".").lower() for x in deny_raw}
    else:
        deny = set(normalize_ext_list(deny_raw))
    return ext if ext in deny else ""


VERSIONS_DIRNAME = ".vditor_versions"


_FILES_CACHE = {"t": 0.0, "data": None}     # /api/files 结果短缓存


_FILES_TTL = 2.0


_UPLOAD_INDEX = {"t": 0.0, "map": None}     # uuid 上传物 → 路径 索引


_UPLOAD_INDEX_TTL = 30.0


def _http_date(ts):
    return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(ts))


def upload_headers(fp):
    """上传物 / 被引用资源：按类型决定内联还是下载，并对可执行内容加沙箱。"""
    ext = os.path.splitext(fp)[1].lower()
    h = {"Content-Type": guess_mime(fp),
         "Cache-Control": "public, max-age=%d, immutable" % UPLOAD_MAX_AGE}
    if ext not in UPLOAD_INLINE_EXTS:
        h["Content-Disposition"] = "attachment"
        h["Content-Security-Policy"] = "sandbox; default-src 'none'"
    elif ext in UPLOAD_SANDBOX_EXTS:
        h["Content-Security-Policy"] = "sandbox"
    return h


def static_headers(fp):
    """静态资源：ETag + Last-Modified + 可校验缓存（避免每次全量重下）。"""
    try:
        st = os.stat(fp)
    except OSError:
        return {"Content-Type": guess_mime(fp)}
    return {
        "Content-Type": guess_mime(fp),
        "ETag": '"%x-%x"' % (int(st.st_mtime), st.st_size),
        "Last-Modified": _http_date(st.st_mtime),
        "Cache-Control": "public, max-age=%d" % CACHE_MAX_AGE,
    }


def trusted_forwarded_proto(handler):
    """仅当直连来源为私有 / 回环（确经本机或局域网代理）时才信任 X-Forwarded-Proto，
    否则客户端可自行伪造该头绕过「强制 HTTPS」判定。"""
    proto = (handler.headers.get("X-Forwarded-Proto", "") or "").lower()
    if proto and is_private_ip(handler.client_address[0]):
        return proto
    return ""


def invalidate_files_cache():
    _FILES_CACHE["data"] = None


def invalidate_upload_index():
    _UPLOAD_INDEX["map"] = None


def is_private_ip(ip):
    """判断 IPv4/IPv6 是否为私有/回环/链路本地网段（局域网）。"""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version == 6 and getattr(addr, "ipv4_mapped", None) is not None:
        addr = addr.ipv4_mapped
    return addr.is_private or addr.is_loopback or addr.is_link_local


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5_-]", "-", s or "").strip("-")
    return s or "root"


def _paths_from_json(txt):
    """尝试把一段文本按 JSON 解析成路径列表；不是可识别的 JSON 时返回 None（交调用方回退）。"""
    try:
        obj = json.loads(txt)
    except Exception:
        return None
    if isinstance(obj, list):
        return [str(x).strip() for x in obj if str(x).strip()]
    if isinstance(obj, dict):
        for k in ("paths", "data_share_paths", "list", "items"):
            if k in obj and isinstance(obj[k], list):
                return [str(x).strip() for x in obj[k] if str(x).strip()]
        return [str(v).strip() for v in obj.values() if str(v).strip()]
    if isinstance(obj, str):
        return [obj.strip()] if obj.strip() else []
    return None


def parse_data_share_paths(raw):
    raw = (raw or "").strip()
    if not raw:
        return []
    got = _paths_from_json(raw)
    if got is not None:
        return got
    # 飞牛 TRIM_DATA_SHARE_PATHS 常见为冒号分隔；亦兼容逗号/分号/换行。
    # 需还原 Windows 盘符（如 C:\a:C:\b 拆分后重组），Linux 路径不受影响。
    parts = re.split(r"[:,;\n]", raw)
    out = []
    i = 0
    while i < len(parts):
        p = parts[i].strip().strip('"').strip("'")
        if re.fullmatch(r"[A-Za-z]", p) and i + 1 < len(parts) and parts[i + 1].lstrip().startswith(("\\", "/")):
            out.append(p + ":" + parts[i + 1].lstrip())
            i += 2
            continue
        if p:
            out.append(p)
        i += 1
    return out


def read_share_paths_file(fp):
    """读取 share_paths 文件（飞牛“访问权限/手动配置”可能写入）：
       支持 JSON 数组、单行带引号路径、逐行路径。"""
    if not fp or not os.path.isfile(fp):
        return []
    try:
        with open(fp, "r", encoding="utf-8") as f:
            txt = f.read().strip()
    except OSError:
        return []
    if not txt:
        return []
    got = _paths_from_json(txt)
    if got is not None:
        return got
    out = []
    for line in txt.splitlines():
        line = line.strip().strip('"').strip("'")
        if line:
            out.append(line)
    return out


def collect_share_paths():
    """收集可用文档分区来源（飞牛 / 自动）：
       1) TRIM_DATA_SHARE_PATHS（访问权限/共享工作区，冒号分隔）
       2) 本应用 config/resource 中 data-share 声明的共享目录（安装目录 shares/ 下的软链）
       3) 访问权限/手动配置写入的 share_paths 文件（TRIM_PKGVAR / PKGETC / PKGHOME）
       返回 [(显示名, 绝对路径), ...]
    """
    paths = []
    for p in parse_data_share_paths(os.environ.get("TRIM_DATA_SHARE_PATHS", "")):
        paths.append((os.path.basename(p.rstrip("/")) or "共享文件夹", p))
    appdest = os.environ.get("TRIM_APPDEST")
    if appdest:
        shares_dir = os.path.join(appdest, "shares")
        if os.path.isdir(shares_dir):
            for name in sorted(os.listdir(shares_dir)):
                fp = os.path.join(shares_dir, name)
                paths.append((name, fp))
    for base in (os.environ.get("TRIM_PKGVAR"), os.environ.get("TRIM_PKGETC"), os.environ.get("TRIM_PKGHOME")):
        if base:
            for p in read_share_paths_file(os.path.join(base, "share_paths")):
                paths.append((os.path.basename(p.rstrip("/")) or "共享文件夹", p))
    return paths


def guess_mime(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in EXTRA_MIME:
        return EXTRA_MIME[ext]
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"


def is_static_denied(fp):
    """判断静态文件路径是否被禁止公开（源码 / 配置 / 密钥，以及点文件）。"""
    if not fp:
        return True
    base = os.path.basename(fp)
    return (base.startswith(".") or base in STATIC_DENY_NAMES
            or base.endswith(STATIC_DENY_EXTS))


# 公开静态资源**白名单**：只放行应用页面、Vditor 前端与桌面图标。
# 采用白名单而非黑名单——将来若把新文件（配置/密钥/源码）放进应用目录，也不会被意外公开。
PUBLIC_STATIC_EXACT = ("/index.html",)
PUBLIC_STATIC_PREFIX = ("/vditor/", "/ui/")

# ---------- 移动端 App 接口预留（1.1.3） ----------
# 仅占位：约定未来手机端接口统一挂在此前缀下，与现有 /api/ 路由物理隔离。
# **当前没有任何路由挂在此前缀下**，调用一律404 —— 详见 docs/MOBILE_API.md（纯规范，未实现）。
# 之所以先落常量，是为了让后续实现有明确归属，避免直接往现有 /api/ 里塞移动端专用接口。
MOBILE_API_PREFIX = "/api/m/"


def is_public_static(path):
    return path in PUBLIC_STATIC_EXACT or path.startswith(PUBLIC_STATIC_PREFIX)


def safe_join(base, path):
    """防止路径穿越，返回绝对路径或 None（跨平台安全）"""
    path = unquote(path).lstrip("/")
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base_abs, path))
    if target == base_abs or target.startswith(base_abs + os.sep):
        return target
    return None


def parse_multipart(body, boundary):
    """极简 multipart/form-data 解析，兼容无 cgi 模块的 Python 3.13+。

    返回 (files, fields)：
      files  = [(field, filename, content_bytes), ...]
      fields = {name: value_str}   # 非文件字段（如上传时携带的 root 分区参数）
    """
    files = []
    fields = {}
    delim = b"--" + boundary
    parts = body.split(delim)
    for part in parts:
        if part in (b"", b"--", b"\r\n", b"--\r\n"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        idx = part.find(b"\r\n\r\n")
        if idx == -1:
            continue
        header = part[:idx].decode("utf-8", "replace")
        content = part[idx + 4:]
        cd = re.search(r"Content-Disposition:[^\r\n]*", header)
        if not cd:
            continue
        dispos = cd.group(0)
        name_m = re.search(r'name="([^"]*)"', dispos)
        file_m = re.search(r'filename="([^"]*)"', dispos)
        field = name_m.group(1) if name_m else None
        fname = file_m.group(1) if file_m else None
        if fname:
            files.append((field, fname, content))
        elif field:
            fields[field] = content.decode("utf-8", "replace").strip()
    return files, fields


def _version_key(rel):
    """版本目录键：可读前缀 + 相对路径哈希。旧的「用 __ 拼接路径」方案存在歧义碰撞
    （a/b__c.md 与 a__b/c.md 会得到同一个键 → 历史版本互相串用），故加哈希后缀。"""
    rel = rel.replace("\\", "/").lstrip("/")
    stem = os.path.splitext(os.path.basename(rel))[0] or "doc"
    parent = os.path.dirname(rel)
    readable = (parent.replace("/", "__") + "__" + stem) if parent else stem
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
    return "%s--%s" % (readable[:60], digest)


def _legacy_version_key(rel):
    """1.1.1 之前的键编码（有碰撞风险），仅用于发现并迁移旧目录。"""
    rel = rel.replace("\\", "/").lstrip("/")
    base = os.path.dirname(rel)
    name = os.path.splitext(os.path.basename(rel))[0]
    return name if not base else (base.replace("/", "__") + "__" + name)


def _folder_note_path(fp):
    """把 <...>/<stem>.md 规范成 <...>/<stem>/<stem>.md（每文档一个同名文件夹）。"""
    d = os.path.dirname(fp)
    stem = os.path.splitext(os.path.basename(fp))[0] or "document"
    return os.path.join(d, stem, stem + ".md")


def _doc_asset_dir(root_path, doc_rel):
    """文档所在目录（上传的图片 / 音频等与文档放在一起）；无目录则用分区根。"""
    d = os.path.dirname((doc_rel or "").replace("\\", "/").lstrip("/"))
    return safe_join(root_path, d) if d else root_path


def _in_doc_folder(base, rel):
    """rel 是否位于某个「文档文件夹」内（该目录下存在同名 .md，即 folder-note 结构）。"""
    parts = rel.split("/")
    for i in range(1, len(parts)):
        anc = "/".join(parts[:i])
        if os.path.isfile(os.path.join(base, anc, os.path.basename(anc) + ".md")):
            return True
    return False
