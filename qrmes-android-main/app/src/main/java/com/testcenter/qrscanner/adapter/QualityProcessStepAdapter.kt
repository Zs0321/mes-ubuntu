package com.testcenter.qrscanner.adapter

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.quality.QualityProcessResultDto

class QualityProcessStepAdapter(
    private val onViewDetail: (QualityProcessResultDto) -> Unit
) : RecyclerView.Adapter<QualityProcessStepAdapter.ViewHolder>() {

    private var steps: List<QualityProcessResultDto> = emptyList()
    private val roundRectDrawables = mutableMapOf<Int, GradientDrawable>()
    private val ovalDrawables = mutableMapOf<Int, GradientDrawable>()

    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val tvStepIndex: TextView = itemView.findViewById(R.id.tvStepIndex)
        val tvProcessName: TextView = itemView.findViewById(R.id.tvProcessName)
        val tvPhotoStatus: TextView = itemView.findViewById(R.id.tvPhotoStatus)
        val tvQcSummary: TextView = itemView.findViewById(R.id.tvQcSummary)
        val tvQcResult: TextView = itemView.findViewById(R.id.tvQcResult)
        val btnViewDetail: MaterialButton = itemView.findViewById(R.id.btnViewDetail)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_quality_process_step, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val step = steps[position]
        val status = step.effectiveStatus ?: step.status ?: "pending"
        holder.tvStepIndex.text = (step.order.takeIf { it > 0 } ?: position + 1).toString()
        holder.tvProcessName.text = step.process.ifBlank { "未命名工序" }
        holder.tvPhotoStatus.text = step.toDisplayPhotoStatus()
        holder.tvPhotoStatus.setTextColor(
            when {
                step.photoRequired == true && !step.hasPhoto && step.photoCount <= 0 -> Color.parseColor("#B91C1C")
                step.hasPhoto || step.photoCount > 0 -> Color.parseColor("#475569")
                else -> Color.parseColor("#64748B")
            }
        )
        holder.tvQcSummary.text = step.summary
            .ifBlank { step.effectiveSummary }
            .ifBlank {
                if (step.photoRequired == true && !step.hasPhoto && step.photoCount <= 0) {
                    "当前工序缺少必需照片。"
                } else {
                    "暂无检查摘要。"
                }
            }

        applyStatusStyle(holder.tvQcResult, holder.tvStepIndex, status)
        holder.btnViewDetail.isEnabled = step.detailAvailable && step.process.isNotBlank()
        holder.btnViewDetail.setOnClickListener { onViewDetail(step) }
    }

    override fun getItemCount(): Int = steps.size

    fun updateData(newSteps: List<QualityProcessResultDto>) {
        val sortedSteps = newSteps.sortedWith(
            compareBy<QualityProcessResultDto>({ if (it.order > 0) it.order else Int.MAX_VALUE }, { it.process })
        )
        val diffResult = DiffUtil.calculateDiff(StepDiffCallback(steps, sortedSteps))
        steps = sortedSteps
        diffResult.dispatchUpdatesTo(this)
    }

    private fun applyStatusStyle(resultView: TextView, indexView: TextView, status: String) {
        when (status) {
            "pass" -> {
                resultView.text = "通过"
                resultView.setTextColor(Color.WHITE)
                resultView.background = getCachedRoundRect(Color.parseColor("#2E7D32"))
                indexView.background = getCachedOval(Color.parseColor("#2E7D32"))
            }
            "review", "ng" -> {
                resultView.text = "待复核"
                resultView.setTextColor(Color.WHITE)
                resultView.background = getCachedRoundRect(Color.parseColor("#ED6C02"))
                indexView.background = getCachedOval(Color.parseColor("#ED6C02"))
            }
            "block", "fail" -> {
                resultView.text = "未通过"
                resultView.setTextColor(Color.WHITE)
                resultView.background = getCachedRoundRect(Color.parseColor("#BA1A1A"))
                indexView.background = getCachedOval(Color.parseColor("#BA1A1A"))
            }
            else -> {
                resultView.text = "待补充"
                resultView.setTextColor(Color.parseColor("#475569"))
                resultView.background = getCachedRoundRect(Color.parseColor("#E2E8F0"))
                indexView.background = getCachedOval(Color.parseColor("#94A3B8"))
            }
        }
    }

    private fun getCachedRoundRect(color: Int): GradientDrawable {
        return roundRectDrawables.getOrPut(color) {
            GradientDrawable().apply {
                cornerRadius = 16f
                setColor(color)
            }
        }
    }

    private fun getCachedOval(color: Int): GradientDrawable {
        return ovalDrawables.getOrPut(color) {
            GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(color)
            }
        }
    }

    private class StepDiffCallback(
        private val old: List<QualityProcessResultDto>,
        private val new: List<QualityProcessResultDto>
    ) : DiffUtil.Callback() {
        override fun getOldListSize(): Int = old.size
        override fun getNewListSize(): Int = new.size

        override fun areItemsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
            val oldItem = old[oldItemPosition]
            val newItem = new[newItemPosition]
            return oldItem.process == newItem.process && oldItem.order == newItem.order
        }

        override fun areContentsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
            return old[oldItemPosition] == new[newItemPosition]
        }
    }
}

internal fun QualityProcessResultDto.toDisplayPhotoStatus(): String {
    return when {
        hasPhoto || photoCount > 0 -> "已上传 (${photoCount})"
        photoRequired == true -> "缺少照片"
        else -> "未上传"
    }
}
