package com.testcenter.qrscanner.network

import android.content.Context
import com.hierynomus.msdtyp.AccessMask
import com.hierynomus.msfscc.FileAttributes
import com.hierynomus.mssmb2.SMB2CreateDisposition
import com.hierynomus.mssmb2.SMB2ShareAccess
import com.hierynomus.smbj.SMBClient
import com.hierynomus.smbj.auth.AuthenticationContext
import com.hierynomus.smbj.connection.Connection
import com.hierynomus.smbj.session.Session
import com.hierynomus.smbj.share.DiskShare
import com.testcenter.qrscanner.data.TestRecord
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.*

class NetworkFileManager(
    private val context: Context,
    private val username: String? = null,
    private val password: String? = null,
    private val domain: String? = null
) {
    
    private val serverAddress = "172.16.30.10"
    private val shareName = "测试中心"
    private val targetPath = "3、下线台架测试 Offline test data/0.4 工程"
    
    private val preferencesManager = PreferencesManager(context)
    
    // 获取实际的登录凭据
    private fun getCredentials(): Triple<String, String, String> {
        val actualUsername = username ?: preferencesManager.getUsername() ?: ""
        val actualPassword = password ?: preferencesManager.getPassword() ?: ""
        val actualDomain = domain ?: preferencesManager.getDomain() ?: ""
        return Triple(actualUsername, actualPassword, actualDomain)
    }
    
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    private val fileNameFormat = SimpleDateFormat("yyyyMMdd", Locale.getDefault())
    
    suspend fun syncTestRecords(records: List<TestRecord>): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val (actualUsername, actualPassword, actualDomain) = getCredentials()
                val client = SMBClient()
                val connection: Connection = client.connect(serverAddress)
                val authContext = AuthenticationContext(actualUsername, actualPassword.toCharArray(), actualDomain)
                val session: Session = connection.authenticate(authContext)
                
                val share = session.connectShare(shareName) as DiskShare
                
                // 确保目标目录存在
                ensureDirectoryExists(share, targetPath)
                
                // 生成CSV文件内容
                val csvContent = generateCSVContent(records)
                val fileName = "test_records_${fileNameFormat.format(Date())}.csv"
                val filePath = "$targetPath/$fileName"
                
                // 写入文件
                writeToNetworkFile(share, filePath, csvContent)
                
                share.close()
                session.close()
                connection.close()
                client.close()
                
                true
            } catch (e: Exception) {
                e.printStackTrace()
                false
            }
        }
    }
    
    private fun ensureDirectoryExists(share: DiskShare, path: String) {
        val pathParts = path.split("/")
        var currentPath = ""
        
        for (part in pathParts) {
            currentPath = if (currentPath.isEmpty()) part else "$currentPath/$part"
            
            if (!share.folderExists(currentPath)) {
                share.mkdir(currentPath)
            }
        }
    }
    
    private fun writeToNetworkFile(share: DiskShare, filePath: String, content: String) {
        val file = share.openFile(
            filePath,
            setOf(AccessMask.GENERIC_WRITE),
            setOf(FileAttributes.FILE_ATTRIBUTE_NORMAL),
            SMB2ShareAccess.ALL,
            SMB2CreateDisposition.FILE_OVERWRITE_IF,
            null
        )
        
        file.use { f ->
            f.outputStream.use { os ->
                os.write(content.toByteArray(Charsets.UTF_8))
                os.flush()
            }
        }
    }
    
    private fun generateCSVContent(records: List<TestRecord>): String {
        val header = "序列号,开始时间,结束时间,测试时长(分钟),状态,创建时间\n"
        val rows = records.joinToString("\n") { record ->
            val endTimeStr = record.endTime?.let { dateFormat.format(it) } ?: ""
            val durationStr = record.testDurationMinutes?.toString() ?: ""
            val status = if (record.isCompleted) "已完成" else "测试中"
            
            "${record.serialNumber},${dateFormat.format(record.startTime)},$endTimeStr,$durationStr,$status,${dateFormat.format(record.createdAt)}"
        }
        
        return header + rows
    }

    private fun appendToNetworkFile(share: DiskShare, filePath: String, content: String) {
        // 读取现有内容
        val existingContent = try {
            val file = share.openFile(
                filePath,
                setOf(AccessMask.GENERIC_READ),
                setOf(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                SMB2ShareAccess.ALL,
                SMB2CreateDisposition.FILE_OPEN,
                null
            )
            file.use { f ->
                f.inputStream.use { inputStream ->
                    inputStream.readBytes().toString(Charsets.UTF_8)
                }
            }
        } catch (e: Exception) {
            ""
        }
        
        // 写入合并后的内容
        val combinedContent = existingContent + content
        writeToNetworkFile(share, filePath, combinedContent)
    }
    
    // 测试网络连接
    suspend fun testConnection(): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val (actualUsername, actualPassword, actualDomain) = getCredentials()
                val client = SMBClient()
                val connection: Connection = client.connect(serverAddress)
                val authContext = AuthenticationContext(actualUsername, actualPassword.toCharArray(), actualDomain)
                val session: Session = connection.authenticate(authContext)
                
                val share = session.connectShare(shareName) as DiskShare
                
                // 测试是否能访问目标路径
                val canAccess = share.folderExists("") // 测试根目录访问
                
                share.close()
                session.close()
                connection.close()
                client.close()
                
                canAccess
            } catch (e: Exception) {
                e.printStackTrace()
                false
            }
        }
    }
    
    // 备用方法：保存到本地存储，然后手动复制到网络位置
    suspend fun saveToLocalStorage(records: List<TestRecord>): String? {
        return withContext(Dispatchers.IO) {
            try {
                val csvContent = generateCSVContent(records)
                val fileName = "test_records_${fileNameFormat.format(Date())}.csv"
                val file = context.getExternalFilesDir(null)?.let { 
                    java.io.File(it, fileName)
                }
                
                file?.writeText(csvContent, Charsets.UTF_8)
                file?.absolutePath
            } catch (e: Exception) {
                e.printStackTrace()
                null
            }
        }
    }

    // 新增：查询产品记录
    suspend fun queryProductRecord(productSerial: String): ProductRecord? {
        return withContext(Dispatchers.IO) {
            try {
                val (actualUsername, actualPassword, actualDomain) = getCredentials()
                val client = SMBClient()
                val connection: Connection = client.connect(serverAddress)
                val authContext = AuthenticationContext(actualUsername, actualPassword.toCharArray(), actualDomain)
                val session: Session = connection.authenticate(authContext)
                
                val share = session.connectShare(shareName) as DiskShare
                
                // 查找今天的产品记录文件
                val fileName = "product_records_${fileNameFormat.format(Date())}.csv"
                val filePath = "$targetPath/$fileName"
                
                var result: ProductRecord? = null
                
                if (share.fileExists(filePath)) {
                    // 读取文件内容
                    val file = share.openFile(
                        filePath,
                        setOf(AccessMask.GENERIC_READ),
                        setOf(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                        SMB2ShareAccess.ALL,
                        SMB2CreateDisposition.FILE_OPEN,
                        null
                    )
                    
                    file.use { f ->
                        f.inputStream.use { inputStream ->
                            val content = inputStream.readBytes().toString(Charsets.UTF_8)
                            result = parseProductRecordFromCSV(content, productSerial)
                        }
                    }
                }
                
                share.close()
                session.close()
                connection.close()
                client.close()
                
                result
            } catch (e: Exception) {
                e.printStackTrace()
                null
            }
        }
    }

    private fun parseProductRecordFromCSV(csvContent: String, targetSerial: String): ProductRecord? {
        val lines = csvContent.split("\n")
        if (lines.size < 2) return null // 至少需要表头和一行数据
        
        // 跳过表头，查找匹配的产品序列号
        for (i in 1 until lines.size) {
            val line = lines[i].trim()
            if (line.isEmpty()) continue
            
            val columns = line.split(",")
            if (columns.size >= 9 && columns[0].trim() == targetSerial) {
                return ProductRecord(
                    productSerial = columns[0].trim(),
                    projectName = columns[1].trim(),
                    operator = columns[2].trim(),
                    scanTime = columns[3].trim(),
                    controlBoard = columns[4].trim(),
                    drivingCapacitor = columns[5].trim(),
                    pumpCapacitor = columns[6].trim(),
                    drivingPower = columns[7].trim(),
                    pumpPower = columns[8].trim()
                )
            }
        }
        
        return null
    }

    // 数据类：产品记录
    data class ProductRecord(
        val productSerial: String,
        val projectName: String,
        val operator: String,
        val scanTime: String,
        val controlBoard: String,
        val drivingCapacitor: String,
        val pumpCapacitor: String,
        val drivingPower: String,
        val pumpPower: String
    )
}
