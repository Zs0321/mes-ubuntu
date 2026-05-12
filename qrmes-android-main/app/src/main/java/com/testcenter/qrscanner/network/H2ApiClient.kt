package com.testcenter.qrscanner.network

import android.content.Context
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * H2数据库API客户端
 * 通过HTTP API与Python后台的H2数据库进行交互
 * 提供高性能的产品记录查询服务
 */
class H2ApiClient(
    private val context: Context
) {
    companion object {
        private const val TAG = "H2ApiClient"
        private const val CONNECTION_TIMEOUT = 10000 // 10秒
        private const val READ_TIMEOUT = 15000 // 15秒
    }

    private val preferencesManager = PreferencesManager(context)

    // 从统一的 API 基础 URL 派生 H2 API 地址
    private val baseUrl: String
        get() = "${preferencesManager.getApiBaseUrl()}/api/h2"
    
    /**
     * 查询产品记录
     */
    suspend fun queryProductRecord(productSerial: String): ProductRecord? = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = "$baseUrl/query/$productSerial"
            AppLogger.log(TAG, "[H2查询] 查询产品记录: $productSerial from $url")
            
            val response = makeHttpRequest(url, "GET")
            val jsonResponse = JSONObject(response)
            
            if (jsonResponse.getBoolean("success")) {
                val recordJson = jsonResponse.getJSONObject("record")
                val record = parseProductRecord(recordJson)
                AppLogger.log(TAG, "[H2查询] ✓ 成功从 H2数据库查询到记录: $productSerial")
                record
            } else {
                AppLogger.log(TAG, "[H2查询] 未在H2数据库中找到记录: $productSerial")
                null
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "[H2查询] H2数据库查询失败: $productSerial", e)
            null
        }
    }
    
    /**
     * 查询项目记录
     */
    suspend fun queryProjectRecords(projectName: String, limit: Int = 100): List<ProductRecord> = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = "$baseUrl/project/$projectName?limit=$limit"
            AppLogger.log(TAG, "Querying project records: $projectName")
            
            val response = makeHttpRequest(url, "GET")
            val jsonResponse = JSONObject(response)
            
            if (jsonResponse.getBoolean("success")) {
                val recordsArray = jsonResponse.getJSONArray("records")
                val records = mutableListOf<ProductRecord>()
                
                for (i in 0 until recordsArray.length()) {
                    val recordJson = recordsArray.getJSONObject(i)
                    parseProductRecord(recordJson)?.let { records.add(it) }
                }
                
                AppLogger.log(TAG, "Found ${records.size} records for project: $projectName")
                records
            } else {
                AppLogger.log(TAG, "No records found for project: $projectName")
                emptyList()
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Failed to query project records: $projectName", e)
            emptyList()
        }
    }
    
    /**
     * 获取数据库统计信息
     */
    suspend fun getDatabaseStats(): DatabaseStats? = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = "$baseUrl/stats"
            AppLogger.log(TAG, "Getting database stats")
            
            val response = makeHttpRequest(url, "GET")
            val jsonResponse = JSONObject(response)
            
            if (jsonResponse.getBoolean("success")) {
                val statsJson = jsonResponse.getJSONObject("stats")
                DatabaseStats(
                    totalRecords = statsJson.getInt("total_records"),
                    dbSize = statsJson.getLong("db_size"),
                    topProjects = parseTopProjects(statsJson.getJSONArray("top_projects"))
                )
            } else {
                null
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Failed to get database stats", e)
            null
        }
    }
    
    /**
     * 发现可同步的CSV文件
     */
    suspend fun discoverCsvFiles(): List<String> = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = "$baseUrl/sync/discover"
            AppLogger.log(TAG, "Discovering CSV files")
            
            val response = makeHttpRequest(url, "GET")
            val jsonResponse = JSONObject(response)
            
            if (jsonResponse.getBoolean("success")) {
                val filesArray = jsonResponse.getJSONArray("files")
                val files = mutableListOf<String>()
                
                for (i in 0 until filesArray.length()) {
                    files.add(filesArray.getString(i))
                }
                
                AppLogger.log(TAG, "Discovered ${files.size} CSV files")
                files
            } else {
                emptyList()
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Failed to discover CSV files", e)
            emptyList()
        }
    }
    
    /**
     * 同步所有CSV文件到H2数据库
     */
    suspend fun syncAllCsvFiles(): SyncResult = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = "$baseUrl/sync/all"
            AppLogger.log(TAG, "Syncing all CSV files")
            
            val response = makeHttpRequest(url, "POST")
            val jsonResponse = JSONObject(response)
            
            if (jsonResponse.getBoolean("success")) {
                val summary = jsonResponse.getJSONObject("summary")
                SyncResult(
                    success = true,
                    message = jsonResponse.getString("message"),
                    totalFiles = summary.getInt("total_files"),
                    successFiles = summary.getInt("success_files"),
                    totalRecords = summary.getInt("total_records")
                )
            } else {
                SyncResult(
                    success = false,
                    message = jsonResponse.getString("message"),
                    totalFiles = 0,
                    successFiles = 0,
                    totalRecords = 0
                )
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Failed to sync CSV files", e)
            SyncResult(
                success = false,
                message = e.message ?: "Unknown error",
                totalFiles = 0,
                successFiles = 0,
                totalRecords = 0
            )
        }
    }
    
    /**
     * 测试API连接
     */
    suspend fun testConnection(): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = "$baseUrl/health"
            AppLogger.log(TAG, "Testing H2 API connection: $url")
            
            val response = makeHttpRequest(url, "GET")
            val jsonResponse = JSONObject(response)
            val success = jsonResponse.getBoolean("success")
            
            AppLogger.log(TAG, if (success) "✓ H2 API connection successful" else "✗ H2 API connection failed")
            success
        } catch (e: Exception) {
            AppLogger.log(TAG, "H2 API connection test failed", e)
            false
        }
    }
    
    /**
     * 执行HTTP请求
     */
    private fun makeHttpRequest(urlString: String, method: String, requestBody: String? = null): String {
        val url = URL(urlString)
        val connection = url.openConnection() as HttpURLConnection
        
        try {
            connection.requestMethod = method
            connection.connectTimeout = CONNECTION_TIMEOUT
            connection.readTimeout = READ_TIMEOUT
            connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
            connection.setRequestProperty("Accept", "application/json")
            
            // 如果有请求体，写入数据
            if (requestBody != null && (method == "POST" || method == "PUT")) {
                connection.doOutput = true
                val writer = OutputStreamWriter(connection.outputStream, "UTF-8")
                writer.write(requestBody)
                writer.flush()
                writer.close()
            }
            
            val responseCode = connection.responseCode
            AppLogger.log(TAG, "HTTP $method to $urlString returned: $responseCode")
            
            if (responseCode in 200..299) {
                val inputStream = BufferedInputStream(connection.inputStream)
                val reader = BufferedReader(InputStreamReader(inputStream, "UTF-8"))
                val response = reader.use { it.readText() }
                return response
            } else {
                val errorStream = connection.errorStream
                val errorResponse = if (errorStream != null) {
                    BufferedReader(InputStreamReader(errorStream, "UTF-8")).use { it.readText() }
                } else {
                    "HTTP Error $responseCode"
                }
                throw Exception("HTTP $responseCode: $errorResponse")
            }
        } finally {
            connection.disconnect()
        }
    }
    
    /**
     * 解析产品记录
     */
    private fun parseProductRecord(json: JSONObject): ProductRecord? {
        return try {
            ProductRecord(
                productSerial = json.getString("product_serial"),
                productType = json.optString("product_type", ""),
                projectName = json.getString("project_name"),
                operator = json.getString("operator"),
                scanTime = json.optLong("scan_time", System.currentTimeMillis()),
                fileSource = json.optString("file_source", "H2数据库"),  // 兼容：没有则默认值
                rawData = json.optString("materials", json.optString("raw_data", "{}"))  // 兼容两种字段名
            )
        } catch (e: Exception) {
            AppLogger.log(TAG, "Failed to parse product record", e)
            null
        }
    }
    
    /**
     * 解析热门项目列表
     */
    private fun parseTopProjects(jsonArray: org.json.JSONArray): List<ProjectStats> {
        val projects = mutableListOf<ProjectStats>()
        for (i in 0 until jsonArray.length()) {
            val projectJson = jsonArray.getJSONObject(i)
            projects.add(
                ProjectStats(
                    name = projectJson.getString("name"),
                    count = projectJson.getInt("count")
                )
            )
        }
        return projects
    }
    
    /**
     * 产品记录数据类
     */
    data class ProductRecord(
        val productSerial: String,
        val productType: String,
        val projectName: String,
        val operator: String,
        val scanTime: Long,
        val fileSource: String,
        val rawData: String
    )
    
    /**
     * 数据库统计信息
     */
    data class DatabaseStats(
        val totalRecords: Int,
        val dbSize: Long,
        val topProjects: List<ProjectStats>
    )
    
    /**
     * 项目统计信息
     */
    data class ProjectStats(
        val name: String,
        val count: Int
    )
    
    /**
     * 同步结果
     */
    data class SyncResult(
        val success: Boolean,
        val message: String,
        val totalFiles: Int,
        val successFiles: Int,
        val totalRecords: Int
    )
}