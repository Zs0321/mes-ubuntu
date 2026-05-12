package com.testcenter.qrscanner.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.asLiveData
import androidx.lifecycle.viewModelScope
import com.testcenter.qrscanner.data.TestDatabase
import com.testcenter.qrscanner.data.TestRecord
import com.testcenter.qrscanner.repository.TestRepository
import com.testcenter.qrscanner.service.SyncService
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val repository: TestRepository
    private val syncService = SyncService(application)

    private val _scanResult = MutableLiveData<String>()
    val scanResult: LiveData<String> = _scanResult

    private val _testResult = MutableLiveData<TestRecord>()
    val testResult: LiveData<TestRecord> = _testResult

    private val _errorMessage = MutableLiveData<String>()
    val errorMessage: LiveData<String> = _errorMessage

    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> = _isLoading

    private val _selectedTester = MutableLiveData<String>("")
    val selectedTester: LiveData<String> = _selectedTester

    private val _pendingSerials = MutableLiveData<List<String>>(emptyList())
    val pendingSerials: LiveData<List<String>> = _pendingSerials

    init {
        val database = TestDatabase.getDatabase(application)
        repository = TestRepository(database.testRecordDao())
    }

    val allRecords: LiveData<List<TestRecord>> = repository.getAllRecords().asLiveData()

    fun setSelectedTester(name: String) {
        _selectedTester.value = name
    }

    fun onQRCodeScanned(serialNumber: String) {
        // 新流程：仅更新扫描结果，由界面决定后续动作（开始/查询/停止）
        _scanResult.value = serialNumber
    }

    // 兼容旧批量流程所需的辅助方法保留（若需要手动加入待开始）
    private fun handleQRCode(serialNumber: String) { /* 不再自动处理 */ }

    fun startSingleTest(serialNumber: String) {
        val tester = _selectedTester.value?.trim().orEmpty()
        if (tester.isEmpty()) {
            _errorMessage.value = "请先选择测试人员"
            return
        }
        viewModelScope.launch {
            try {
                _isLoading.value = true
                val record = repository.startTest(serialNumber, tester)
                _testResult.value = record
                _errorMessage.value = "已开始测试：$serialNumber（测试人员：$tester）"
                // 同步CSV
                syncService.syncToNetworkShare { success, count ->
                    _errorMessage.value = if (success) {
                        if (count > 0) "上传成功（${count}条）" else "无新数据需要上传"
                    } else {
                        "上传失败，请检查网络或账号"
                    }
                }
            } catch (e: Exception) {
                _errorMessage.value = "开始测试失败 $serialNumber：${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun endSingleTest(serialNumber: String) {
        viewModelScope.launch {
            try {
                _isLoading.value = true
                val completed = repository.endTest(serialNumber)
                _testResult.value = completed
                _errorMessage.value = "测试完成！产品 $serialNumber 测试时长：${completed.testDurationMinutes} 分钟"
                // 同步CSV
                syncService.syncToNetworkShare { success, count ->
                    _errorMessage.value = if (success) {
                        if (count > 0) "上传成功（${count}条）" else "无新数据需要上传"
                    } else {
                        "上传失败，请检查网络或账号"
                    }
                }
            } catch (e: Exception) {
                _errorMessage.value = "结束测试失败 $serialNumber：${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun removePendingSerial(serialNumber: String) {
        val current = _pendingSerials.value ?: emptyList()
        _pendingSerials.value = current.filterNot { it == serialNumber }
    }

    fun clearPending() {
        _pendingSerials.value = emptyList()
    }

    // 添加待开始测试的序列号（支持换行、逗号、空格、分号、制表符分隔）
    fun addPendingSerials(input: String) {
        val tokens = input
            .replace('\r', '\n')
            .split('\n', ',', '，', ' ', '\t', ';', '；')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
        if (tokens.isEmpty()) return
        val current = _pendingSerials.value ?: emptyList()
        val merged = (current + tokens).map { it.trim() }.filter { it.isNotEmpty() }.distinct()
        _pendingSerials.value = merged
        _errorMessage.value = "已添加 ${tokens.size} 条待开始序列号"
    }

    fun startTests() {
        val tester = _selectedTester.value?.trim().orEmpty()
        val serials = _pendingSerials.value ?: emptyList()
        if (tester.isEmpty()) {
            _errorMessage.value = "请先选择测试人员"
            return
        }
        if (serials.isEmpty()) {
            _errorMessage.value = "待开始列表为空"
            return
        }
        viewModelScope.launch {
            try {
                _isLoading.value = true
                for (sn in serials) {
                    try {
                        val record = repository.startTest(sn, tester)
                        _testResult.postValue(record)
                    } catch (ie: Exception) {
                        _errorMessage.postValue("开始测试失败 $sn：${ie.message}")
                    }
                }
                _errorMessage.value = "已开始测试：${serials.joinToString(", ")}（测试人员：$tester）"
                clearPending()
                // 同步
                syncService.syncToNetworkShare { success, count ->
                    _errorMessage.value = if (success) {
                        if (count > 0) "上传成功（${count}条）" else "无新数据需要上传"
                    } else {
                        "上传失败，请检查网络或账号"
                    }
                }
            } catch (e: Exception) {
                _errorMessage.value = "错误：${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }
    
    fun clearMessages() {
        _errorMessage.value = ""
        _scanResult.value = ""
    }
}
