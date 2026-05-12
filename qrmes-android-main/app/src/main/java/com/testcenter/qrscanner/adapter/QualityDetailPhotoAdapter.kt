package com.testcenter.qrscanner.adapter

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import com.bumptech.glide.Glide
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.databinding.ItemQualityDetailPhotoBinding
import com.testcenter.qrscanner.quality.QualityPhotoDto
import com.testcenter.qrscanner.quality.QualityPhotoRequestFactory

class QualityDetailPhotoAdapter(
    private val onPhotoSelected: (QualityPhotoDto) -> Unit
) : RecyclerView.Adapter<QualityDetailPhotoAdapter.ViewHolder>() {

    private var items: List<QualityPhotoDto> = emptyList()
    private var selectedIndex: Int = RecyclerView.NO_POSITION

    inner class ViewHolder(
        private val binding: ItemQualityDetailPhotoBinding
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(photo: QualityPhotoDto, isSelected: Boolean) {
            binding.tvPhotoName.text = photo.name.ifBlank { "工序图片" }
            binding.cardPhoto.strokeWidth = if (isSelected) 3 else 1
            binding.cardPhoto.strokeColor = ContextCompat.getColor(
                binding.root.context,
                if (isSelected) R.color.md_primary else android.R.color.darker_gray
            )

            val model = QualityPhotoRequestFactory.buildModel(
                context = binding.root.context,
                photo = photo,
                preferThumbnail = true
            )
            Glide.with(binding.ivThumbnail)
                .load(model)
                .centerCrop()
                .placeholder(R.drawable.ic_photo)
                .error(R.drawable.ic_photo)
                .into(binding.ivThumbnail)

            binding.root.setOnClickListener {
                val position = adapterPosition
                if (position != RecyclerView.NO_POSITION) {
                    setSelectedIndex(position)
                    onPhotoSelected(items[position])
                }
            }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemQualityDetailPhotoBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(items[position], position == selectedIndex)
    }

    override fun getItemCount(): Int = items.size

    fun submitList(newItems: List<QualityPhotoDto>) {
        val diff = DiffUtil.calculateDiff(PhotoDiffCallback(items, newItems))
        items = newItems
        selectedIndex = if (newItems.isEmpty()) RecyclerView.NO_POSITION else 0
        diff.dispatchUpdatesTo(this)
    }

    fun selectPhoto(photo: QualityPhotoDto) {
        val newIndex = items.indexOfFirst { it.url == photo.url && it.name == photo.name }
            .takeIf { it >= 0 }
            ?: return
        setSelectedIndex(newIndex)
    }

    private fun setSelectedIndex(newIndex: Int) {
        if (selectedIndex == newIndex) {
            return
        }
        val oldIndex = selectedIndex
        selectedIndex = newIndex
        if (oldIndex != RecyclerView.NO_POSITION) {
            notifyItemChanged(oldIndex)
        }
        if (newIndex != RecyclerView.NO_POSITION) {
            notifyItemChanged(newIndex)
        }
    }

    private class PhotoDiffCallback(
        private val oldItems: List<QualityPhotoDto>,
        private val newItems: List<QualityPhotoDto>
    ) : DiffUtil.Callback() {
        override fun getOldListSize(): Int = oldItems.size

        override fun getNewListSize(): Int = newItems.size

        override fun areItemsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
            val oldItem = oldItems[oldItemPosition]
            val newItem = newItems[newItemPosition]
            return oldItem.url == newItem.url && oldItem.name == newItem.name
        }

        override fun areContentsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
            return oldItems[oldItemPosition] == newItems[newItemPosition]
        }
    }
}
