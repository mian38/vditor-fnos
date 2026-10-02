package com.mian38.vditor.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.mian38.vditor.R
import com.mian38.vditor.data.VersionItem
import com.mian38.vditor.net.ApiClient
import kotlinx.coroutines.launch
import org.json.JSONObject

/** 历史版本列表与回滚。回滚由服务端负责（当前内容会先存为新版本，不会丢）。 */
class VersionsActivity : BaseActivity() {

    companion object {
        const val EXTRA_ROOT = "root"
        const val EXTRA_PATH = "path"
        const val EXTRA_NAME = "name"
    }

    private lateinit var toolbar: MaterialToolbar
    private lateinit var swipe: SwipeRefreshLayout
    private lateinit var list: RecyclerView
    private lateinit var emptyBox: View
    private lateinit var errorBox: View
    private lateinit var tvError: TextView
    private lateinit var adapter: VersionAdapter

    private var rootId: String = ""
    private var docPath: String = ""
    private var docName: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_versions)

        rootId = intent.getStringExtra(EXTRA_ROOT) ?: ""
        docPath = intent.getStringExtra(EXTRA_PATH) ?: ""
        docName = intent.getStringExtra(EXTRA_NAME) ?: ""
        if (rootId.isEmpty() || docPath.isEmpty()) {
            fail(getString(R.string.bad_args)); finish(); return
        }

        toolbar = findViewById(R.id.toolbar)
        swipe = findViewById(R.id.swipe)
        list = findViewById(R.id.list)
        emptyBox = findViewById(R.id.emptyBox)
        errorBox = findViewById(R.id.errorBox)
        tvError = findViewById(R.id.tvError)

        toolbar.title = getString(R.string.versions_of, docName)
        toolbar.setNavigationOnClickListener { finish() }

        list.layoutManager = LinearLayoutManager(this)
        adapter = VersionAdapter(::confirmRestore)
        list.adapter = adapter

        swipe.setOnRefreshListener { load() }
        findViewById<View>(R.id.btnRetry).setOnClickListener { load() }
        ApiClient.onUnauthorized = { goLogin() }
        load()
    }

    override fun onDestroy() {
        ApiClient.onUnauthorized = null
        super.onDestroy()
    }

    private fun showState(state: String, err: String = "") {
        UiKit.setVisible(errorBox, state == "error")
        UiKit.setVisible(emptyBox, state == "empty")
        UiKit.setVisible(list, state == "content")
        swipe.isRefreshing = false
        if (state == "error") tvError.text = err
    }

    private fun load() {
        lifecycleScope.launch {
            try {
                val r = ApiClient.versions(rootId, docPath)
                if (!r.ok) {
                    showState("error", r.message.ifEmpty { getString(R.string.load_failed) })
                    return@launch
                }
                val arr = r.data?.optJSONArray("versions")
                val items = ArrayList<VersionItem>()
                if (arr != null) for (i in 0 until arr.length()) {
                    arr.optJSONObject(i)?.let { items.add(VersionItem.from(it)) }
                }
                adapter.submit(items)
                showState(if (items.isEmpty()) "empty" else "content")
            } catch (e: Exception) {
                showState("error", getString(R.string.load_failed) + "\n" + (e.message ?: ""))
            }
        }
    }

    private fun confirmRestore(v: VersionItem) {
        AlertDialog.Builder(this)
            .setTitle(R.string.restore)
            .setMessage(getString(R.string.restore_confirm_at, UiKit.millisToLocal(v.version)))
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.restore) { _, _ -> doRestore(v) }
            .show()
    }

    private fun doRestore(v: VersionItem) {
        lifecycleScope.launch {
            try {
                val r = ApiClient.restore(rootId, docPath, v.version)
                if (r.ok) {
                    UiKit.toast(this@VersionsActivity, getString(R.string.restored))
                    load()
                } else {
                    fail(r.message.ifEmpty { getString(R.string.op_failed) })
                }
            } catch (e: Exception) {
                fail(e.message ?: getString(R.string.op_failed), isNetwork = true)
            }
        }
    }
}

/** 版本列表适配器。 */
class VersionAdapter(
    private val onRestore: (VersionItem) -> Unit
) : RecyclerView.Adapter<VersionAdapter.VH>() {

    private val items = ArrayList<VersionItem>()

    fun submit(list: List<VersionItem>) {
        items.clear(); items.addAll(list); notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) = VH(
        LayoutInflater.from(parent.context).inflate(R.layout.item_version, parent, false)
    )

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(items[position])
    override fun getItemCount(): Int = items.size

    inner class VH(view: View) : RecyclerView.ViewHolder(view) {
        private val iv: ImageView = view.findViewById(R.id.ivIcon)
        private val tvTitle: TextView = view.findViewById(R.id.tvTitle)
        private val tvMeta: TextView = view.findViewById(R.id.tvMeta)
        private val btn: MaterialButton = view.findViewById(R.id.btnRestore)

        fun bind(v: VersionItem) {
            val ctx = itemView.context
            val t = UiKit.millisToLocal(v.version)
            tvTitle.text = t
            val src = if (v.source.isNotEmpty()) v.source else "auto"
            tvMeta.text = "${UiKit.size(v.size)} · $src"
            iv.setImageResource(R.drawable.ic_restore)
            btn.setOnClickListener { onRestore(v) }
            itemView.setOnClickListener { onRestore(v) }
            // 读屏时把时间与操作合成一句完整的话
            btn.contentDescription =
                ctx.getString(R.string.restore_at, t)
        }
    }
}
