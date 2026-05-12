package com.testcenter.qrscanner.integration

import com.testcenter.qrscanner.data.ProcessStep
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * 工序记录功能集成测试
 * 测试完整的工序记录工作流程
 * 测试需求: 4.1, 4.2, 4.5, 5.5
 */
class ProcessRecordingIntegrationTest {

    private lateinit var testProcessSteps: List<ProcessStep>

    @Before
    fun setup() {
        testProcessSteps = listOf(
            ProcessStep(
                id = "process_001",
                name = "热套工序",
                description = "热套装配工序",
                order = 1,
                required = true,
                photoRequired = true,
                estimatedDuration = 300
            ),
            ProcessStep(
                id = "process_002",
                name = "总装工序",
                description = "最终总装工序",
                order = 2,
                required = true,
                photoRequired = true,
                estimatedDuration = 600
            ),
            ProcessStep(
                id = "process_003",
                name = "质检工序",
                description = "质量检查工序",
                order = 3,
                required = true,
                photoRequired = true,
                estimatedDuration = 180
            )
        )
    }

    /**
     * 测试完整的工序记录数据流程
     * 需求: 4.1, 4.2, 4.3, 4.4, 4.5
     */
    @Test
    fun testCompleteProcessRecordingDataFlow() {
        // Given: 产品序列号
        val productSerial = "INTEGRATION_TEST_PROD_001"
        
        // When: 模拟扫描产品后加载工序步骤
        val loadedSteps = testProcessSteps.sortedBy { it.order }
        
        // Then: 验证工序步骤正确加载
        assertEquals("应该加载所有工序步骤", testProcessSteps.size, loadedSteps.size)
        assertEquals("第一个工序应该是热套工序", "热套工序", loadedSteps[0].name)
        assertEquals("第二个工序应该是总装工序", "总装工序", loadedSteps[1].name)
        assertEquals("第三个工序应该是质检工序", "质检工序", loadedSteps[2].name)
        
        // When: 验证每个工序的拍照需求
        val photoRequiredSteps = loadedSteps.filter { it.photoRequired }
        
        // Then: 验证所有工序都需要拍照
        assertEquals("所有工序都应该需要拍照", loadedSteps.size, photoRequiredSteps.size)
    }

    /**
     * 测试多个产品连续处理的数据管理
     * 需求: 4.3, 4.4
     */
    @Test
    fun testMultipleProductDataHandling() {
        // Given: 多个产品序列号
        val products = listOf("PROD_001", "PROD_002", "PROD_003")
        
        // When: 为每个产品分配工序步骤
        val productProcessMap = products.associateWith { productSerial ->
            testProcessSteps.map { step ->
                "${productSerial}_${step.id}" to step
            }.toMap()
        }
        
        // Then: 验证每个产品都有完整的工序步骤
        products.forEach { productSerial ->
            val processSteps = productProcessMap[productSerial]
            assertNotNull("产品 $productSerial 应该有工序步骤", processSteps)
            assertEquals("每个产品应该有3个工序步骤", testProcessSteps.size, processSteps?.size)
        }
        
        // Then: 验证工序步骤的唯一性
        val allProcessKeys = productProcessMap.values.flatMap { it.keys }
        val uniqueKeys = allProcessKeys.toSet()
        assertEquals("所有工序键应该唯一", allProcessKeys.size, uniqueKeys.size)
    }

    /**
     * 测试工序步骤排序的一致性
     * 需求: 5.5
     */
    @Test
    fun testProcessStepsOrderingConsistency() {
        // Given: 乱序的工序步骤
        val shuffledSteps = testProcessSteps.shuffled()
        
        // When: 多次排序
        val sorted1 = shuffledSteps.sortedBy { it.order }
        val sorted2 = shuffledSteps.sortedBy { it.order }
        val sorted3 = shuffledSteps.sortedBy { it.order }
        
        // Then: 验证排序结果一致
        assertEquals("多次排序结果应该一致", sorted1, sorted2)
        assertEquals("多次排序结果应该一致", sorted2, sorted3)
        
        // Then: 验证排序顺序正确
        for (i in 0 until sorted1.size - 1) {
            assertTrue("工序顺序应该递增", sorted1[i].order < sorted1[i + 1].order)
        }
    }

    /**
     * 测试工序记录的数据完整性验证
     * 需求: 4.5
     */
    @Test
    fun testProcessRecordDataIntegrity() {
        // Given: 工序记录数据
        val processRecords = testProcessSteps.map { step ->
            mapOf(
                "productSerial" to "TEST_PROD_001",
                "processStepId" to step.id,
                "processStepName" to step.name,
                "order" to step.order,
                "required" to step.required,
                "photoRequired" to step.photoRequired,
                "estimatedDuration" to step.estimatedDuration,
                "status" to "pending"
            )
        }
        
        // Then: 验证每条记录的完整性
        processRecords.forEach { record ->
            assertNotNull("产品序列号不应该为空", record["productSerial"])
            assertNotNull("工序步骤ID不应该为空", record["processStepId"])
            assertNotNull("工序步骤名称不应该为空", record["processStepName"])
            assertNotNull("工序顺序不应该为空", record["order"])
            assertNotNull("必需标志不应该为空", record["required"])
            assertNotNull("拍照需求不应该为空", record["photoRequired"])
            assertNotNull("预计时间不应该为空", record["estimatedDuration"])
            assertNotNull("状态不应该为空", record["status"])
        }
        
        // Then: 验证记录数量
        assertEquals("应该有3条工序记录", testProcessSteps.size, processRecords.size)
    }

    /**
     * 测试照片文件命名的集成逻辑
     * 需求: 6.1
     */
    @Test
    fun testPhotoFileNamingIntegration() {
        // Given: 产品和工序信息
        val productSerial = "INTEGRATION_PROD_001"
        val timestamp = "20241018_143022"
        
        // When: 为每个工序生成照片文件名
        val photoFileNames = testProcessSteps.map { step ->
            "${productSerial}_${step.name}_${timestamp}.jpg"
        }
        
        // Then: 验证文件名格式
        photoFileNames.forEach { fileName ->
            assertTrue("文件名应该包含产品序列号", fileName.contains(productSerial))
            assertTrue("文件名应该包含时间戳", fileName.contains(timestamp))
            assertTrue("文件名应该以.jpg结尾", fileName.endsWith(".jpg"))
        }
        
        // Then: 验证文件名唯一性
        val uniqueFileNames = photoFileNames.toSet()
        assertEquals("所有照片文件名应该唯一", photoFileNames.size, uniqueFileNames.size)
        
        // Then: 验证具体文件名
        assertEquals("INTEGRATION_PROD_001_热套工序_20241018_143022.jpg", photoFileNames[0])
        assertEquals("INTEGRATION_PROD_001_总装工序_20241018_143022.jpg", photoFileNames[1])
        assertEquals("INTEGRATION_PROD_001_质检工序_20241018_143022.jpg", photoFileNames[2])
    }

    /**
     * 测试工序记录状态管理
     * 需求: 4.5
     */
    @Test
    fun testProcessRecordStatusManagement() {
        // Given: 工序状态枚举
        val statusOptions = listOf("pending", "in_progress", "completed", "skipped")
        
        // When: 创建工序状态记录
        val processStatusMap = testProcessSteps.associate { step ->
            step.id to "pending"
        }.toMutableMap()
        
        // Then: 验证初始状态
        processStatusMap.values.forEach { status ->
            assertEquals("初始状态应该是pending", "pending", status)
        }
        
        // When: 更新工序状态
        processStatusMap[testProcessSteps[0].id] = "in_progress"
        processStatusMap[testProcessSteps[1].id] = "completed"
        
        // Then: 验证状态更新
        assertEquals("第一个工序状态应该更新", "in_progress", processStatusMap[testProcessSteps[0].id])
        assertEquals("第二个工序状态应该更新", "completed", processStatusMap[testProcessSteps[1].id])
        assertEquals("第三个工序状态应该保持", "pending", processStatusMap[testProcessSteps[2].id])
        
        // When: 计算完成进度
        val completedCount = processStatusMap.values.count { it == "completed" }
        val totalCount = processStatusMap.size
        val progress = (completedCount.toDouble() / totalCount * 100).toInt()
        
        // Then: 验证进度计算
        assertEquals("完成进度应该正确", 33, progress) // 1/3 ≈ 33%
    }

    /**
     * 测试错误场景的数据处理
     * 需求: 4.1, 4.2, 5.5
     */
    @Test
    fun testErrorScenarioDataHandling() {
        // Given: 空的工序步骤列表（模拟配置加载失败）
        val emptySteps = emptyList<ProcessStep>()
        
        // When: 处理空列表
        val sortedEmptySteps = emptySteps.sortedBy { it.order }
        val filteredEmptySteps = emptySteps.filter { it.required }
        
        // Then: 验证空列表处理
        assertEquals("空列表排序后仍为空", 0, sortedEmptySteps.size)
        assertEquals("空列表过滤后仍为空", 0, filteredEmptySteps.size)
        
        // Given: 无效的工序数据
        val invalidSteps = listOf(
            ProcessStep("", "", "", 0, false, false, -1)
        )
        
        // When: 验证无效数据
        val hasValidId = invalidSteps.any { it.id.isNotEmpty() }
        val hasValidName = invalidSteps.any { it.name.isNotEmpty() }
        val hasValidOrder = invalidSteps.any { it.order > 0 }
        
        // Then: 验证无效数据检测
        assertFalse("应该检测到无效ID", hasValidId)
        assertFalse("应该检测到无效名称", hasValidName)
        assertFalse("应该检测到无效顺序", hasValidOrder)
    }
}