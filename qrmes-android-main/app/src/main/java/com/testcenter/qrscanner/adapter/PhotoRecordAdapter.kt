package com.testcenter.qrscanner.adapter

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.testcenter.qrscanner.PhotoRecordsActivity
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

class PhotoRecordAdapter(
    private var photos: List<PhotoRecordsActivity.PhotoRecord>,
    private val directoryInfo: FileManager.PhotoDirectoryInfo,
    private val onPhotoClick: (PhotoRecordsActivity.PhotoRecord) -> Unit
) : RecyclerView.Adapter<PhotoRecordAdapter.PhotoViewHolder>() {

    private val dateFormat = SimpleDateFormat("MM-dd HH:mm", Locale.getDefault())

    // 使用 LruCache 替代无限增长的 MutableMap，限制为 20MB
    private val thumbnailCache: LruCache<String, Bitmap> = run {
        val maxMemory = (Runtime.getRuntime().maxMemory() / 1024).toInt()
        val cacheSize = (maxMemory / 8).coerceAtMost(20 * 1024) // 最多 20MB
        object : LruCache<String, Bitmap>(cacheSize) {
            override fun sizeOf(key: String, bitmap: Bitmap): Int {
                return bitmap.byteCount / 1024
            }
        }
    }

    // 跟踪每个 ViewHolder 的加载任务，避免错位
    private val loadJobs = mutableMapOf<Int, Job>()

    companion object {
        private const val THUMBNAIL_MAX_DIMENSION = 512
    }

    class PhotoViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val ivPhoto: ImageView = view.findViewById(R.id.ivPhoto)
        val tvFileName: TextView = view.findViewById(R.id.tvFileName)
        val tvUploadTime: TextView = view.findViewById(R.id.tvUploadTime)
        val tvFileSize: TextView = view.findViewById(R.id.tvFileSize)
        val progressBar: android.widget.ProgressBar = view.findViewById(R.id.progressBar)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): PhotoViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_photo_record, parent, false)
        return PhotoViewHolder(view)
    }

    override fun onBindViewHolder(holder: PhotoViewHolder, position: Int) {
        val photo = photos[position]

        holder.tvFileName.text = photo.fileName
        holder.tvUploadTime.text = dateFormat.format(Date(photo.uploadTime))
        holder.tvFileSize.text = formatFileSize(photo.fileSize)

        // 取消之前的加载任务（使用 position 而非 hashCode 避免错位）
        loadJobs[position]?.cancel()

        // 检查 Bitmap 缓存
        val cached = thumbnailCache.get(photo.fileName)
        if (cached != null) {
            holder.progressBar.visibility = View.GONE
            holder.ivPhoto.setImageBitmap(cached)
            return
        }

        // 设置默认图标并开始异步加载
        holder.ivPhoto.setImageResource(R.drawable.ic_photo)
        holder.progressBar.visibility = View.VISIBLE

        val job = CoroutineScope(Dispatchers.Main).launch {
            try {
                val context = holder.itemView.context
                val preferencesManager = PreferencesManager(context)
                val username = preferencesManager.getUsername() ?: ""
                val password = preferencesManager.getPassword() ?: ""
                val fileManager = FileManagerFactory.create(context, username, password)

                val bitmap = withContext(Dispatchers.IO) {
                    val photoBytes = fileManager.downloadPhoto(directoryInfo, photo.fileName)
                        ?: return@withContext null
                    decodeSampledBitmap(photoBytes)
                }

                // 检查 ViewHolder 是否仍然绑定到同一个 position
                if (holder.adapterPosition == position && bitmap != null) {
                    thumbnailCache.put(photo.fileName, bitmap)
                    holder.progressBar.visibility = View.GONE
                    holder.ivPhoto.setImageBitmap(bitmap)
                }
            } catch (e: Exception) {
                if (holder.adapterPosition == position) {
                    holder.progressBar.visibility = View.GONE
                }
                AppLogger.log("PhotoRecordAdapter", "加载照片异常: ${photo.fileName}, ${e.message}", e)
            }
        }
        loadJobs[position] = job
    }

    override fun onViewRecycled(holder: PhotoViewHolder) {
        super.onViewRecycled(holder)
        val pos = holder.adapterPosition
        if (pos != RecyclerView.NO_POSITION) {
            loadJobs.remove(pos)?.cancel()
        }
    }

    override fun getItemCount(): Int = photos.size

    fun updateData(newPhotos: List<PhotoRecordsActivity.PhotoRecord>) {
        photos = newPhotos
        notifyDataSetChanged()
    }

    /**
     * 降采样解码 Bitmap，生成缩略图
     */
    private fun decodeSampledBitmap(photoBytes: ByteArray): Bitmap? {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(photoBytes, 0, photoBytes.size, options)

        var sampleSize = 1
        while (options.outWidth / sampleSize > THUMBNAIL_MAX_DIMENSION ||
            options.outHeight / sampleSize > THUMBNAIL_MAX_DIMENSION) {
            sampleSize *= 2
        }

        val decodeOptions = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        return BitmapFactory.decodeByteArray(photoBytes, 0, photoBytes.size, decodeOptions)
    }

    private fun formatFileSize(bytes: Long): String {
        return when {
            bytes < 1024 -> "$bytes B"
            bytes < 1024 * 1024 -> "${bytes / 1024} KB"
            else -> String.format("%.1f MB", bytes / (1024.0 * 1024.0))
        }
    }
}
