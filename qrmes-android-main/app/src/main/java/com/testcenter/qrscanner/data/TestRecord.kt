package com.testcenter.qrscanner.data

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.Date

@Entity(tableName = "test_records")
data class TestRecord(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val serialNumber: String,
    val startTime: Date,
    val endTime: Date? = null,
    val testDurationMinutes: Long? = null,
    val isCompleted: Boolean = false,
    val createdAt: Date = Date(),
    val syncedToServer: Boolean = false,
    val tester: String = ""
)
