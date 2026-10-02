"""移动端 API（/api/m/）的实现体。

设计要点（与 MOBILE_API.md 规范对齐）：

* **统一响应包**：`{"ok": bool, "data": ..., "error": code, "message": 中文}`。
  客户端应以 `ok` 判定成败，而非依赖 HTTP 状态码单独判断。
* **鉴权**：Bearer Token（`Authorization: Bearer <token>`），与 Web 端Cookie 会话**物理隔离**，
  便于按客户端维度限流与吊销。Token 与会话同寿命（空闲 30 分钟 / 绝对 8 小时）。
* **复用既有能力**：路径安全走 `safe_join`、文档/附件结构走 `_doc_asset_dir`、
  上传校验走 `is_denied_upload` + `upload_headers`——**不另写一套**。
* **错误码**：见 `ERROR_HTTP` 映射，机器可读码 + 中文提示成对出现。

本模块只提供**纯逻辑**（响应包构造、参数校验、错误码映射）；
真正的路由分发与 IO 调用由 `server.py` 的 `Handler._m_get/_m_post/_m_put/_m_delete` 完成。
"""

import hashlib
import time

API_VERSION = "m1"
APP_ID = "com.mian38.vditor"

# 统一错误码 → HTTP 状态码。规范见 MOBILE_API.md §1.3。
ERROR_HTTP = {
    "INVALID_TOKEN": 401,
    "NEED_SETUP": 428,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "DENIED_EXT": 400,
    "TOO_LARGE": 413,
    "RATE_LIMITED": 429,
    "BAD_REQUEST": 400,
    "CONFLICT": 409,
    "SERVER_ERROR": 500,
    # API 数据输出开关关闭时的专用码（403：鉴权已过，但策略不允许输出数据）。
    # 与 FORBIDDEN 区分开，便于客户端判断「是权限不足」还是「开关没开」。
    "API_OUTPUT_DISABLED": 403,
}

# 错误码 → 面向用户的中文提示。客户端可直接展示 message。
ERROR_MESSAGE = {
    "INVALID_TOKEN": "登录已失效，请重新登录",
    "NEED_SETUP": "应用尚未完成首次设置密码，请先在浏览器端完成初始设置",
    "FORBIDDEN": "没有权限执行该操作",
    "NOT_FOUND": "请求的内容不存在",
    "DENIED_EXT": "该文件类型不允许上传",
    "TOO_LARGE": "文件超过大小上限",
    "RATE_LIMITED": "请求过于频繁，请稍后重试",
    "BAD_REQUEST": "请求参数有误",
    "CONFLICT": "内容已存在",
    "SERVER_ERROR": "服务端异常，请稍后重试",
    "API_OUTPUT_DISABLED": "API 数据输出已关闭：请在「设置 → 开发者选项」中开启「API 接口对外输出数据」后再试（该开关仅用于开发调试）",
}


def ok(data=None):
    """成功响应包。"""
    return {"ok": True, "data": data if data is not None else {}, "error": "", "message": ""}


def fail(code, message=None, http=None):
    """失败响应包。

    `code` 必须是 ERROR_HTTP 中的键；未登记的码统一降级为 SERVER_ERROR，
    避免客户端遇到不认识的错误码而无法分支处理。
    """
    if code not in ERROR_HTTP:
        code = "SERVER_ERROR"
    return {
        "ok": False,
        "data": None,
        "error": code,
        "message": message or ERROR_MESSAGE.get(code, ""),
        "_http": http or ERROR_HTTP[code],
    }


def http_status(resp):
    """从响应包取出应回的 HTTP 状态码。"""
    return int(resp.get("_http", 200))


def strip_internal(resp):
    """对外输出前剥掉内部字段 `_http`。"""
    return {k: v for k, v in resp.items() if not k.startswith("_")}


def iso(ts):
    """Unix 时间戳 → ISO 8601 UTC（规范要求的时间格式）。"""
    if not ts:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))


# ---------------- 参数校验（统一返回 None 表示非法） ----------------

def take_str(obj, key, required=True, default="", maxlen=4096):
    """取字符串字段：非字符串一律视为非法（不静默强转，避免脏数据写入）。"""
    v = obj.get(key)
    if v is None:
        if required:
            return None
        return default
    if not isinstance(v, str):
        return None
    if len(v) > maxlen:
        return None
    return v


def take_int(obj, key, default, lo, hi):
    """取整数字段并夹到 [lo, hi]。非法值回落默认，避免越界参数打穿服务。"""
    v = obj.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def take_paging(qs, default_limit=200, max_limit=1000):
    """解析分页参数 limit/offset（规范 §4.2）。非法值回落默认而非报错。"""
    def _num(name, default, lo, hi):
        raw = (qs.get(name) or [None])[0]
        if raw is None or raw == "":
            return default
        try:
            n = int(raw)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, n))

    return _num("limit", default_limit, 1, max_limit), _num("offset", 0, 0, 10 ** 9)


def doc_id(rel):
    """文档稳定 id：取相对路径的 sha1 前 8 位。

    只用于客户端做乐观锁/去重，不承担安全职责（安全校验一律走服务端 safe_join）。
    """
    return hashlib.sha1((rel or "").encode("utf-8")).hexdigest()[:8]