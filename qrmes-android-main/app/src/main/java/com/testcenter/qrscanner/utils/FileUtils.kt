package com.testcenter.qrscanner.utils

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File
import java.io.FileOutputStream

/**
 * 文件操作工具类
 */
object FileUtils {

    /**
     * 获取文件大小（字节）
     */
    fun getFileSize(context: Context, uri: Uri): Long {
        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
            if (sizeIndex >= 0 && cursor.moveToFirst()) {
                return cursor.getLong(sizeIndex)
            }
        }
        return 0
    }

    /**
     * 获取文件名
     */
    fun getFileName(context: Context, uri: Uri): String {
        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (nameIndex >= 0 && cursor.moveToFirst()) {
                return cursor.getString(nameIndex)
            }
        }
        return "unknown.pdf"
    }

    /**
     * 将 Uri 复制到缓存目录，返回临时 File
     */
    fun uriToFile(context: Context, uri: Uri): File {
        val fileName = getFileName(context, uri)
        val tempFile = File(context.cacheDir, fileName)

        context.contentResolver.openInputStream(uri)?.use { input ->
            FileOutputStream(tempFile).use { output ->
                input.copyTo(output)
            }
        }

        return tempFile
    }

    /**
     * 验证文件大小是否在限制内
     */
    fun validateFileSize(sizeBytes: Long, maxSizeMB: Int = 20): Boolean {
        val maxSizeBytes = maxSizeMB.toLong() * 1024 * 1024
        return sizeBytes in 1..maxSizeBytes
    }
}
