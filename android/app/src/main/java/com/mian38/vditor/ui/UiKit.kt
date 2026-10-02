package com.mian38.vditor.ui

import android.content.Context
import android.view.View
import android.widget.Toast
import com.mian38.vditor.R
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** 通用 UI 工具：toast、字节数与时间的可读化。 */
object UiKit {

    fun toast(ctx: Context, msg: String) {
        Toast.makeText(ctx, msg, Toast.LENGTH_SHORT).show()
    }

    fun longToast(ctx: Context, msg: String) {
        Toast.makeText(ctx, msg, Toast.LENGTH_LONG).show()
    }

    fun View.visible(show: Boolean) {
        visibility = if (show) View.VISIBLE else View.GONE
    }

    /**
     * 以「类名 + 参数」方式切换显隐的入口。
     *
     * 扩展函数 [visible] 只能用 `view.visible(true)` 调用，而 Activity 里大量是
     * 持有字段再操作（`loadingBox.visible(false)` 尚可，但 `UiKit.setVisible(loadingBox, false)`
     * 这种写法在 Kotlin 里不成立——扩展接收者不进参数表）。这里补一个普通函数，
     * 兼顾「可链式」与「可按字段名传参」两种写法。
     */
    fun setVisible(view: View?, show: Boolean) {
        view?.visibility = if (show) View.VISIBLE else View.GONE
    }

    /** 字节数 → 人类可读。服务端字节口径为 UTF-8。 */
    fun size(bytes: Long): String = when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        bytes < 1024L * 1024 * 1024 -> String.format(Locale.US, "%.1f MB", bytes / 1024.0 / 1024.0)
        else -> String.format(Locale.US, "%.1f GB", bytes / 1024.0 / 1024.0 / 1024.0)
    }

    /**
     * 服务端时间戳（ISO8601 UTC）→ 本地时间显示。
     * 解析失败时原样返回，避免因格式差异显示空白。
     */
    fun isoToLocal(iso: String): String {
        if (iso.isBlank()) return ""
        return try {
            val inFmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
            inFmt.timeZone = TimeZone.getTimeZone("UTC")
            val d: Date = inFmt.parse(iso) ?: return iso
            SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(d)
        } catch (e: Exception) {
            iso
        }
    }

    /** 版本时间戳（毫秒）→ 本地时间显示。 */
    fun millisToLocal(ms: Long): String = try {
        SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date(ms))
    } catch (e: Exception) {
        ms.toString()
    }

    /** 取扩展名（含点），无扩展名时返回空串。 */
    fun extOf(name: String): String {
        val i = name.lastIndexOf('.')
        return if (i > 0) name.substring(i + 1).lowercase(Locale.US) else ""
    }

    fun ctx(ctx: Context) = ctx.applicationContext

    val ctxLoginNeedSetup: Int get() = R.string.login_need_setup
}
