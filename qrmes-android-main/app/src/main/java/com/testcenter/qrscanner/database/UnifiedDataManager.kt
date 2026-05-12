package com.testcenter.qrscanner.database

import android.content.Context
import com.testcenter.qrscanner.data.ProductRecord
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 统一数据管理器（仅 API 模式）
 */
class UnifiedDataManager(
    private val context: Context,
    private val preferencesManager: PreferencesManager
) {
    companion object {
        private const val TAG = "UnifiedDataManager"

        @Volatile
        private var instance: UnifiedDataManager? = null

        fun getInstance(context: Context): UnifiedDataManager {
            return instance ?: synchronized(this) {
                val prefs = PreferencesManager(context.applicationContext)
                instance ?: UnifiedDataManager(context.applicationContext, prefs).also { instance = it }
            }
        }
    }

    private val dataValidator = DataValidator(context)

    suspend fun saveRecord(record: ProductRecord, skipValidation: Boolean = false): Boolean {
        if (!skipValidation) {
            val (fixedRecord, validationResult) = dataValidator.validateAndFix(record)

            if (validationResult.hasErrors()) {
                AppLogger.log(TAG, "Record validation failed: ${validationResult.errors.joinToString("; ")}")
                return false
            }

            if (validationResult.hasWarnings()) {
                AppLogger.log(TAG, "Record validation warnings: ${validationResult.warnings.joinToString("; ")}")
            }

            return saveToAPI(fixedRecord)
        }

        return saveToAPI(record)
    }

    suspend fun getRecord(productSerial: String): ProductRecord? {
        return queryFromAPI(productSerial)
    }

    suspend fun getRecordsByProject(projectName: String): List<ProductRecord> {
        return emptyList()
    }

    suspend fun getRecordsByOperator(operator: String): List<ProductRecord> {
        return emptyList()
    }

    suspend fun testConnection(): Boolean {
        return try {
            val apiBaseUrl = preferencesManager.getApiBaseUrl()
            val url = "$apiBaseUrl/api/h2/health"
            val connection = java.net.URL(url).openConnection() as java.net.HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 5000
            connection.readTimeout = 5000
            connection.responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun getStats(): Map<String, Any> {
        return mapOf(
            "mode" to "API Only",
            "total_records" to 0
        )
    }

    private suspend fun saveToAPI(record: ProductRecord): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val apiBaseUrl = preferencesManager.getApiBaseUrl()
            val url = "$apiBaseUrl/api/h2/save"

            val requestData = org.json.JSONObject().apply {
                put("product_serial", record.productSerial)
                put("product_type", record.productType)
                put("project_name", record.projectName)
                put("operator", record.operator)
                put("scan_time", record.scanTime)
                put("materials", org.json.JSONObject(record.materials))
            }

            val connection = java.net.URL(url).openConnection() as java.net.HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true
            connection.connectTimeout = 10000
            connection.readTimeout = 10000

            connection.outputStream.use { os ->
                os.write(requestData.toString().toByteArray(Charsets.UTF_8))
            }

            val responseCode = connection.responseCode
            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                val jsonResponse = org.json.JSONObject(response)
                val success = jsonResponse.optBoolean("success", false)

                if (success) {
                    AppLogger.log(TAG, "API save success: ${record.productSerial}")
                    true
                } else {
                    val message = jsonResponse.optString("message", "unknown error")
                    AppLogger.log(TAG, "API save failed: $message")
                    false
                }
            } else {
                AppLogger.log(TAG, "API save failed: HTTP $responseCode")
                false
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "API save error: ${e.message}", e)
            false
        }
    }

    private suspend fun queryFromAPI(productSerial: String): ProductRecord? = withContext(Dispatchers.IO) {
        return@withContext try {
            val apiBaseUrl = preferencesManager.getApiBaseUrl()
            val url = "$apiBaseUrl/api/h2/query/$productSerial"

            val connection = java.net.URL(url).openConnection() as java.net.HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 10000
            connection.readTimeout = 10000

            val responseCode = connection.responseCode
            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                val jsonResponse = org.json.JSONObject(response)
                val success = jsonResponse.optBoolean("success", false)

                if (success) {
                    val recordJson = jsonResponse.getJSONObject("record")

                    val materialsStr = recordJson.optString("materials", "{}")
                    val materialsJson = org.json.JSONObject(materialsStr)
                    val materials = mutableMapOf<String, String>()
                    materialsJson.keys().forEach { key ->
                        materials[key] = materialsJson.optString(key, "")
                    }

                    ProductRecord(
                        productSerial = recordJson.getString("product_serial"),
                        productType = recordJson.getString("product_type"),
                        projectName = recordJson.getString("project_name"),
                        operator = recordJson.getString("operator"),
                        scanTime = recordJson.getLong("scan_time"),
                        materials = materials
                    )
                } else {
                    null
                }
            } else {
                null
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "API query error: ${e.message}", e)
            null
        }
    }
}
