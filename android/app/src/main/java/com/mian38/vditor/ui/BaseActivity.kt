package com.mian38.vditor.ui

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.mian38.vditor.data.Prefs

/**
 * 所有页面的公共基类。
 *
 * 职责：统一注入 [Prefs]、统一处理 token 失效跳登录、统一把网络异常翻译成人话。
 * 子类只需实现 [requireLogin] 来声明「进入本页必须已登录且已配置地址」。
 */
abstract class BaseActivity : AppCompatActivity() {

    protected lateinit var prefs: Prefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        if (requireLogin && !hasSession()) {
            goLogin()
            return
        }
    }

    /** 子类覆盖：本页是否必须已登录。 */
    protected open val requireLogin: Boolean get() = true

    protected fun hasSession(): Boolean =
        com.mian38.vditor.net.ApiClient.token.isNotEmpty() &&
                com.mian38.vditor.net.ApiClient.baseUrl.isNotEmpty()

    /** token 失效/主动退出：统一回登录页并清理栈。 */
    fun goLogin() {
        val i = Intent(this, LoginActivity::class.java)
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        startActivity(i)
        finish()
    }

    /**
     * 统一的失败提示。
     * 网络类异常（重试后仍失败）走 [isNetwork] 分支，给出「检查连接」类文案而非原始异常。
     */
    protected fun fail(msg: String, isNetwork: Boolean = false) {
        val text = if (isNetwork) "$msg\n${getString(com.mian38.vditor.R.string.offline)}" else msg
        UiKit.toast(this, text)
    }

    protected fun failLong(msg: String, isNetwork: Boolean = false) {
        val text = if (isNetwork) "$msg\n${getString(com.mian38.vditor.R.string.offline)}" else msg
        Toast.makeText(this, text, Toast.LENGTH_LONG).show()
    }
}
