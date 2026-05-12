package com.testcenter.qrscanner.adapter

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import com.testcenter.qrscanner.R

class InspectionStepAdapter(
    private var steps: List<StepItem> = emptyList()
) : RecyclerView.Adapter<InspectionStepAdapter.ViewHolder>() {

    data class StepItem(
        val processName: String,
        val order: Int,
        val hasPhoto: Boolean,
        val photoCount: Int = 0,
        val qcStatus: String?,       // "pass" / "fail" / "ng" / null
        val summary: String = "",
        val defects: List<String> = emptyList()
    )

    // Drawable 缓存：按 (形状, 颜色) 缓存，避免 onBind 时频繁创建
    private val ovalDrawables = mutableMapOf<Int, GradientDrawable>()
    private val roundRectDrawables = mutableMapOf<Int, GradientDrawable>()

    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val tvStepIndex: TextView = itemView.findViewById(R.id.tvStepIndex)
        val tvProcessName: TextView = itemView.findViewById(R.id.tvProcessName)
        val tvPhotoStatus: TextView = itemView.findViewById(R.id.tvPhotoStatus)
        val tvQcSummary: TextView = itemView.findViewById(R.id.tvQcSummary)
        val tvDefects: TextView = itemView.findViewById(R.id.tvDefects)
        val tvQcResult: TextView = itemView.findViewById(R.id.tvQcResult)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_inspection_step, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val step = steps[position]

        // 工序序号
        holder.tvStepIndex.text = step.order.toString()

        // 工序名称
        holder.tvProcessName.text = step.processName

        // 照片状态
        if (step.hasPhoto) {
            holder.tvPhotoStatus.text = if (step.photoCount > 0) "已上传 ${step.photoCount} 张照片" else "已上传照片"
            holder.tvPhotoStatus.setTextColor(Color.parseColor("#666666"))
        } else {
            holder.tvPhotoStatus.text = "未上传照片"
            holder.tvPhotoStatus.setTextColor(Color.parseColor("#F44336"))
        }

        // QC 摘要
        if (step.summary.isNotEmpty()) {
            holder.tvQcSummary.visibility = View.VISIBLE
            holder.tvQcSummary.text = step.summary
        } else {
            holder.tvQcSummary.visibility = View.GONE
        }

        // 缺陷列表
        if (step.defects.isNotEmpty()) {
            holder.tvDefects.visibility = View.VISIBLE
            holder.tvDefects.text = step.defects.joinToString("\n") { "- $it" }
        } else {
            holder.tvDefects.visibility = View.GONE
        }

        // QC 结果标签 + 序号圆圈颜色
        when (step.qcStatus) {
            "pass" -> {
                holder.tvQcResult.text = "通过"
                holder.tvQcResult.setTextColor(Color.WHITE)
                holder.tvQcResult.background = getCachedRoundRect(Color.parseColor("#4CAF50"))
                holder.tvStepIndex.background = getCachedOval(Color.parseColor("#4CAF50"))
            }
            "fail" -> {
                holder.tvQcResult.text = "未通过"
                holder.tvQcResult.setTextColor(Color.WHITE)
                holder.tvQcResult.background = getCachedRoundRect(Color.parseColor("#F44336"))
                holder.tvStepIndex.background = getCachedOval(Color.parseColor("#F44336"))
            }
            "ng" -> {
                holder.tvQcResult.text = "待复核"
                holder.tvQcResult.setTextColor(Color.WHITE)
                holder.tvQcResult.background = getCachedRoundRect(Color.parseColor("#FF9800"))
                holder.tvStepIndex.background = getCachedOval(Color.parseColor("#FF9800"))
            }
            else -> {
                if (!step.hasPhoto) {
                    holder.tvQcResult.text = "缺失"
                    holder.tvQcResult.setTextColor(Color.parseColor("#999999"))
                    holder.tvQcResult.background = getCachedRoundRect(Color.parseColor("#E0E0E0"))
                    holder.tvStepIndex.background = getCachedOval(Color.parseColor("#BDBDBD"))
                } else {
                    holder.tvQcResult.text = "未检"
                    holder.tvQcResult.setTextColor(Color.parseColor("#666666"))
                    holder.tvQcResult.background = getCachedRoundRect(Color.parseColor("#E0E0E0"))
                    holder.tvStepIndex.background = getCachedOval(Color.parseColor("#9E9E9E"))
                }
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

    private fun getCachedRoundRect(color: Int): GradientDrawable {
        return roundRectDrawables.getOrPut(color) {
            GradientDrawable().apply {
                cornerRadius = 12f
                setColor(color)
            }
        }
    }

    override fun getItemCount(): Int = steps.size

    fun updateData(newSteps: List<StepItem>) {
        val diffResult = DiffUtil.calculateDiff(StepDiffCallback(steps, newSteps))
        steps = newSteps
        diffResult.dispatchUpdatesTo(this)
    }

    private class StepDiffCallback(
        private val old: List<StepItem>,
        private val new: List<StepItem>
    ) : DiffUtil.Callback() {
        override fun getOldListSize() = old.size
        override fun getNewListSize() = new.size
        override fun areItemsTheSame(oldPos: Int, newPos: Int) =
            old[oldPos].processName == new[newPos].processName && old[oldPos].order == new[newPos].order
        override fun areContentsTheSame(oldPos: Int, newPos: Int) = old[oldPos] == new[newPos]
    }
}
