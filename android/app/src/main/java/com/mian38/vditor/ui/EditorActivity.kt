package com.mian38.vditor.ui

import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.mian38.vditor.R
import com.mian38.vditor.data.Asset
import com.mian38.vditor.data.DocDetail
import com.mian38.vditor.data.UploadLimits
import com.mian38.vditor.net.ApiClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayOutputStream

/**
 * Markdown 编辑页。
 *
 * 关键设计：
 * - **乐观锁**：加载时记录服务端 version，保存时带`if_version`；
 *   若他人已改，服务端返回 FORBIDDEN，本地不覆盖而是提示重新加载。
 * - **自动保存**：停止输入 1.2s 后静默保存，用户无需手动点；顶栏仍有「保存」可强制触发。
 * - **离开确认**：有未保存改动时返回会二次确认。
 */
class EditorActivity : BaseActivity() {

    companion object {
        const val EXTRA_ROOT = "root"
        const val EXTRA_PATH = "path"
        const val EXTRA_NAME = "name"
        private const val AUTOSAVE_DELAY_MS = 1200L
    }

    private lateinit var toolbar: MaterialToolbar
    private lateinit var et: EditText
    private lateinit var tvStatus: TextView
    private lateinit var loadingBox: View

    private var rootId: String = ""
    private var docPath: String = ""
    private var docName: String = ""
    private var serverVersion: Int = 1
    private var assets: List<Asset> = emptyList()

    /** 是否有未保存改动。 */
    private var dirty = false
    private var saving = false
    private var loaded = false
    /** 附件返回后要插入的引用文本。 */
    private var pendingInsert: String = ""

    //系统文件选择器：Android 5.0+ 的 ACTION_OPEN_DOCUMENT，兼容各厂商
    private val pickFile = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) readAndUpload(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_editor)

        rootId = intent.getStringExtra(EXTRA_ROOT) ?: ""
        docPath = intent.getStringExtra(EXTRA_PATH) ?: ""
        docName = intent.getStringExtra(EXTRA_NAME) ?: docPath.substringAfterLast('/')
        if (rootId.isEmpty() || docPath.isEmpty()) {
            fail(getString(R.string.bad_args)); finish(); return
        }

        toolbar = findViewById(R.id.toolbar)
        et = findViewById(R.id.etContent)
        tvStatus = findViewById(R.id.tvStatus)
        loadingBox = findViewById(R.id.loadingBox)

        toolbar.title = docName
        toolbar.setNavigationOnClickListener { confirmExit() }
        toolbar.inflateMenu(R.menu.editor)
        toolbar.setOnMenuItemClickListener { m ->
            when (m.itemId) {
                R.id.action_save -> { save(manual = true); true }
                R.id.action_history -> { openVersions(); true }
                R.id.action_upload -> { pickUpload(); true }
                R.id.action_delete -> { confirmDelete(); true }
                else -> false
            }
        }

        findViewById<View>(R.id.btnAssets).setOnClickListener { showAssets() }

        et.doAfterTextChanged {
            if (!loaded) return@doAfterTextChanged
            dirty = true
            setStatus(getString(R.string.unsaved_changes))
            scheduleAutosave()
        }

        ApiClient.onUnauthorized = { goLogin() }
        load()
    }

    override fun onDestroy() {
        ApiClient.onUnauthorized = null
        super.onDestroy()
    }

    // ---------------- 加载 ----------------

    private fun load() {
        UiKit.setVisible(loadingBox, true)
        lifecycleScope.launch {
            try {
                val r = ApiClient.file(rootId, docPath)
                UiKit.setVisible(loadingBox, false)
                if (!r.ok) {
                    fail(r.message.ifEmpty { getString(R.string.load_failed) }, isNetwork = true)
                    finish(); return@launch
                }
                val d = DocDetail.from(r.data ?: JSONObject())
                serverVersion = d.version
                assets = d.assets
                et.setText(d.content)
                et.setSelection(et.text.length)
                loaded = true
                dirty = false
                setStatus(getString(R.string.saved_at, UiKit.isoToLocal(d.updatedAt)))
            } catch (e: Exception) {
                UiKit.setVisible(loadingBox, false)
                fail(e.message ?: getString(R.string.load_failed), isNetwork = true)
                finish()
            }
        }
    }

    private fun setStatus(s: String) { tvStatus.text = s }

    // ---------------- 自动保存 ----------------

    private var autosaveJob: kotlinx.coroutines.Job? = null

    private fun scheduleAutosave() {
        autosaveJob?.cancel()
        autosaveJob = lifecycleScope.launch {
            kotlinx.coroutines.delay(AUTOSAVE_DELAY_MS)
            if (dirty) save(manual = false)
        }
    }

    private fun save(manual: Boolean) {
        if (!loaded || saving) return
        if (!dirty && !manual) return
        autosaveJob?.cancel()
        val content = et.text?.toString().orEmpty()
        saving = true
        if (manual) setStatus(getString(R.string.saving))
        lifecycleScope.launch {
            try {
                val r = ApiClient.saveFile(rootId, docPath, content, serverVersion)
                saving = false
                if (r.ok) {
                    serverVersion = r.data?.optInt("version", serverVersion + 1) ?: (serverVersion + 1)
                    dirty = false
                    val t = UiKit.isoToLocal(r.data?.optString("updated_at").orEmpty())
                    setStatus(
                        if (t.isEmpty()) getString(R.string.saved)
                        else getString(R.string.saved_at, t)
                    )
                } else if (r.error == "FORBIDDEN") {
                    // 乐观锁冲突：绝不覆盖，交给用户决定
                    setStatus(getString(R.string.save_conflict))
                    showConflict(serverVersion)
                } else {
                    setStatus(getString(R.string.save_failed))
                    fail(r.message.ifEmpty { getString(R.string.save_failed) })
                }
            } catch (e: Exception) {
                saving = false
                setStatus(getString(R.string.save_failed))
                fail(e.message ?: getString(R.string.save_failed), isNetwork = true)
            }
        }
    }

    private fun showConflict(serverNow: Int) {
        val mine = serverVersion
        AlertDialog.Builder(this)
            .setTitle(R.string.conflict_title)
            .setMessage(getString(R.string.conflict_msg, serverNow, mine))
            .setCancelable(false)
            .setNegativeButton(R.string.discard_changes) { _, _ -> finish() }
            .setPositiveButton(R.string.reload) { _, _ ->
                loaded = false
                load()
            }
            .show()
    }

    // ---------------- 附件 ----------------

    private fun showAssets() {
        if (assets.isEmpty()) {
            AlertDialog.Builder(this)
                .setTitle(R.string.assets_title)
                .setMessage(R.string.no_assets)
                .setPositiveButton(android.R.string.ok, null)
                .show()
            return
        }
        val names = assets.map { it.name }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle(R.string.assets_title)
            .setItems(names) { _, which ->
                val a = assets[which]
                pendingInsert = "![](${a.name})"
                insertAtCursor(pendingInsert)
                UiKit.toast(this, getString(R.string.inserted_ref, a.name))
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun pickUpload() {
        try {
            pickFile.launch(arrayOf("*/*"))
        } catch (e: Exception) {
            fail(getString(R.string.no_picker))
        }
    }

    private fun readAndUpload(uri: Uri) {
        lifecycleScope.launch {
            setStatus(getString(R.string.uploading))
            try {
                val res = withContext(Dispatchers.IO) {
                    contentResolver.openInputStream(uri)?.use { ins ->
                        val buf = ByteArrayOutputStream()
                        val b = ByteArray(16384)
                        var total = 0L
                        while (true) {
                            val n = ins.read(b)
                            if (n < 0) break
                            total += n
                            buf.write(b, 0, n)
                        }
                        buf.toByteArray()
                    }
                }
                if (res == null || res.isEmpty()) {
                    setStatus(getString(R.string.save_failed))
                    fail(getString(R.string.read_failed)); return@launch
                }
                val name = queryDisplayName(uri)
                if (name.isEmpty()) {
                    setStatus(getString(R.string.save_failed))
                    fail(getString(R.string.read_failed)); return@launch
                }
                val ext = UiKit.extOf(name)

                // 先取服务端限制：黑名单与体积上限，避免白跑一趟
                val lim = ApiClient.uploadLimits()
                val limits = if (lim.ok) UploadLimits.from(lim.data ?: JSONObject()) else null
                if (limits != null && ext.isNotEmpty() && limits.denyExts.contains(ext)) {
                    setStatus(getString(R.string.save_failed))
                    fail(getString(R.string.asset_denied)); return@launch
                }
                if (limits != null && res.size > limits.maxMb * 1024L * 1024L) {
                    setStatus(getString(R.string.save_failed))
                    fail(getString(R.string.asset_too_large, limits.maxMb)); return@launch
                }

                val r = ApiClient.upload(rootId, docPath, name, guessMime(ext), res)
                if (r.ok) {
                    val insert = r.data?.optString("insert_text").orEmpty()
                        .ifEmpty { "![](${r.data?.optString("name").orEmpty()})" }
                    insertAtCursor(insert)
                    UiKit.toast(this@EditorActivity, getString(R.string.uploaded))
                    setStatus(getString(R.string.unsaved_changes))
                    save(manual = false)
                } else {
                    setStatus(getString(R.string.save_failed))
                    fail(r.message.ifEmpty { getString(R.string.upload_failed) })
                }
            } catch (e: Exception) {
                setStatus(getString(R.string.save_failed))
                fail(e.message ?: getString(R.string.upload_failed), isNetwork = true)
            }
        }
    }

    private fun queryDisplayName(uri: Uri): String {
        return try {
            contentResolver.query(uri, null, null, null, null)?.use { c ->
                val idx = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                if (idx >= 0 && c.moveToFirst()) c.getString(idx) ?: "" else ""
            } ?: ""
        } catch (e: Exception) {
            ""
        }
    }

    private fun guessMime(ext: String): String = when (ext) {
        "png" -> "image/png"; "jpg", "jpeg" -> "image/jpeg"; "gif" -> "image/gif"
        "webp" -> "image/webp"; "svg" -> "image/svg+xml"
        "pdf" -> "application/pdf"; "zip" -> "application/zip"
        "txt", "md" -> "text/plain"; "json" -> "application/json"
        "mp4" -> "video/mp4"; "mp3" -> "audio/mpeg"
        else -> "application/octet-stream"
    }

    private fun insertAtCursor(text: String) {
        val s = et.text ?: return
        val pos = et.selectionStart.coerceIn(0, s.length)
        // 插入前后各补一个换行，避免与正文粘连
        val payload = "\n\n$text\n"
        s.replace(pos, pos, payload)
        dirty = true
        setStatus(getString(R.string.unsaved_changes))
    }

    // ---------------- 导航 ----------------

    private fun openVersions() {
        val i = android.content.Intent(this, VersionsActivity::class.java)
        i.putExtra(VersionsActivity.EXTRA_ROOT, rootId)
        i.putExtra(VersionsActivity.EXTRA_PATH, docPath)
        i.putExtra(VersionsActivity.EXTRA_NAME, docName)
        startActivity(i)
    }

    private fun confirmDelete() {
        AlertDialog.Builder(this)
            .setTitle(R.string.delete)
            .setMessage(getString(R.string.delete_doc_confirm_named, docName))
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.delete) { _, _ ->
                lifecycleScope.launch {
                    try {
                        val r = ApiClient.deleteFile(rootId, docPath)
                        if (r.ok) {
                            UiKit.toast(this@EditorActivity, getString(R.string.deleted))
                            dirty = false
                            finish()
                        } else {
                            fail(r.message.ifEmpty { getString(R.string.op_failed) })
                        }
                    } catch (e: Exception) {
                        fail(e.message ?: getString(R.string.op_failed), isNetwork = true)
                    }
                }
            }
            .show()
    }

    private fun confirmExit() {
        if (!dirty) { finish(); return }
        AlertDialog.Builder(this)
            .setTitle(R.string.unsaved_changes)
            .setMessage(R.string.discard_changes_msg)
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.discard_changes) { _, _ -> finish() }
            .setNeutralButton(R.string.save) { _, _ -> save(manual = true) }
            .show()
    }

    @Deprecated("兼容旧版按键")
    override fun onBackPressed() {
        if (dirty) confirmExit() else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
