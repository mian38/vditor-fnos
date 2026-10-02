package com.mian38.vditor.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import com.google.android.material.chip.Chip
import com.mian38.vditor.R
import com.mian38.vditor.data.Prefs
import com.mian38.vditor.net.ApiClient
import kotlinx.coroutines.launch

/**
 * 登录页。
 *
 * 支持两种地址形态（用户要求）：
 * - 局域网「IP:端口」→ 自动补http:// 与默认端口 9000
 * - 公网「域名」→ 自动补 https://
 *
 * 「记住地址」只保存**地址**不保存密码：勾选后下次自动填入地址，
 * 同时把地址写入历史（最多 5 条）以Chip 形式供快速选择。
 */
class LoginActivity : BaseActivity() {

    private lateinit var inputAddr: com.google.android.material.textfield.TextInputEditText
    private lateinit var inputPwd: com.google.android.material.textfield.TextInputEditText
    private lateinit var chkRemember: com.google.android.material.checkbox.MaterialCheckBox
    private lateinit var btnLogin: com.google.android.material.button.MaterialButton
    private lateinit var progress: View
    private lateinit var tvError: TextView
    private lateinit var historyBox: View
    private lateinit var historyChips: com.google.android.material.chip.ChipGroup

    override val requireLogin: Boolean get() = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)
        ApiClient.initLenientTls()

        inputAddr = findViewById(R.id.inputAddr)
        inputPwd = findViewById(R.id.inputPwd)
        chkRemember = findViewById(R.id.chkRemember)
        btnLogin = findViewById(R.id.btnLogin)
        progress = findViewById(R.id.progress)
        tvError = findViewById(R.id.tvError)
        historyBox = findViewById(R.id.historyBox)
        historyChips = findViewById(R.id.historyChips)

        chkRemember.isChecked = prefs.rememberAddress
        if (prefs.rememberAddress && prefs.baseUrl.isNotEmpty()) {
            inputAddr.setText(prefs.baseUrl)
        }
        renderHistory()

        btnLogin.setOnClickListener { submit() }
        // 密码框「回车/搜索键」直接登录
        inputPwd.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_GO || actionId == EditorInfo.IME_ACTION_DONE) {
                submit(); true
            } else false
        }
    }

    private fun renderHistory() {
        val list = prefs.history()
        historyChips.removeAllViews()
        if (list.isEmpty()) {
            UiKit.setVisible(historyBox, false)
            return
        }
        for (url in list) {
            val chip = Chip(this)
            chip.text = url
            chip.isCheckable = false
            chip.isClickable = true
            chip.contentDescription = getString(R.string.login_use_addr, url)
            chip.setOnClickListener {
                inputAddr.setText(url)
                inputPwd.requestFocus()
            }
            historyChips.addView(chip)
        }
        UiKit.setVisible(historyBox, true)
    }

    private fun busy(on: Boolean) {
        progress.visibility = if (on) View.VISIBLE else View.GONE
        btnLogin.isEnabled = !on
        inputAddr.isEnabled = !on
        inputPwd.isEnabled = !on
    }

    private fun showError(msg: String?) {
        if (msg.isNullOrBlank()) {
            tvError.visibility = View.GONE
        } else {
            tvError.text = msg
            tvError.visibility = View.VISIBLE
        }
    }

    private fun submit() {
        showError(null)
        val raw = inputAddr.text?.toString()?.trim().orEmpty()
        if (raw.isEmpty()) {
            showError(getString(R.string.login_addr_required))
            return
        }
        val base = ApiClient.normalizeBase(raw)
        if (base.isEmpty()) {
            showError(getString(R.string.login_addr_bad))
            return
        }
        val pwd = inputPwd.text?.toString().orEmpty()
        if (pwd.isEmpty()) {
            showError(getString(R.string.login_pwd_required))
            return
        }

        busy(true)
        // 先把地址写入全局，health/login 都要用
        ApiClient.baseUrl = base
        lifecycleScope.launch {
            try {
                // 先探活：区分「连不上」与「密码错」，给出可操作的提示
                val h = ApiClient.health()
                if (!h.ok) {
                    busy(false)
                    showError(
                        if (h.error == "NEED_SETUP") getString(R.string.login_need_setup)
                        else "${h.message.ifEmpty { getString(R.string.login_unreachable) }}"
                    )
                    ApiClient.baseUrl = ""
                    return@launch
                }
                val r = ApiClient.login(pwd)
                busy(false)
                if (r.ok) {
                    val tok = r.data?.optString("token").orEmpty()
                    if (tok.isEmpty()) {
                        showError(getString(R.string.login_bad_token))
                        return@launch
                    }
                    ApiClient.token = tok
                    if (chkRemember.isChecked) {
                        prefs.rememberAddress = true
                        prefs.baseUrl = base
                        prefs.pushHistory(base)
                    } else {
                        prefs.rememberAddress = false
                        prefs.clearAll()
                    }
                    UiKit.toast(this@LoginActivity, getString(R.string.login_ok))
                    startActivity(Intent(this@LoginActivity, FilesActivity::class.java))
                    finish()
                } else {
                    ApiClient.token = ""
                    ApiClient.baseUrl = ""
                    showError(r.message.ifEmpty { getString(R.string.login_failed) })
                }
            } catch (e: Exception) {
                busy(false)
                ApiClient.baseUrl = ""
                showError(
                    getString(R.string.login_unreachable) + "\n" +
                            (e.message ?: "")
                )
            }
        }
    }
}
