package com.testcenter.qrscanner.repository

import com.testcenter.qrscanner.data.TestRecord
import com.testcenter.qrscanner.data.TestRecordDao
import kotlinx.coroutines.flow.Flow
import java.util.Date
import java.util.concurrent.TimeUnit

class TestRepository(private val testRecordDao: TestRecordDao) {
    
    fun getAllRecords(): Flow<List<TestRecord>> = testRecordDao.getAllRecords()
    
    suspend fun startTest(serialNumber: String, tester: String): TestRecord {
        // 检查是否已有未完成的测试
        val existingTest = testRecordDao.getActiveTestBySerial(serialNumber)
        if (existingTest != null) {
            // 已有活动测试，返回现有记录，允许继续添加零部件数据
            return existingTest
        }
        
        // 没有活动测试，创建新记录
        val newRecord = TestRecord(
            serialNumber = serialNumber,
            startTime = Date(),
            isCompleted = false,
            tester = tester
        )
        
        val id = testRecordDao.insertRecord(newRecord)
        return newRecord.copy(id = id)
    }
    
    suspend fun endTest(serialNumber: String): TestRecord {
        val activeTest = testRecordDao.getActiveTestBySerial(serialNumber)
            ?: throw IllegalStateException("未找到产品 $serialNumber 的活动测试")
        
        val endTime = Date()
        val durationMinutes = TimeUnit.MILLISECONDS.toMinutes(
            endTime.time - activeTest.startTime.time
        )
        
        val completedRecord = activeTest.copy(
            endTime = endTime,
            testDurationMinutes = durationMinutes,
            isCompleted = true,
            // 结束后需要重新上传（包含结束时间和时长）
            syncedToServer = false
        )
        
        testRecordDao.updateRecord(completedRecord)
        return completedRecord
    }
    
    suspend fun getRecordsBySerial(serialNumber: String): List<TestRecord> {
        return testRecordDao.getRecordsBySerial(serialNumber)
    }
    
    suspend fun getUnsyncedRecords(): List<TestRecord> {
        return testRecordDao.getUnsyncedRecords()
    }
    
    suspend fun markAsSynced(id: Long) {
        testRecordDao.markAsSynced(id)
    }
}
