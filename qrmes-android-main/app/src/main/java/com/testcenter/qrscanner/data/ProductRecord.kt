package com.testcenter.qrscanner.data

import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import com.google.gson.reflect.TypeToken

/**
 * 产品记录数据模型
 * 用于 API 数据传输
 */
data class ProductRecord(
    @SerializedName("productSerial")
    val productSerial: String,              // 产品序列号（主键）
    
    @SerializedName("productType")
    val productType: String,                // 产品类型（如：电机控制器）
    
    @SerializedName("projectName")
    val projectName: String,                // 项目名称
    
    @SerializedName("operator")
    val operator: String,                   // 操作员
    
    @SerializedName("scanTime")
    val scanTime: Long,                     // 扫描时间（Unix timestamp）
    
    @SerializedName("materials")
    val materials: Map<String, String>,     // 物料数据：物料名称 -> 序列号
    
    @SerializedName("createdAt")
    val createdAt: Long = System.currentTimeMillis(),
    
    @SerializedName("updatedAt")
    val updatedAt: Long = System.currentTimeMillis()
) {
    /**
     * 获取物料JSON字符串
     */
    fun getMaterialsJson(): String {
        return Companion.materialsToJson(materials)
    }
    
    companion object {
        private val gson = Gson()
        
        /**
         * 将物料Map转为JSON字符串（用于存储）
         */
        fun materialsToJson(materials: Map<String, String>): String {
            return gson.toJson(materials)
        }
        
        /**
         * 从JSON字符串解析物料Map
         */
        fun materialsFromJson(json: String): Map<String, String> {
            return try {
                val type = object : TypeToken<Map<String, String>>() {}.type
                gson.fromJson(json, type) ?: emptyMap()
            } catch (e: Exception) {
                emptyMap()
            }
        }
        

    }
}
