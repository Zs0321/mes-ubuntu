package com.testcenter.qrscanner.performance

import android.app.ActivityManager
import android.content.Context
import android.graphics.Bitmap
import com.testcenter.qrscanner.utils.AppLogger
import java.lang.ref.WeakReference
import java.util.concurrent.ConcurrentHashMap

/**
 * 内存优化管理器
 * 优化移动端的内存使用和响应速度
 */
class MemoryOptimizer(private val context: Context) {
    
    companion object {
        private const val TAG = "MemoryOptimizer"
        private const val LOW_MEMORY_THRESHOLD_MB = 50
        private const val CRITICAL_MEMORY_THRESHOLD_MB = 20
    }
    
    private val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
    private val bitmapCache = ConcurrentHashMap<String, WeakReference<Bitmap>>()
    
    /**
     * 内存状态
     */
    enum class MemoryStatus {
        NORMAL,     // 正常
        LOW,        // 内存不足
        CRITICAL    // 内存严重不足
    }
    
    /**
     * 获取当前内存状态
     */
    fun getMemoryStatus(): MemoryStatus {
        val memInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memInfo)
        
        val availableMB = memInfo.availMem / (1024 * 1024)
        
        return when {
            availableMB < CRITICAL_MEMORY_THRESHOLD_MB -> MemoryStatus.CRITICAL
            availableMB < LOW_MEMORY_THRESHOLD_MB -> MemoryStatus.LOW
            else -> MemoryStatus.NORMAL
        }
    }
    
    /**
     * 获取可用内存（MB）
     */
    fun getAvailableMemoryMB(): Long {
        val memInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memInfo)
        return memInfo.availMem / (1024 * 1024)
    }
    
    /**
     * 获取总内存（MB）
     */
    fun getTotalMemoryMB(): Long {
        val memInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memInfo)
        return memInfo.totalMem / (1024 * 1024)
    }
    
    /**
     * 获取内存使用百分比
     */
    fun getMemoryUsagePercentage(): Int {
        val memInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memInfo)
        
        val usedMem = memInfo.totalMem - memInfo.availMem
        return ((usedMem.toFloat() / memInfo.totalMem.toFloat()) * 100).toInt()
    }
    
    /**
     * 检查是否处于低内存状态
     */
    fun isLowMemory(): Boolean {
        val memInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memInfo)
        return memInfo.lowMemory
    }
    
    /**
     * 缓存Bitmap（使用弱引用）
     */
    fun cacheBitmap(key: String, bitmap: Bitmap) {
        bitmapCache[key] = WeakReference(bitmap)
        AppLogger.log(TAG, "缓存Bitmap: $key")
    }
    
    /**
     * 获取缓存的Bitmap
     */
    fun getCachedBitmap(key: String): Bitmap? {
        val weakRef = bitmapCache[key]
        val bitmap = weakRef?.get()
        
        if (bitmap == null) {
            bitmapCache.remove(key)
        }
        
        return bitmap
    }
    
    /**
     * 清除Bitmap缓存
     */
    fun clearBitmapCache() {
        bitmapCache.values.forEach { weakRef ->
            weakRef.get()?.recycle()
        }
        bitmapCache.clear()
        AppLogger.log(TAG, "清除Bitmap缓存")
    }
    
    /**
     * 执行内存清理
     */
    fun performMemoryCleanup() {
        AppLogger.log(TAG, "执行内存清理")
        
        // 清理Bitmap缓存中已被回收的引用
        val iterator = bitmapCache.entries.iterator()
        var cleanedCount = 0
        
        while (iterator.hasNext()) {
            val entry = iterator.next()
            if (entry.value.get() == null) {
                iterator.remove()
                cleanedCount++
            }
        }
        
        if (cleanedCount > 0) {
            AppLogger.log(TAG, "清理了 $cleanedCount 个无效的Bitmap引用")
        }
        
        // 建议系统进行垃圾回收
        System.gc()
        
        AppLogger.log(TAG, "内存清理完成，当前可用内存: ${getAvailableMemoryMB()}MB")
    }
    
    /**
     * 根据内存状态自动调整
     */
    fun autoAdjustByMemoryStatus(): MemoryStatus {
        val status = getMemoryStatus()
        
        when (status) {
            MemoryStatus.CRITICAL -> {
                AppLogger.log(TAG, "内存严重不足，执行紧急清理")
                clearBitmapCache()
                performMemoryCleanup()
            }
            MemoryStatus.LOW -> {
                AppLogger.log(TAG, "内存不足，执行常规清理")
                performMemoryCleanup()
            }
            MemoryStatus.NORMAL -> {
                // 正常状态，无需特殊处理
            }
        }
        
        return status
    }
    
    /**
     * 获取内存信息摘要
     */
    fun getMemorySummary(): String {
        val availableMB = getAvailableMemoryMB()
        val totalMB = getTotalMemoryMB()
        val usagePercentage = getMemoryUsagePercentage()
        val status = getMemoryStatus()
        
        return """
            内存状态: $status
            可用内存: ${availableMB}MB
            总内存: ${totalMB}MB
            使用率: $usagePercentage%
            Bitmap缓存数: ${bitmapCache.size}
        """.trimIndent()
    }
    
    /**
     * 监控内存使用并记录日志
     */
    fun logMemoryUsage() {
        AppLogger.log(TAG, getMemorySummary())
    }
}
