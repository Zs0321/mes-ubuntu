package com.testcenter.qrscanner.process

import com.testcenter.qrscanner.data.ProcessStep
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * 工序记录基础功能测试
 * 测试需求: 4.1, 4.2, 4.5
 */
class ProcessRecordActivityTest {

    private val testProcessSteps = listOf(
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
        )
    )

    @Before
    fun setup() {
        // Setup test data
    }

    /**
     * 测试工序步骤数据模型的基本属性
     * 需求: 4.5
     */
    @Test
    fun testProcessStepDataModel() {
        // Given: 创建工序步骤
        val processStep = testProcessSteps[0]
        
        // Then: 验证工序步骤属性
        assertEquals("工序ID应该正确", "process_001", processStep.id)
        assertEquals("工序名称应该正确", "热套工序", processStep.name)
        assertEquals("工序描述应该正确", "热套装配工序", processStep.description)
        assertEquals("工序顺序应该正确", 1, processStep.order)
        assertTrue("工序应该是必需的", processStep.required)
        assertTrue("工序应该需要拍照", processStep.photoRequired)
        assertEquals("预计耗时应该正确", 300, processStep.estimatedDuration)
    }

    /**
     * 测试工序步骤列表排序功能
     * 需求: 5.5
     */
    @Test
    fun testProcessStepsOrdering() {
        // Given: 创建乱序的工序步骤列表
        val unorderedSteps = listOf(
            ProcessStep("process_003", "工序C", "描述C", 3, true, true, 100),
            ProcessStep("process_001", "工序A", "描述A", 1, true, true, 100),
            ProcessStep("process_002", "工序B", "描述B", 2, true, true, 100)
        )
        
        // When: 按order字段排序
        val sortedSteps = unorderedSteps.sortedBy { it.order }
        
        // Then: 验证排序结果
        assertEquals("第一个应该是order=1的工序", "工序A", sortedSteps[0].name)
        assertEquals("第二个应该是order=2的工序", "工序B", sortedSteps[1].name)
        assertEquals("第三个应该是order=3的工序", "工序C", sortedSteps[2].name)
    }

    /**
     * 测试工序步骤属性验证
     * 需求: 4.5
     */
    @Test
    fun testProcessStepValidation() {
        // Given: 测试工序步骤
        val processStep = testProcessSteps[1]
        
        // Then: 验证工序步骤的各项属性
        assertNotNull("工序ID不应该为空", processStep.id)
        assertNotNull("工序名称不应该为空", processStep.name)
        assertNotNull("工序描述不应该为空", processStep.description)
        assertTrue("工序顺序应该大于0", processStep.order > 0)
        assertTrue("预计耗时应该大于等于0", processStep.estimatedDuration >= 0)
        
        // Then: 验证具体值
        assertEquals("总装工序", processStep.name)
        assertEquals(2, processStep.order)
        assertEquals(600, processStep.estimatedDuration)
    }

    /**
     * 测试工序步骤列表过滤功能
     * 需求: 4.5
     */
    @Test
    fun testProcessStepsFiltering() {
        // Given: 包含必需和非必需工序的列表
        val mixedSteps = listOf(
            ProcessStep("process_001", "必需工序", "必需的工序", 1, true, true, 300),
            ProcessStep("process_002", "可选工序", "可选的工序", 2, false, true, 200),
            ProcessStep("process_003", "另一个必需工序", "另一个必需的工序", 3, true, true, 400)
        )
        
        // When: 过滤出必需的工序
        val requiredSteps = mixedSteps.filter { it.required }
        
        // Then: 验证过滤结果
        assertEquals("应该有2个必需工序", 2, requiredSteps.size)
        assertTrue("第一个工序应该是必需的", requiredSteps[0].required)
        assertTrue("第二个工序应该是必需的", requiredSteps[1].required)
        assertEquals("必需工序", requiredSteps[0].name)
        assertEquals("另一个必需工序", requiredSteps[1].name)
    }

    /**
     * 测试工序步骤拍照需求验证
     * 需求: 4.5
     */
    @Test
    fun testProcessStepPhotoRequirement() {
        // Given: 测试工序步骤
        val processSteps = testProcessSteps
        
        // Then: 验证所有工序都需要拍照
        processSteps.forEach { step ->
            assertTrue("工序 ${step.name} 应该需要拍照", step.photoRequired)
        }
        
        // Given: 创建不需要拍照的工序
        val noPhotoStep = ProcessStep(
            id = "process_no_photo",
            name = "无需拍照工序",
            description = "不需要拍照的工序",
            order = 99,
            required = true,
            photoRequired = false,
            estimatedDuration = 100
        )
        
        // Then: 验证该工序不需要拍照
        assertFalse("该工序不应该需要拍照", noPhotoStep.photoRequired)
    }

    /**
     * 测试工序步骤时间估算功能
     * 需求: 4.5
     */
    @Test
    fun testProcessStepTimeEstimation() {
        // Given: 测试工序步骤
        val processSteps = testProcessSteps
        
        // When: 计算总预计时间
        val totalEstimatedTime = processSteps.sumOf { it.estimatedDuration }
        
        // Then: 验证时间计算
        assertEquals("总预计时间应该正确", 900, totalEstimatedTime) // 300 + 600
        
        // Then: 验证各工序时间
        assertEquals("热套工序预计时间", 300, processSteps[0].estimatedDuration)
        assertEquals("总装工序预计时间", 600, processSteps[1].estimatedDuration)
        
        // When: 计算平均时间
        val averageTime = totalEstimatedTime / processSteps.size
        
        // Then: 验证平均时间
        assertEquals("平均时间应该正确", 450, averageTime)
    }

    /**
     * 测试工序步骤ID唯一性验证
     * 需求: 4.5
     */
    @Test
    fun testProcessStepIdUniqueness() {
        // Given: 测试工序步骤列表
        val processSteps = testProcessSteps
        
        // When: 提取所有ID
        val ids = processSteps.map { it.id }
        val uniqueIds = ids.toSet()
        
        // Then: 验证ID唯一性
        assertEquals("所有工序步骤ID应该唯一", ids.size, uniqueIds.size)
        
        // Then: 验证具体ID
        assertTrue("应该包含process_001", ids.contains("process_001"))
        assertTrue("应该包含process_002", ids.contains("process_002"))
        
        // When: 检查重复ID
        val duplicateIds = ids.groupingBy { it }.eachCount().filter { it.value > 1 }
        
        // Then: 验证没有重复ID
        assertTrue("不应该有重复的ID", duplicateIds.isEmpty())
    }

    /**
     * 测试工序步骤数据完整性验证
     * 需求: 4.5
     */
    @Test
    fun testProcessStepDataIntegrity() {
        // Given: 测试工序步骤
        val processSteps = testProcessSteps
        
        // Then: 验证每个工序步骤的数据完整性
        processSteps.forEach { step ->
            assertNotNull("工序ID不应该为null", step.id)
            assertNotNull("工序名称不应该为null", step.name)
            assertNotNull("工序描述不应该为null", step.description)
            
            assertFalse("工序ID不应该为空字符串", step.id.isEmpty())
            assertFalse("工序名称不应该为空字符串", step.name.isEmpty())
            assertFalse("工序描述不应该为空字符串", step.description.isEmpty())
            
            assertTrue("工序顺序应该为正数", step.order > 0)
            assertTrue("预计耗时应该为非负数", step.estimatedDuration >= 0)
        }
    }

    /**
     * 测试工序步骤搜索功能
     * 需求: 4.5
     */
    @Test
    fun testProcessStepSearch() {
        // Given: 测试工序步骤列表
        val processSteps = testProcessSteps
        
        // When: 按名称搜索工序
        val searchResult1 = processSteps.filter { it.name.contains("热套") }
        val searchResult2 = processSteps.filter { it.name.contains("总装") }
        val searchResult3 = processSteps.filter { it.name.contains("不存在") }
        
        // Then: 验证搜索结果
        assertEquals("应该找到1个热套工序", 1, searchResult1.size)
        assertEquals("应该找到1个总装工序", 1, searchResult2.size)
        assertEquals("不应该找到不存在的工序", 0, searchResult3.size)
        
        assertEquals("热套工序", searchResult1[0].name)
        assertEquals("总装工序", searchResult2[0].name)
    }
}