package com.mian38.vditor.ui

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.widget.PopupMenu
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.floatingactionbutton.FloatingActionButton
import com.mian38.vditor.R
import com.mian38.vditor.data.FileItem
import com.mian38.vditor.data.Root
import com.mian38.vditor.net.ApiClient
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * 文档列表页（对应 Web 端左侧文件树 + 列表）。
 *
 * 状态机：loading / content / empty / error 四态互斥切换，
 * 断线时进入 error 态并提供「重试」；下拉刷新与重试走同一条 load()。
 */
class FilesActivity : BaseActivity() {

    private lateinit var toolbar: MaterialToolbar
    private lateinit var swipe: SwipeRefreshLayout
    private lateinit var list: RecyclerView
    private lateinit var emptyBox: View
    private lateinit var loadingBox: View
    private lateinit var errorBox: View
    private lateinit var tvError: TextView
    private lateinit var fab: FloatingActionButton

    private lateinit var adapter: FileAdapter

    /** 当前分区 id；空串表示尚未加载分区列表。 */
    private var rootId: String = ""
    private var rootName: String = ""
    /** 当前所在子目录（相对分区根），空串为根层。 */
    private var subPath: String = ""

    /** 面包屑栈，用于逐级返回。 */
    private val pathStack = ArrayList<String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_files)

        toolbar = findViewById(R.id.toolbar)
        swipe = findViewById(R.id.swipe)
        list = findViewById(R.id.list)
        emptyBox = findViewById(R.id.emptyBox)
        loadingBox = findViewById(R.id.loadingBox)
        errorBox = findViewById(R.id.errorBox)
        tvError = findViewById(R.id.tvError)
        fab = findViewById(R.id.fab)

        list.layoutManager = LinearLayoutManager(this)
        adapter = FileAdapter(onOpen = ::onItemOpen, onMore = ::showItemMenu)
        list.adapter = adapter

        toolbar.inflateMenu(R.menu.files)
        toolbar.setOnMenuItemClickListener { m ->
            when (m.itemId) {
                R.id.action_refresh -> { load(showLoading = false); true }
                R.id.action_logout -> { confirmLogout(); true }
                else -> false
            }
        }

        swipe.setOnRefreshListener { load(showLoading = false) }
        findViewById<View>(R.id.btnRetry).setOnClickListener { load(showLoading = true) }
        fab.setOnClickListener { promptNewDoc() }

        // token 失效统一跳登录
        ApiClient.onUnauthorized = { goLogin() }

        loadRoots()
    }

    override fun onDestroy() {
        ApiClient.onUnauthorized = null
        super.onDestroy()
    }

    // ---------------- 状态机 ----------------

    private fun showState(state: String, errMsg: String = "") {
        UiKit.setVisible(loadingBox, state == "loading")
        UiKit.setVisible(errorBox, state == "error")
        UiKit.setVisible(emptyBox, state == "empty")
        UiKit.setVisible(list, state == "content")
        UiKit.setVisible(fab, state != "loading")
        swipe.isRefreshing = false
        if (state == "error") tvError.text = errMsg
    }

    // ---------------- 分区 ----------------

    private fun loadRoots() {
        showState("loading")
        lifecycleScope.launch {
            try {
                val r = ApiClient.roots()
                if (!r.ok) {
                    showState("error", r.message.ifEmpty { getString(R.string.load_failed) })
                    return@launch
                }
                val arr = r.data?.optJSONArray("roots")
                val roots = ArrayList<Root>()
                if (arr != null) for (i in 0 until arr.length()) {
                    arr.optJSONObject(i)?.let { roots.add(Root.from(it)) }
                }
                if (roots.isEmpty()) {
                    showState("error", getString(R.string.no_roots))
                    return@launch
                }
                // 优先回到上次使用的分区
                val last = prefs.lastRootId
                val pick = roots.firstOrNull { it.id == last } ?: roots.first()
                rootId = pick.id
                rootName = pick.name
                load(showLoading = true)
            } catch (e: Exception) {
                showState("error", getString(R.string.load_failed) + "\n" + (e.message ?: ""))
            }
        }
    }

    private fun switchRootDialog() {
        lifecycleScope.launch {
            val r = try { ApiClient.roots() } catch (e: Exception) { null }
            val arr = r?.data?.optJSONArray("roots")
            val names = ArrayList<String>()
            val ids = ArrayList<String>()
            if (arr != null) for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                ids.add(o.optString("id"))
                names.add(o.optString("name"))
            }
            if (names.isEmpty()) {
                fail(getString(R.string.load_failed))
                return@launch
            }
            val cur = names.indexOfFirst { it == rootName }.coerceAtLeast(0)
            AlertDialog.Builder(this@FilesActivity)
                .setTitle(R.string.switch_root)
                .setSingleChoiceItems(names.toTypedArray(), cur) { d, which ->
                    rootId = ids[which]
                    rootName = names[which]
                    prefs.lastRootId = rootId
                    subPath = ""
                    pathStack.clear()
                    load(showLoading = true)
                    d.dismiss()
                }
                .setNegativeButton(R.string.cancel, null)
                .show()
        }
    }

    // ---------------- 列表 ----------------

    private fun load(showLoading: Boolean) {
        if (rootId.isEmpty()) return
        if (showLoading) showState("loading")
        else swipe.isRefreshing = true

        lifecycleScope.launch {
            try {
                val r = ApiClient.files(rootId, subPath)
                swipe.isRefreshing = false
                if (!r.ok) {
                    showState("error", r.message.ifEmpty { getString(R.string.load_failed) })
                    return@launch
                }
                val d = r.data ?: JSONObject()
                val arr = d.optJSONArray("items")
                val list2 = ArrayList<FileItem>()
                if (arr != null) for (i in 0 until arr.length()) {
                    arr.optJSONObject(i)?.let { list2.add(FileItem.from(it)) }
                }
                adapter.submit(list2)
                toolbar.subtitle = if (subPath.isEmpty()) rootName else "$rootName / $subPath"
                toolbar.setNavigationOnClickListener {
                    if (subPath.isEmpty()) switchRootDialog() else goUp()
                }
                showState(if (list2.isEmpty()) "empty" else "content")
            } catch (e: Exception) {
                showState("error", getString(R.string.load_failed) + "\n" + (e.message ?: ""))
            }
        }
    }

    private fun goUp() {
        if (pathStack.isEmpty()) return
        pathStack.removeAt(pathStack.size - 1)
        subPath = pathStack.joinToString("/")
        load(showLoading = true)
    }

    @Deprecated("兼容旧版按键")
    override fun onBackPressed() {
        if (subPath.isNotEmpty()) {
            goUp()
            return
        }
        @Suppress("DEPRECATION")
        super.onBackPressed()
    }

    // ---------------- 条目交互 ----------------

    private fun onItemOpen(item: FileItem) {
        if (item.isDir) {
            pathStack.add(item.name)
            subPath = pathStack.joinToString("/")
            load(showLoading = true)
        } else {
            val i = Intent(this, EditorActivity::class.java)
            i.putExtra(EditorActivity.EXTRA_ROOT, item.root)
            i.putExtra(EditorActivity.EXTRA_PATH, item.path)
            i.putExtra(EditorActivity.EXTRA_NAME, item.name)
            startActivity(i)
        }
    }

    private fun showItemMenu(item: FileItem, anchor: View) {
        val pm = PopupMenu(this, anchor)
        pm.inflate(R.menu.item_file)
        pm.menu.findItem(R.id.act_open).setVisible(!item.isDir)
        pm.menu.findItem(R.id.act_history).setVisible(!item.isDir)
        pm.menu.findItem(R.id.act_rename).setVisible(false)   // 服务端暂无重命名接口，避免给出死按钮
        pm.setOnMenuItemClickListener { m ->
            when (m.itemId) {
                R.id.act_open -> { onItemOpen(item); true }
                R.id.act_history -> { openVersions(item); true }
                R.id.act_delete -> { confirmDelete(item); true }
                else -> false
            }
        }
        pm.show()
    }

    private fun openVersions(item: FileItem) {
        val i = Intent(this, VersionsActivity::class.java)
        i.putExtra(VersionsActivity.EXTRA_ROOT, item.root)
        i.putExtra(VersionsActivity.EXTRA_PATH, item.path)
        i.putExtra(VersionsActivity.EXTRA_NAME, item.name)
        startActivity(i)
    }

    private fun confirmDelete(item: FileItem) {
        AlertDialog.Builder(this)
            .setTitle(R.string.delete)
            .setMessage(getString(R.string.delete_doc_confirm_named, item.name))
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.delete) { _, _ -> doDelete(item) }
            .show()
    }

    private fun doDelete(item: FileItem) {
        lifecycleScope.launch {
            try {
                val r = ApiClient.deleteFile(item.root, item.path)
                if (r.ok) {
                    UiKit.toast(this@FilesActivity, getString(R.string.deleted))
                    load(showLoading = false)
                } else {
                    fail(r.message.ifEmpty { getString(R.string.op_failed) })
                }
            } catch (e: Exception) {
                fail(e.message ?: getString(R.string.op_failed), isNetwork = true)
            }
        }
    }

    // ---------------- 新建 ----------------

    private fun promptNewDoc() {
        val et = EditText(this)
        et.hint = getString(R.string.input_name)
        et.setSingleLine()
        val pad = (16 * resources.displayMetrics.density).toInt()
        et.setPadding(pad, pad, pad, pad)
        AlertDialog.Builder(this)
            .setTitle(R.string.new_doc_title)
            .setView(et)
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.create) { _, _ ->
                val name = et.text.toString().trim()
                if (name.isEmpty()) {
                    fail(getString(R.string.name_empty))
                    return@setPositiveButton
                }
                createDoc(name)
            }
            .show()
    }

    private fun createDoc(name: String) {
        val full = if (subPath.isEmpty()) name else "$subPath/$name"
        lifecycleScope.launch {
            try {
                val r = ApiClient.createFile(rootId, full, "")
                if (r.ok) {
                    UiKit.toast(this@FilesActivity, getString(R.string.created))
                    load(showLoading = false)
                } else {
                    fail(
                        if (r.error == "CONFLICT") getString(R.string.name_taken)
                        else r.message.ifEmpty { getString(R.string.op_failed) }
                    )
                }
            } catch (e: Exception) {
                fail(e.message ?: getString(R.string.op_failed), isNetwork = true)
            }
        }
    }

    // ---------------- 退出 ----------------

    private fun confirmLogout() {
        AlertDialog.Builder(this)
            .setTitle(R.string.logout)
            .setMessage(R.string.logout_confirm)
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.logout) { _, _ ->
                lifecycleScope.launch {
                    try { ApiClient.logout() } catch (e: Exception) { /* 忽略：本地照常清 */ }
                    ApiClient.token = ""
                    prefs.clearAll()
                    goLogin()
                }
            }
            .show()
    }
}
