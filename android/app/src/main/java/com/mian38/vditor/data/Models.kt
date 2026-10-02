package com.mian38.vditor.data

import org.json.JSONObject

/**
 * 统一响应包：服务端所有 /api/m/ 接口返回 {ok, data, error, message}。
 * 客户端一律以 ok 判定成败，不依赖 HTTP 状态码单独判断（MOBILE_API.md §1.1）。
 */
class ApiResult(val ok: Boolean,
                 val data: JSONObject?,
                 val error: String,
                 val message: String,
                 val httpCode: Int) {
    companion object {
        fun of(json: JSONObject, httpCode: Int): ApiResult =
            ApiResult(
                json.optBoolean("ok", false),
                if (json.isNull("data")) null else json.optJSONObject("data"),
                json.optString("error", ""),
                json.optString("message", ""),
                httpCode
            )
    }
}

/** 文档分区。 */
data class Root(val id: String, val name: String, val path: String, val exists: Boolean) {
    companion object {
        fun from(o: JSONObject) = Root(
            o.optString("id"), o.optString("name"), o.optString("path"),
            o.optBoolean("exists", true)
        )
    }
}

/**
 * 列表条目。isDir 为 true 时表示目录（用于进入下一层），其余为文档。
 */
data class FileItem(
    val id: String,
    val name: String,
    val path: String,
    val root: String,
    val size: Long,
    val updatedAt: String,
    val isDir: Boolean,
    val hasVersions: Boolean
) {
    companion object {
        fun from(o: JSONObject) = FileItem(
            o.optString("id"), o.optString("name"), o.optString("path"),
            o.optString("root"), o.optLong("size"), o.optString("updated_at"),
            o.optBoolean("is_dir", false), o.optBoolean("has_versions", false)
        )
    }
}

/** 文档详情。 */
data class DocDetail(
    val id: String,
    val name: String,
    val path: String,
    val root: String,
    val content: String,
    val size: Long,
    val version: Int,
    val updatedAt: String,
    val assets: List<Asset>
) {
    companion object {
        fun from(o: JSONObject): DocDetail {
            val arr = o.optJSONArray("assets")
            val list = ArrayList<Asset>()
            if (arr != null) for (i in 0 until arr.length()) {
                arr.optJSONObject(i)?.let { list.add(Asset.from(it)) }
            }
            return DocDetail(
                o.optString("id"), o.optString("name"), o.optString("path"),
                o.optString("root"), o.optString("content"), o.optLong("size"),
                o.optInt("version", 1), o.optString("updated_at"), list
            )
        }
    }
}

/** 文档附件。 */
data class Asset(val name: String, val url: String, val size: Long, val ext: String) {
    companion object {
        fun from(o: JSONObject) = Asset(
            o.optString("name"), o.optString("url"),
            o.optLong("size"), o.optString("ext")
        )
    }
}

/** 历史版本条目。version 字段即服务端的毫秒时间戳。 */
data class VersionItem(val version: Long, val createdAt: String, val size: Long, val source: String) {
    companion object {
        fun from(o: JSONObject) = VersionItem(
            o.optLong("version"), o.optString("created_at"),
            o.optLong("size"), o.optString("source")
        )
    }
}

/** 上传限制。 */
data class UploadLimits(val maxMb: Int, val minMb: Int, val maxMbLimit: Int,
                        val denyExts: List<String>, val defaultDenyExts: List<String>) {
    companion object {
        private fun strList(o: JSONObject, key: String): List<String> {
            val a = o.optJSONArray(key) ?: return emptyList()
            val out = ArrayList<String>()
            for (i in 0 until a.length()) out.add(a.optString(i))
            return out
        }

        fun from(o: JSONObject) = UploadLimits(
            o.optInt("max_mb", 256), o.optInt("min_mb", 1), o.optInt("max_mb_limit", 512),
            strList(o, "deny_exts"), strList(o, "default_deny_exts")
        )
    }
}