package com.testcenter.qrscanner.adapter

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.data.ProcessStep
import com.testcenter.qrscanner.utils.AppLogger

class ProcessStepAdapter(
    private val processSteps: List<ProcessStep>,
    private val onCameraClick: (ProcessStep) -> Unit,
    private val onStepClick: ((ProcessStep, QcStatusInfo?) -> Unit)? = null
) : RecyclerView.Adapter<ProcessStepAdapter.ProcessStepViewHolder>() {

    // 工序 QC 状态缓存: processStepId -> QcStatusInfo
    private val qcStatusMap = mutableMapOf<String, QcStatusInfo>()

    // 预创建 Drawable 缓存，避免 onBind 时频繁创建
    private val drawableCache = mutableMapOf<String, GradientDrawable>()

    data class QcStatusInfo(
        val hasPhoto: Boolean = false,
        val photoCount: Int = 0,
        val qcStatus: String? = null,  // "pass" / "fail" / "ng" / null
        val qcSummary: String? = null, // QC 结论描述
        val findings: List<FindingInfo> = emptyList(), // QC 发现的具体问题
        val pdfCount: Int = 0,  // 已上传 PDF 数量
        val aiStatus: String? = null,
        val aiSummary: String? = null,
        val aiFindings: List<FindingInfo> = emptyList(),
        val humanStatus: String? = null,
        val humanSummary: String? = null,
        val humanFindings: List<FindingInfo> = emptyList()
    )

    data class FindingInfo(
        val severity: String,   // "critical" / "major" / "minor"
        val description: String,
        val location: String = ""
    )

    class ProcessStepViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val card: MaterialCardView = itemView as MaterialCardView
        val tvStepName: TextView = itemView.findViewById(R.id.tvStepName)
        val tvStepDescription: TextView = itemView.findViewById(R.id.tvStepDescription)
        val tvStepOrder: TextView = itemView.findViewById(R.id.tvStepOrder)
        val btnCamera: MaterialButton = itemView.findViewById(R.id.btnCamera)
        val ivPhotoPreview: ImageView = itemView.findViewById(R.id.ivPhotoPreview)
        val tvQcStatus: TextView = itemView.findViewById(R.id.tvQcStatus)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ProcessStepViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_process_step, parent, false)
        return ProcessStepViewHolder(view)
    }

    override fun onBindViewHolder(holder: ProcessStepViewHolder, position: Int) {
        val processStep = processSteps[position]

        holder.tvStepName.text = processStep.name
        holder.tvStepDescription.text = processStep.description
        holder.tvStepOrder.text = "步骤 ${processStep.order}"

        // 根据 attachmentType 调整按钮文字和图标
        AppLogger.log("ProcessStepAdapter", "[工序${processStep.order}] ${processStep.name} attachmentType='${processStep.attachmentType}'")
        when (processStep.attachmentType) {
            "pdf" -> {
                holder.btnCamera.text = "选择PDF"
                holder.btnCamera.setIconResource(R.drawable.ic_pdf)
            }
            "both" -> {
                holder.btnCamera.text = "拍照/PDF"
                holder.btnCamera.setIconResource(R.drawable.ic_camera_alt)
            }
            else -> {
                holder.btnCamera.text = "拍照"
                holder.btnCamera.setIconResource(R.drawable.ic_camera_alt)
            }
        }

        holder.btnCamera.setOnClickListener {
            onCameraClick(processStep)
        }

        // 卡片点击查看 QC 详情
        holder.card.setOnClickListener {
            onStepClick?.invoke(processStep, qcStatusMap[processStep.id])
        }

        holder.ivPhotoPreview.visibility = View.GONE

        // 显示 QC 结论描述（复用工序描述区域）
        val statusInfo = qcStatusMap[processStep.id]
        if (statusInfo?.qcSummary?.isNotBlank() == true) {
            holder.tvStepDescription.text = buildStepDescription(statusInfo)
            holder.tvStepDescription.setTextColor(
                when (statusInfo.qcStatus) {
                    "pass" -> Color.parseColor("#2E7D32")
                    "fail" -> Color.parseColor("#C62828")
                    "ng" -> Color.parseColor("#E65100")
                    else -> Color.parseColor("#666666")
                }
            )
        } else {
            holder.tvStepDescription.text = processStep.description
            holder.tvStepDescription.setTextColor(Color.parseColor("#666666"))
        }
        val countSuffix = buildString {
            if (statusInfo != null && statusInfo.photoCount > 0) append(" (${statusInfo.photoCount}张)")
            if (statusInfo != null && statusInfo.pdfCount > 0) append(" (${statusInfo.pdfCount}文档)")
        }

        if (statusInfo != null) {
            when (statusInfo.qcStatus) {
                "pass" -> {
                    holder.tvQcStatus.visibility = View.VISIBLE
                    holder.tvQcStatus.text = "QC通过$countSuffix"
                    holder.tvQcStatus.setTextColor(Color.WHITE)
                    holder.tvQcStatus.background = getCachedDrawable("pass", "#4CAF50")
                }
                "fail" -> {
                    holder.tvQcStatus.visibility = View.VISIBLE
                    holder.tvQcStatus.text = "QC未通过$countSuffix"
                    holder.tvQcStatus.setTextColor(Color.WHITE)
                    holder.tvQcStatus.background = getCachedDrawable("fail", "#F44336")
                }
                "ng" -> {
                    holder.tvQcStatus.visibility = View.VISIBLE
                    holder.tvQcStatus.text = "待复核$countSuffix"
                    holder.tvQcStatus.setTextColor(Color.WHITE)
                    holder.tvQcStatus.background = getCachedDrawable("ng", "#FF9800")
                }
                else -> {
                    if (statusInfo.hasPhoto || statusInfo.pdfCount > 0) {
                        holder.tvQcStatus.visibility = View.VISIBLE
                        val label = when {
                            statusInfo.hasPhoto && statusInfo.pdfCount > 0 -> "已上传$countSuffix"
                            statusInfo.pdfCount > 0 -> "已上传$countSuffix"
                            else -> "已拍照$countSuffix"
                        }
                        holder.tvQcStatus.text = label
                        holder.tvQcStatus.setTextColor(Color.parseColor("#666666"))
                        holder.tvQcStatus.background = getCachedDrawable("photo", "#E0E0E0")
                    } else if (processStep.required && processStep.photoRequired) {
                        holder.tvQcStatus.visibility = View.VISIBLE
                        holder.tvQcStatus.text = "未拍照"
                        holder.tvQcStatus.setTextColor(Color.WHITE)
                        holder.tvQcStatus.background = getCachedDrawable("missing", "#F44336")
                    } else {
                        holder.tvQcStatus.visibility = View.GONE
                    }
                }
            }
        } else {
            holder.tvQcStatus.visibility = View.GONE
        }

        // 未拍照必需工序卡片标红
        val needsPhoto = processStep.required && processStep.photoRequired
        val hasPhoto = statusInfo?.hasPhoto == true
        if (needsPhoto && statusInfo != null && !hasPhoto) {
            holder.card.strokeColor = Color.parseColor("#F44336")
            holder.card.strokeWidth = 2
        } else {
            holder.card.strokeColor = Color.TRANSPARENT
            holder.card.strokeWidth = 0
        }
    }

    private fun getCachedDrawable(key: String, colorHex: String): GradientDrawable {
        return drawableCache.getOrPut(key) {
            GradientDrawable().apply {
                cornerRadius = 8f
                setColor(Color.parseColor(colorHex))
            }
        }
    }

    override fun getItemCount(): Int = processSteps.size

    /**
     * 更新单个工序的 QC 状态
     */
    fun updateQcStatus(
        processStepId: String,
        hasPhoto: Boolean,
        photoCount: Int,
        qcStatus: String?,
        qcSummary: String? = null,
        findings: List<FindingInfo> = emptyList(),
        aiStatus: String? = null,
        aiSummary: String? = null,
        aiFindings: List<FindingInfo> = emptyList(),
        humanStatus: String? = null,
        humanSummary: String? = null,
        humanFindings: List<FindingInfo> = emptyList()
    ) {
        val existing = qcStatusMap[processStepId]
        qcStatusMap[processStepId] = QcStatusInfo(
            hasPhoto = hasPhoto,
            photoCount = photoCount,
            qcStatus = qcStatus,
            qcSummary = qcSummary,
            findings = findings,
            pdfCount = existing?.pdfCount ?: 0,  // 保留已有的 PDF 计数
            aiStatus = aiStatus ?: existing?.aiStatus,
            aiSummary = aiSummary ?: existing?.aiSummary,
            aiFindings = if (aiFindings.isNotEmpty()) aiFindings else existing?.aiFindings ?: emptyList(),
            humanStatus = humanStatus ?: existing?.humanStatus,
            humanSummary = humanSummary ?: existing?.humanSummary,
            humanFindings = if (humanFindings.isNotEmpty()) humanFindings else existing?.humanFindings ?: emptyList()
        )
        val index = processSteps.indexOfFirst { it.id == processStepId }
        if (index >= 0) {
            notifyItemChanged(index)
        }
    }

    private fun buildStepDescription(statusInfo: QcStatusInfo): String {
        val lines = mutableListOf<String>()
        val currentSummary = statusInfo.qcSummary?.trim().orEmpty()
        val aiSummary = statusInfo.aiSummary?.trim().orEmpty()

        if (currentSummary.isNotEmpty()) {
            lines.add(currentSummary)
        }
        if (aiSummary.isNotEmpty() && aiSummary != currentSummary) {
            lines.add("AI: $aiSummary")
        }
        if (lines.isEmpty()) {
            return ""
        }
        return lines.joinToString("\n")
    }

    /**
     * 更新工序的 PDF 文档数量（累加）
     */
    fun incrementPdfCount(processStepId: String) {
        val existing = qcStatusMap[processStepId]
        qcStatusMap[processStepId] = (existing ?: QcStatusInfo()).copy(
            pdfCount = (existing?.pdfCount ?: 0) + 1
        )
        val index = processSteps.indexOfFirst { it.id == processStepId }
        if (index >= 0) {
            notifyItemChanged(index)
        }
    }

    /**
     * 查询工序是否有照片
     */
    fun hasPhotoForStep(stepId: String): Boolean {
        return qcStatusMap[stepId]?.hasPhoto == true
    }

    /**
     * 获取工序的 QC 状态（供外部读取）
     */
    fun getQcStatusForStep(stepId: String): QcStatusInfo? {
        return qcStatusMap[stepId]
    }

    /**
     * 完整更新工序状态（含 pdfCount）
     */
    fun updateQcStatusFull(
        processStepId: String,
        hasPhoto: Boolean,
        photoCount: Int,
        qcStatus: String?,
        qcSummary: String? = null,
        findings: List<FindingInfo> = emptyList(),
        pdfCount: Int = 0,
        aiStatus: String? = null,
        aiSummary: String? = null,
        aiFindings: List<FindingInfo> = emptyList(),
        humanStatus: String? = null,
        humanSummary: String? = null,
        humanFindings: List<FindingInfo> = emptyList()
    ) {
        val existing = qcStatusMap[processStepId]
        qcStatusMap[processStepId] = QcStatusInfo(
            hasPhoto = hasPhoto,
            photoCount = photoCount,
            qcStatus = qcStatus,
            qcSummary = qcSummary,
            findings = findings,
            pdfCount = pdfCount,
            aiStatus = aiStatus ?: existing?.aiStatus,
            aiSummary = aiSummary ?: existing?.aiSummary,
            aiFindings = if (aiFindings.isNotEmpty()) aiFindings else existing?.aiFindings ?: emptyList(),
            humanStatus = humanStatus ?: existing?.humanStatus,
            humanSummary = humanSummary ?: existing?.humanSummary,
            humanFindings = if (humanFindings.isNotEmpty()) humanFindings else existing?.humanFindings ?: emptyList()
        )
        val index = processSteps.indexOfFirst { it.id == processStepId }
        if (index >= 0) {
            notifyItemChanged(index)
        }
    }

    /**
     * 清除所有 QC 状态
     */
    fun clearQcStatus() {
        qcStatusMap.clear()
        notifyDataSetChanged()
    }
}
