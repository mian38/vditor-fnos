package com.mian38.vditor.net

import android.util.Log
import com.mian38.vditor.data.ApiResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLSession
import java.security.cert.X509Certificate

/**
 * 移动端 API 客户端。
 *
 * 设计约束：
 * - **零第三方网络库**：用系统自带的 HttpURLConnection + org.json，包体最小、无依赖冲突。
 * - **地址两种形态**：局域网「IP:端口」与公网「域名（HTTPS）」统一归一为 baseUrl。
 * - **Token 单独保存**：不与 Web Cookie 混用。
 * - **401 统一上抛**：由上层统一清token 跳登录，不在每个页面各自处理（MOBILE_API.md §5.2）。
 * - **断线重连**：所有请求经 [retryWithBackoff]，网络类异常按指数退避重试。
 */
object ApiClient {

    private const val TAG = "VditorApi"
    private const val CONNECT_TIMEOUT = 8000
    private const val READ_TIMEOUT = 20000
    private const val UPLOAD_TIMEOUT = 60000

    @Volatile
    var baseUrl: String = ""

    @Volatile
    var token: String = ""

    /** 由上层设置：token 失效时的回调（跳登录页）。 */
    @Volatile
    var onUnauthorized: (() -> Unit)? = null

    /**
     * 自签名 / 内网证书的宽松校验。
     *
     * 已知取舍：本地 NAS 常通过自签证书的 HTTPS 暴露，Android 默认会拒绝。
     * 这里放行证书链校验以兼容内网自签场景；**仅适用于用户自建的局域网/私有域名**，
     * 不适用于访问公网不可信站点。若要更严格，可改为「校验失败则拒绝」+ 导入自有 CA。
     *
     * 用 object 表达式而非 SAM 转换：`X509TrustManager` 是 Java 接口，
     * Kotlin 只对 `fun interface` 与部分 Java 接口做 SAM 转换，
     * 这里三个方法都要实现（两个空实现），写成 object 最直白。
     */
    private val allTrust = object : javax.net.ssl.X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }

    private val lenientVerifier = HostnameVerifier { _, _ -> true }

    private fun trustAllForSelfSigned() {
        try {
            val ct = javax.net.ssl.SSLContext.getInstance("TLS")
            ct.init(null, arrayOf(allTrust), java.security.SecureRandom())
            HttpsURLConnection.setDefaultSSLSocketFactory(ct.socketFactory)
            HttpsURLConnection.setDefaultHostnameVerifier(lenientVerifier)
        } catch (e: Exception) {
            Log.w(TAG, "放宽 TLS 校验失败，回退到系统默认", e)
        }
    }

    fun initLenientTls() = trustAllForSelfSigned()

    // ---------------- 地址归一 ----------------

    /**
     * 把用户输入的地址归一为 base URL。
     *
     * 支持：
     * - `192.168.1.10:9000`（局域网 IP:端口）→ `http://192.168.1.10:9000`
     * - `10.0.0.5`（无端口）→ `http://10.0.0.5:9000`（补默认端口）
     * - `vditor.example.com`（公网域名）→ `https://vditor.example.com`
     * - 带 scheme / 带路径的完整 URL → 原样使用
     */
    fun normalizeBase(input: String): String {
        var s = input.trim().replace("，", ",")
        if (s.isEmpty()) return ""
        s = s.replace(Regex("^/+|/+$"), "")
        val hasScheme = s.startsWith("http://", true) || s.startsWith("https://", true)
        if (!hasScheme) s = "http://$s"
        // 补默认端口：局域网 IP 未指定端口时用 9000（服务端默认）
        val m = Regex("^(https?)://([^/:]+)$").find(s)
        if (m != null) s = "${m.groupValues[1]}://${m.groupValues[2]}:9000"
        return s
    }

    fun isLanHost(base: String): Boolean {
        val m = Regex("^https?://([^/:]+)").find(base) ?: return false
        val h = m.groupValues[1]
        return h.startsWith("192.168.") || h.startsWith("10.") || h.startsWith("172.") ||
                h == "localhost" || h.startsWith("127.") || h.endsWith(".local") ||
                h.contains(":")   // IPv6
    }

    // ---------------- 请求执行（含重试） ----------------

    private class NetException(msg: String, cause: Throwable? = null) : Exception(msg, cause)

    /**
     * 带指数退避的重试。
     *
     * 只对**网络类瞬时故障**（连接超时、连接重置、IOException）重试；
     * 4xx 这类确定性失败不重试，否则会放大无效请求并拖慢界面反馈。
     */
    private suspend fun <T> retryWithBackoff(
        maxAttempts: Int = 3,
        initialDelayMs: Long = 600,
        block: suspend () -> T
    ): T {
        var delay = initialDelayMs
        var last: Exception? = null
        for (i in 1..maxAttempts) {
            try {
                return block()
            } catch (e: NetException) {
                last = e
                if (i == maxAttempts) break
                Log.w(TAG, "第 $i 次请求失败，${delay}ms 后重试：${e.message}")
                kotlinx.coroutines.delay(delay)
                delay *= 2
            }
        }
        throw last ?: NetException("请求失败")
    }

    private fun conn(path: String, method: String): HttpURLConnection {
        if (baseUrl.isEmpty()) throw NetException("未配置服务器地址")
        val url = URL(baseUrl + path)
        val c = url.openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = CONNECT_TIMEOUT
        c.readTimeout = if (method == "POST" && path.endsWith("/upload")) UPLOAD_TIMEOUT else READ_TIMEOUT
        c.instanceFollowRedirects = true
        c.setRequestProperty("Accept", "application/json")
        if (token.isNotEmpty()) c.setRequestProperty("Authorization", "Bearer $token")
        return c
    }

    private fun readAll(ins: InputStream?): String {
        if (ins == null) return ""
        return BufferedInputStream(ins).use { bis ->
            val buf = ByteArrayOutputStream()
            val b = ByteArray(8192)
            while (true) {
                val n = bis.read(b)
                if (n < 0) break
                buf.write(b, 0, n)
            }
            buf.toString("UTF-8")
        }
    }

    private fun parse(text: String, code: Int): ApiResult {
        val json = try {
            JSONObject(text)
        } catch (e: Exception) {
            Log.w(TAG, "响应非JSON（HTTP $code）：${text.take(160)}")
            return ApiResult(false, null, "SERVER_ERROR", "服务端返回异常（HTTP $code）", code)
        }
        val r = ApiResult.of(json, code)
        if (r.error == "INVALID_TOKEN") {
            // token 失效：通知上层统一跳登录（不在各页面重复处理）
            token = ""
            onUnauthorized?.invoke()
        }
        return r
    }

    private suspend fun request(
        method: String, path: String, body: JSONObject? = null
    ): ApiResult = withContext(Dispatchers.IO) {
        retryWithBackoff {
            var c: HttpURLConnection? = null
            try {
                c = conn(path, method)
                if (body != null) {
                    c.doOutput = true
                    c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                }
                val code = try {
                    c.responseCode
                } catch (e: Exception) {
                    throw NetException("无法连接服务器（${baseUrl}）", e)
                }
                val text = if (code in 200..299) readAll(c.inputStream) else readAll(c.errorStream)
                parse(text, code)
            } catch (e: NetException) {
                throw e
            } catch (e: Exception) {
                throw NetException("网络异常：${e.message}", e)
            } finally {
                c?.disconnect()
            }
        }
    }

    // ---------------- 接口方法 ----------------

    suspend fun health(): ApiResult = request("GET", "/api/m/health")

    suspend fun login(password: String): ApiResult =
        request("POST", "/api/m/auth/login", JSONObject().put("password", password))

    suspend fun logout(): ApiResult = request("POST", "/api/m/auth/logout")

    suspend fun session(): ApiResult = request("GET", "/api/m/auth/session")

    suspend fun roots(): ApiResult = request("GET", "/api/m/roots")

    suspend fun files(root: String, path: String = ""): ApiResult =
        request("GET", "/api/m/files?root=${enc(root)}${if (path.isEmpty()) "" else "&path=${enc(path)}"}")

    suspend fun file(root: String, path: String): ApiResult =
        request("GET", "/api/m/file?root=${enc(root)}&path=${enc(path)}")

    suspend fun createFile(root: String, path: String, content: String): ApiResult =
        request("POST", "/api/m/file",
            JSONObject().put("root", root).put("path", path).put("content", content))

    suspend fun saveFile(root: String, path: String, content: String, ifVersion: Int? = null): ApiResult {
        val b = JSONObject().put("root", root).put("path", path).put("content", content)
        if (ifVersion != null) b.put("if_version", ifVersion)
        return request("PUT", "/api/m/file", b)
    }

    suspend fun deleteFile(root: String, path: String): ApiResult =
        request("DELETE", "/api/m/file", JSONObject().put("root", root).put("path", path))

    suspend fun versions(root: String, path: String): ApiResult =
        request("GET", "/api/m/file/versions?root=${enc(root)}&path=${enc(path)}")

    suspend fun restore(root: String, path: String, version: Long): ApiResult =
        request("POST", "/api/m/file/versions/restore",
            JSONObject().put("root", root).put("path", path).put("version", version))

    suspend fun assets(root: String, path: String): ApiResult =
        request("POST", "/api/m/file/assets", JSONObject().put("root", root).put("path", path))

    suspend fun uploadLimits(): ApiResult = request("GET", "/api/m/settings/upload")

    /** 附件上传：单请求直传（分片断点续传待定，见 MOBILE_API.md §6.2）。 */
    suspend fun upload(
        root: String, docPath: String, fileName: String, mime: String, bytes: ByteArray
    ): ApiResult = withContext(Dispatchers.IO) {
        retryWithBackoff(maxAttempts = 1) {     // 上传不自动重试，避免重复写入
            val boundary = "----vditor" + UUID.randomUUID().toString().replace("-", "")
            var c: HttpURLConnection? = null
            try {
                c = conn("/api/m/upload", "POST")
                c.doOutput = true
                c.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
                DataOutputStream(c.outputStream).use { out ->
                    fun field(k: String, v: String) {
                        out.writeBytes("--$boundary\r\n")
                        out.writeBytes("Content-Disposition: form-data; name=\"$k\"\r\n\r\n")
                        out.write(v.toByteArray(Charsets.UTF_8))
                        out.writeBytes("\r\n")
                    }
                    field("root", root)
                    if (docPath.isNotEmpty()) field("path", docPath)
                    out.writeBytes("--$boundary\r\n")
                    out.writeBytes(
                        "Content-Disposition: form-data; name=\"file\"; filename=\"$fileName\"\r\n"
                    )
                    out.writeBytes("Content-Type: $mime\r\n\r\n")
                    out.write(bytes)
                    out.writeBytes("\r\n--$boundary--\r\n")
                }
                val code = try { c.responseCode } catch (e: Exception) {
                    throw NetException("上传失败：无法连接服务器", e)
                }
                val text = if (code in 200..299) readAll(c.inputStream) else readAll(c.errorStream)
                parse(text, code)
            } catch (e: NetException) {
                throw e
            } catch (e: Exception) {
                throw NetException("上传异常：${e.message}", e)
            } finally {
                c?.disconnect()
            }
        }
    }

    private fun enc(v: String): String = URLEncoder.encode(v, "UTF-8")
}