package com.testcenter.qrscanner.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface TestRecordDao {
    @Query("SELECT * FROM test_records ORDER BY createdAt DESC")
    fun getAllRecords(): Flow<List<TestRecord>>
    
    @Query("SELECT * FROM test_records WHERE serialNumber = :serialNumber AND isCompleted = 0 LIMIT 1")
    suspend fun getActiveTestBySerial(serialNumber: String): TestRecord?
    
    @Query("SELECT * FROM test_records WHERE serialNumber = :serialNumber ORDER BY createdAt DESC")
    suspend fun getRecordsBySerial(serialNumber: String): List<TestRecord>
    
    @Insert
    suspend fun insertRecord(record: TestRecord): Long
    
    @Update
    suspend fun updateRecord(record: TestRecord)
    
    @Delete
    suspend fun deleteRecord(record: TestRecord)
    
    @Query("SELECT * FROM test_records WHERE syncedToServer = 0")
    suspend fun getUnsyncedRecords(): List<TestRecord>
    
    @Query("UPDATE test_records SET syncedToServer = 1 WHERE id = :id")
    suspend fun markAsSynced(id: Long)
}
