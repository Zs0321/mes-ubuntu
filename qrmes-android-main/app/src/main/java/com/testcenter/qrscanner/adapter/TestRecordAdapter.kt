package com.testcenter.qrscanner.adapter

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.data.TestRecord
import java.text.SimpleDateFormat
import java.util.*

class TestRecordAdapter : ListAdapter<TestRecord, TestRecordAdapter.TestRecordViewHolder>(DiffCallback) {

    var onItemClick: ((TestRecord) -> Unit)? = null

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): TestRecordViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_test_record, parent, false)
        return TestRecordViewHolder(view)
    }

    override fun onBindViewHolder(holder: TestRecordViewHolder, position: Int) {
        val record = getItem(position)
        holder.bind(record)
        holder.itemView.setOnClickListener { onItemClick?.invoke(record) }
    }

    class TestRecordViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val tvSerialNumber: TextView = itemView.findViewById(R.id.tvSerialNumber)
        private val tvStartTime: TextView = itemView.findViewById(R.id.tvStartTime)
        private val tvEndTime: TextView = itemView.findViewById(R.id.tvEndTime)
        private val tvDuration: TextView = itemView.findViewById(R.id.tvDuration)
        private val tvStatus: TextView = itemView.findViewById(R.id.tvStatus)
        private val layoutEndTime: View = itemView.findViewById(R.id.layoutEndTime)
        private val layoutDuration: View = itemView.findViewById(R.id.layoutDuration)

        private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())

        fun bind(record: TestRecord) {
            tvSerialNumber.text = record.serialNumber
            tvStartTime.text = dateFormat.format(record.startTime)

            if (record.isCompleted && record.endTime != null) {
                layoutEndTime.visibility = View.VISIBLE
                layoutDuration.visibility = View.VISIBLE
                tvEndTime.text = dateFormat.format(record.endTime)
                tvDuration.text = "${record.testDurationMinutes} 分钟"
                tvStatus.text = "已完成"
                tvStatus.setBackgroundColor(itemView.context.getColor(android.R.color.holo_green_dark))
            } else {
                layoutEndTime.visibility = View.GONE
                layoutDuration.visibility = View.GONE
                tvStatus.text = "测试中..."
                tvStatus.setBackgroundColor(itemView.context.getColor(android.R.color.holo_orange_dark))
            }
        }
    }

    companion object DiffCallback : DiffUtil.ItemCallback<TestRecord>() {
        override fun areItemsTheSame(oldItem: TestRecord, newItem: TestRecord): Boolean {
            return oldItem.id == newItem.id
        }

        override fun areContentsTheSame(oldItem: TestRecord, newItem: TestRecord): Boolean {
            return oldItem == newItem
        }
    }
}
