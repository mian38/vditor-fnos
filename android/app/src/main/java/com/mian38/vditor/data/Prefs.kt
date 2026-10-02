package com.mian38.vditor.data

import android.content.Context
import android.content.SharedPreferences
import android.content.res.Configuration

/**
 * 本地偏好：记住服务器地址（便于下次快速登录）+ 上次登录成功的凭据线索。
 *
 * 只存**地址**与用户名形态的标识；密码交给系统 Keystore 或不落盘，
 * 默认不开自动登录（安全优先，用户可主动勾选「记住地址」只免去输地址这一步）。
 */
class Prefs(context: Context) {

    private val sp: SharedPreferences =
        context.getSharedPreferences("vditor_prefs", Context.MODE_PRIVATE)

    companion object {
        private const val K_BASE_URL = "base_url"
        private const val K_REMEMBER = "remember_addr"
        private const val K_LAST_ROOT = "last_root_id"
        private const val K_THEME_MODE = "theme_mode"
        private const val K_HISTORY = "addr_history"
    }

    var baseUrl: String
        get() = sp.getString(K_BASE_URL, "") ?: ""
        set(v) = sp.edit().putString(K_BASE_URL, v).apply()

    /** 是否记住地址。默认开启——只免输入，不保存密码。 */
    var rememberAddress: Boolean
        get() = sp.getBoolean(K_REMEMBER, true)
        set(v) = sp.edit().putBoolean(K_REMEMBER, v).apply()

    /** 上次选中的分区 id，登录后直接定位。 */
    var lastRootId: String
        get() = sp.getString(K_LAST_ROOT, "") ?: ""
        set(v) = sp.edit().putString(K_LAST_ROOT, v).apply()

    /** 主题：0=跟随系统，1=浅色，2=深色。 */
    var themeMode: Int
        get() = sp.getInt(K_THEME_MODE, 0)
        set(v) = sp.edit().putInt(K_THEME_MODE, v).apply()

    /** 地址历史（最多 5 条，最近在前），用于登录页快速选择。 */
    fun history(): List<String> =
        (sp.getString(K_HISTORY, "") ?: "").split('\n').filter { it.isNotBlank() }

    fun pushHistory(url: String) {
        if (url.isBlank()) return
        val list = ArrayList(history().filter { it != url })
        list.add(0, url)
        while (list.size > 5) list.removeAt(list.size - 1)
        sp.edit().putString(K_HISTORY, list.joinToString("\n")).apply()
    }

    fun clearAll() {
        sp.edit().remove(K_BASE_URL).remove(K_LAST_ROOT).remove(K_HISTORY).apply()
    }
}

/** 判断当前是否深色模式，供「跟随系统」模式下同步 UI。 */
fun Context.isNightMode(): Boolean =
    (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) ==
            Configuration.UI_MODE_NIGHT_YES