package com.mian38.vditor.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.mian38.vditor.R
import com.mian38.vditor.data.FileItem

/**
 * 文件列表适配器。
 *
 * 无障碍：条目整体可读（图标 importantForAccessibility=no，由行文本承载语义），
 * 「更多」按钮单独设contentDescription 并带上文件名，读屏能区分不同条目。
 */
class FileAdapter(
    private val onOpen: (FileItem) -> Unit,
    private val onMore: (FileItem, View) -> Unit
) : RecyclerView.Adapter<FileAdapter.VH>() {

    private val items = ArrayList<FileItem>()

    fun submit(list: List<FileItem>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_file, parent, false)
        return VH(v)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(items[position])
    }

    override fun getItemCount(): Int = items.size

    inner class VH(view: View) : RecyclerView.ViewHolder(view) {
        private val iv: ImageView = view.findViewById(R.id.ivIcon)
        private val tvName: TextView = view.findViewById(R.id.tvName)
        private val tvMeta: TextView = view.findViewById(R.id.tvMeta)
        private val btnMore: MaterialButton = view.findViewById(R.id.btnMore)

        fun bind(item: FileItem) {
            val ctx = itemView.context
            tvName.text = item.name
            iv.setImageResource(if (item.isDir) R.drawable.ic_folder else R.drawable.ic_file)

            tvMeta.text = if (item.isDir) {
                ctx.getString(R.string.meta_folder)
            } else {
                val size = UiKit.size(item.size)
                val time = UiKit.isoToLocal(item.updatedAt)
                if (time.isEmpty()) size else "$size · $time"
            }

            // 整行可点= 打开；长按与「更多」= 菜单
            itemView.setOnClickListener { onOpen(item) }
            itemView.setOnLongClickListener { onMore(item, btnMore); true }

            btnMore.contentDescription =
                ctx.getString(R.string.more_of, item.name)
            btnMore.setOnClickListener { onMore(item, btnMore) }

            // 目录不提供「历史版本/删除」等文档专属操作，故隐藏更多按钮
            btnMore.visibility = if (item.isDir) View.GONE else View.VISIBLE
        }
    }
}
