package com.testcenter.qrscanner

import android.app.Dialog
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.DialogFragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.bumptech.glide.Glide
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.testcenter.qrscanner.adapter.QualityDetailPhotoAdapter
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.api.QualityPhotoDeleteRequest
import com.testcenter.qrscanner.databinding.DialogQualityProcessDetailBinding
import com.testcenter.qrscanner.quality.QualityDefectDto
import com.testcenter.qrscanner.quality.QualityPhotoDto
import com.testcenter.qrscanner.quality.QualityPhotoRequestFactory
import com.testcenter.qrscanner.quality.QualityProcessDetailResponse
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class QualityProcessDetailDialogFragment : DialogFragment() {

    private var _binding: DialogQualityProcessDetailBinding? = null
    private val binding get() = _binding!!

    private lateinit var photoAdapter: QualityDetailPhotoAdapter
    private var activePhoto: QualityPhotoDto? = null
    private var hasRequestedDetail: Boolean = false
    private var detailJob: Job? = null

    private fun getApiServiceOrNull() = context?.let { ApiClient.getApiService(it) }

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        val currentBinding = DialogQualityProcessDetailBinding.inflate(LayoutInflater.from(requireContext()))
        _binding = currentBinding
        setupUi(currentBinding)
        return MaterialAlertDialogBuilder(requireContext())
            .setView(currentBinding.root)
            .create()
    }

    override fun onStart() {
        super.onStart()
        dialog?.window?.setLayout(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        )
        if (!hasRequestedDetail) {
            hasRequestedDetail = true
            loadProcessDetail()
        }
    }

    private fun setupUi(currentBinding: DialogQualityProcessDetailBinding) {
        currentBinding.btnClose.setOnClickListener { dismissAllowingStateLoss() }
        currentBinding.btnOpenFullScreen.setOnClickListener { openFullScreenPhoto() }
        currentBinding.btnDeletePhoto.setOnClickListener { confirmDeleteCurrentPhoto() }
        currentBinding.ivPreview.setOnClickListener { openFullScreenPhoto() }

        photoAdapter = QualityDetailPhotoAdapter { photo ->
            showPhoto(photo)
        }
        currentBinding.recyclerViewPhotos.apply {
            layoutManager = LinearLayoutManager(currentBinding.root.context, LinearLayoutManager.HORIZONTAL, false)
            adapter = photoAdapter
            isNestedScrollingEnabled = false
        }
    }

    private fun openFullScreenPhoto() {
        val photo = activePhoto
        val context = context ?: return
        if (photo == null) {
            Toast.makeText(context, "当前没有可查看图片", Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(context, QualityPhotoPreviewActivity::class.java).apply {
            putExtra(QualityPhotoPreviewActivity.EXTRA_PHOTO_NAME, photo.name)
            putExtra(QualityPhotoPreviewActivity.EXTRA_PHOTO_URL, photo.url)
            putExtra(QualityPhotoPreviewActivity.EXTRA_THUMBNAIL_URL, photo.thumbnailUrl)
        })
    }

    private fun loadProcessDetail() {
        val serial = requireArguments().getString(ARG_SERIAL_NUMBER).orEmpty()
        val processName = requireArguments().getString(ARG_PROCESS_NAME).orEmpty()
        if (serial.isBlank() || processName.isBlank()) {
            showError("缺少工序查询参数")
            return
        }

        val currentBinding = _binding ?: return
        currentBinding.loadingSection.visibility = android.view.View.VISIBLE
        currentBinding.contentSection.visibility = android.view.View.GONE
        currentBinding.tvErrorMessage.visibility = android.view.View.GONE
        currentBinding.tvTitle.text = processName
        currentBinding.tvSubtitle.text = serial

        val service = getApiServiceOrNull() ?: return
        detailJob?.cancel()
        detailJob = lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    service.getQualityWorkbenchProcessDetail(serial, processName)
                }
                if (_binding == null) {
                    return@launch
                }
                if (!response.isSuccessful) {
                    showError("请求失败 (${response.code()})")
                    return@launch
                }
                val payload = response.body()
                if (payload == null || !payload.success) {
                    showError(payload?.error ?: "未找到工序详情")
                    return@launch
                }
                renderPayload(payload)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                AppLogger.log(TAG, "加载工序详情失败: ${e.message}", e)
                showError("加载失败: ${e.message}")
            }
        }
    }

    private fun renderPayload(payload: QualityProcessDetailResponse) {
        val currentBinding = _binding ?: return
        val detail = payload.processDetail
        currentBinding.loadingSection.visibility = android.view.View.GONE
        currentBinding.contentSection.visibility = android.view.View.VISIBLE
        currentBinding.tvErrorMessage.visibility = android.view.View.GONE

        currentBinding.tvTitle.text = detail.process.ifBlank { "工序详情" }
        currentBinding.tvSubtitle.text = buildString {
            append(payload.serialNumber.ifBlank { "-" })
            append(" / ")
            append(payload.productType.ifBlank { "-" })
        }

        applyBadgeStyle(currentBinding.tvStatusBadge, mapStatusLabel(detail.status), detail.status)
        currentBinding.tvMeta.text = buildMetaText(
            "工序顺序" to detail.order.toString(),
            "拍照要求" to if (detail.photoRequired == true) "必需拍照" else "非必需拍照",
            "照片数量" to detail.photoCount.toString(),
            "AI 判定" to detail.aiStatus.orEmpty().ifBlank { "-" },
            "人工判定" to detail.humanStatus.orEmpty().ifBlank { "-" },
            "最近检查时间" to detail.latestInspectionTime.ifBlank { "-" }
        )

        currentBinding.tvSummary.text = buildString {
            append("AI 说明：")
            append(detail.aiSummary.ifBlank { "—" })
            append("\n\n人工说明：")
            append(detail.humanSummary.ifBlank { "—" })
            append("\n\n最终结论：")
            append(detail.effectiveSummary.ifBlank { "—" })
        }

        currentBinding.tvDefects.text = buildDefectsText(detail.defects)

        val photos = detail.photos
        photoAdapter.submitList(photos)
        currentBinding.recyclerViewPhotos.visibility = if (photos.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE
        currentBinding.tvPhotoEmpty.visibility = if (photos.isEmpty()) android.view.View.VISIBLE else android.view.View.GONE
        currentBinding.btnOpenFullScreen.isEnabled = photos.isNotEmpty()
        currentBinding.btnDeletePhoto.visibility = if (detail.canDeletePhotos && photos.isNotEmpty()) android.view.View.VISIBLE else android.view.View.GONE
        currentBinding.btnDeletePhoto.isEnabled = detail.canDeletePhotos && photos.isNotEmpty()

        if (photos.isNotEmpty()) {
            showPhoto(photos.first())
        } else {
            activePhoto = null
            currentBinding.ivPreview.setImageDrawable(null)
            currentBinding.ivPreview.visibility = android.view.View.GONE
            currentBinding.tvPreviewName.text = "当前工序没有可查看图片。若该工序要求拍照，则该状态会计入缺失工序。"
        }
    }

    private fun showPhoto(photo: QualityPhotoDto) {
        val currentBinding = _binding ?: return
        val context = context ?: return
        activePhoto = photo
        photoAdapter.selectPhoto(photo)
        currentBinding.ivPreview.visibility = android.view.View.VISIBLE
        currentBinding.tvPreviewName.text = photo.name.ifBlank { "工序图片" }
        val model = QualityPhotoRequestFactory.buildModel(context, photo, preferThumbnail = false)
        Glide.with(currentBinding.ivPreview)
            .load(model)
            .fitCenter()
            .placeholder(com.testcenter.qrscanner.R.drawable.ic_photo)
            .error(com.testcenter.qrscanner.R.drawable.ic_photo)
            .into(currentBinding.ivPreview)
    }

    private fun confirmDeleteCurrentPhoto() {
        val photo = activePhoto
        val context = context ?: return
        if (photo == null) {
            Toast.makeText(context, "当前没有可删除图片", Toast.LENGTH_SHORT).show()
            return
        }
        if (photo.relativePath.isBlank()) {
            Toast.makeText(context, "缺少照片路径，无法删除", Toast.LENGTH_SHORT).show()
            return
        }
        MaterialAlertDialogBuilder(context)
            .setTitle("删除照片")
            .setMessage("确定删除 ${photo.name.ifBlank { "当前工序照片" }} 吗？删除后不可恢复。")
            .setNegativeButton("取消", null)
            .setPositiveButton("删除") { _, _ ->
                deletePhoto(photo)
            }
            .show()
    }

    private fun deletePhoto(photo: QualityPhotoDto) {
        val context = context ?: return
        val currentBinding = _binding ?: return
        val service = getApiServiceOrNull() ?: return
        currentBinding.btnDeletePhoto.isEnabled = false
        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    service.deleteQualityWorkbenchPhoto(QualityPhotoDeleteRequest(photo.relativePath))
                }
                if (_binding == null) {
                    return@launch
                }
                val payload = response.body()
                if (!response.isSuccessful || payload?.success != true) {
                    currentBinding.btnDeletePhoto.isEnabled = true
                    Toast.makeText(context, payload?.error ?: "删除失败 (${response.code()})", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                Toast.makeText(context, payload.message ?: "照片删除成功", Toast.LENGTH_SHORT).show()
                loadProcessDetail()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                currentBinding.btnDeletePhoto.isEnabled = true
                AppLogger.log(TAG, "删除工序照片失败: ${e.message}", e)
                Toast.makeText(context, "删除失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun showError(message: String) {
        val currentBinding = _binding ?: return
        currentBinding.loadingSection.visibility = android.view.View.GONE
        currentBinding.contentSection.visibility = android.view.View.GONE
        currentBinding.tvErrorMessage.visibility = android.view.View.VISIBLE
        currentBinding.tvErrorMessage.text = message
    }

    private fun buildMetaText(vararg items: Pair<String, String>): String {
        return items.joinToString("\n") { (key, value) -> "$key：${value.ifBlank { "-" }}" }
    }

    private fun buildDefectsText(defects: List<QualityDefectDto>): String {
        if (defects.isEmpty()) {
            return "当前没有缺陷记录。"
        }
        return defects.joinToString("\n") { defect ->
            defect.description.ifBlank {
                defect.type.ifBlank { "未命名缺陷" }
            }
        }
    }

    private fun mapStatusLabel(status: String?): String {
        return when (status) {
            "pass" -> "通过"
            "review", "ng" -> "待复核"
            "block", "fail" -> "未通过"
            else -> "待补充"
        }
    }

    private fun applyBadgeStyle(textView: TextView, label: String, level: String?) {
        textView.text = label
        val background = GradientDrawable().apply { cornerRadius = 20f }
        when (level) {
            "pass" -> {
                background.setColor(Color.parseColor("#E6F4EA"))
                textView.setTextColor(Color.parseColor("#1B5E20"))
            }
            "review", "ng" -> {
                background.setColor(Color.parseColor("#FFF4E5"))
                textView.setTextColor(Color.parseColor("#B45309"))
            }
            "block", "fail" -> {
                background.setColor(Color.parseColor("#FDECEC"))
                textView.setTextColor(Color.parseColor("#B91C1C"))
            }
            else -> {
                background.setColor(Color.parseColor("#F1F5F9"))
                textView.setTextColor(Color.parseColor("#475569"))
            }
        }
        textView.background = background
    }

    override fun onDestroyView() {
        detailJob?.cancel()
        detailJob = null
        _binding = null
        super.onDestroyView()
    }

    companion object {
        private const val ARG_SERIAL_NUMBER = "arg_serial_number"
        private const val ARG_PROCESS_NAME = "arg_process_name"
        private const val TAG = "QualityProcessDetail"

        fun newInstance(serialNumber: String, processName: String): QualityProcessDetailDialogFragment {
            return QualityProcessDetailDialogFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_SERIAL_NUMBER, serialNumber)
                    putString(ARG_PROCESS_NAME, processName)
                }
            }
        }
    }
}
