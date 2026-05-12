package com.testcenter.qrscanner.adapter

import android.net.Uri
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.testcenter.qrscanner.databinding.ItemPhotoThumbnailBinding

class PhotoThumbnailAdapter(
    private val photoUris: MutableList<Uri>,
    private val onRemoveClick: (Int) -> Unit
) : RecyclerView.Adapter<PhotoThumbnailAdapter.PhotoViewHolder>() {

    inner class PhotoViewHolder(private val binding: ItemPhotoThumbnailBinding) : 
        RecyclerView.ViewHolder(binding.root) {
        
        fun bind(uri: Uri, position: Int) {
            binding.ivThumbnail.setImageURI(uri)
            binding.btnRemove.setOnClickListener {
                onRemoveClick(position)
            }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): PhotoViewHolder {
        val binding = ItemPhotoThumbnailBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return PhotoViewHolder(binding)
    }

    override fun onBindViewHolder(holder: PhotoViewHolder, position: Int) {
        holder.bind(photoUris[position], position)
    }

    override fun getItemCount(): Int = photoUris.size

    fun updateData(newUris: List<Uri>) {
        photoUris.clear()
        photoUris.addAll(newUris)
        notifyDataSetChanged()
    }
}
