package com.testcenter.qrscanner.adapter

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.data.MaterialInfo

data class Component(
    val name: String,
    val partNumber: String = "",
    var serial: String = "待扫描",
    val qrRuleType: String = MaterialInfo.QR_RULE_MOTOR,
    val expectedVersion: String = "",
    val forceVersionCheck: Boolean = false
)
class ComponentAdapter(
    private val components: List<Component>,
    private val onScanClick: (Component) -> Unit,
    private val onManualInputClick: (Component) -> Unit
) :
    RecyclerView.Adapter<ComponentAdapter.ComponentViewHolder>() {

    private var isReadOnlyMode = false

    /**
     * 设置只读模式
     */
    fun setReadOnlyMode(readOnly: Boolean) {
        if (isReadOnlyMode != readOnly) {
            isReadOnlyMode = readOnly
            notifyDataSetChanged()
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ComponentViewHolder {
        val view =
            LayoutInflater.from(parent.context).inflate(R.layout.list_item_component, parent, false)
        return ComponentViewHolder(view)
    }

    override fun onBindViewHolder(holder: ComponentViewHolder, position: Int) {
        val component = components[position]
        holder.bind(component, isReadOnlyMode)
        
        if (isReadOnlyMode) {
            // 只读模式下禁用按钮
            holder.scanButton.isEnabled = false
            holder.manualInputButton.isEnabled = false
            holder.scanButton.text = "只读"
            holder.manualInputButton.text = "只读"
        } else {
            // 编辑模式下启用按钮和点击事件
            holder.scanButton.isEnabled = true
            holder.manualInputButton.isEnabled = true
            holder.scanButton.text = "扫描"
            holder.manualInputButton.text = "手动输入"
            holder.scanButton.setOnClickListener { onScanClick(component) }
            holder.manualInputButton.setOnClickListener { onManualInputClick(component) }
        }
    }

    override fun getItemCount() = components.size

    class ComponentViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val nameTextView: TextView = itemView.findViewById(R.id.tvComponentName)
        private val partNumberTextView: TextView = itemView.findViewById(R.id.tvComponentPartNumber)
        private val serialTextView: TextView = itemView.findViewById(R.id.tvComponentSerial)
        val scanButton: Button = itemView.findViewById(R.id.btnScanComponent)
        val manualInputButton: Button = itemView.findViewById(R.id.btnManualInputComponent)

        fun bind(component: Component, isReadOnlyMode: Boolean = false) {
            nameTextView.text = component.name
            partNumberTextView.text = component.partNumber
            serialTextView.text = component.serial
            
            // 在只读模式下调整UI样式
            if (isReadOnlyMode) {
                // 设置只读模式的视觉样式
                nameTextView.alpha = 0.7f
                partNumberTextView.alpha = 0.7f
                serialTextView.alpha = 0.7f
                scanButton.alpha = 0.5f
                manualInputButton.alpha = 0.5f
            } else {
                // 恢复正常样式
                nameTextView.alpha = 1.0f
                partNumberTextView.alpha = 1.0f
                serialTextView.alpha = 1.0f
                scanButton.alpha = 1.0f
                manualInputButton.alpha = 1.0f
            }
        }
    }
}
