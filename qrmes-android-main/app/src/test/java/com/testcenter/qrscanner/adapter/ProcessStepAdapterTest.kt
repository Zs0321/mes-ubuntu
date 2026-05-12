package com.testcenter.qrscanner.adapter

import com.testcenter.qrscanner.data.ProcessStep
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * 工序步骤适配器测试
 * 测试需求: 4.5
 */
class ProcessStepAdapterTest {

    private lateinit var processSteps: List<ProcessStep>

    @Before
    fun setup() {
        processSteps = listOf(
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
    }

    /**
     * 测试工序步骤数据结构
     */
    @Test
    fun testProcessStepDataStructure() {
        // Then: 验证工序步骤列表不为空
        assertNotNull("工序步骤列表不应该为null", processSteps)
        assertEquals("应该有2个工序步骤", 2, processSteps.size)
    }

    /**
     * 测试工序步骤数据内容
     */
    @Test
    fun testProcessStepDataContent() {
        // Given: 第一个工序步骤
        val firstStep = processSteps[0]
        
        // Then: 验证第一个工序步骤的数据
        assertEquals("process_001", firstStep.id)
        assertEquals("热套工序", firstStep.name)
        assertEquals("热套装配工序", firstStep.description)
        assertEquals(1, firstStep.order)
        assertTrue(firstStep.required)
        assertTrue(firstStep.photoRequired)
        assertEquals(300, firstStep.estimatedDuration)
    }

    /**
     * 测试工序步骤排序
     */
    @Test
    fun testProcessStepOrdering() {
        // When: 按order排序
        val sortedSteps = processSteps.sortedBy { it.order }
        
        // Then: 验证排序结果
        assertEquals("第一个应该是order=1", 1, sortedSteps[0].order)
        assertEquals("第二个应该是order=2", 2, sortedSteps[1].order)
        assertEquals("热套工序", sortedSteps[0].name)
        assertEquals("总装工序", sortedSteps[1].name)
    }

    /**
     * 测试工序步骤过滤
     */
    @Test
    fun testProcessStepFiltering() {
        // When: 过滤需要拍照的工序
        val photoRequiredSteps = processSteps.filter { it.photoRequired }
        
        // Then: 验证过滤结果
        assertEquals("所有工序都需要拍照", processSteps.size, photoRequiredSteps.size)
        
        // When: 过滤必需的工序
        val requiredSteps = processSteps.filter { it.required }
        
        // Then: 验证过滤结果
        assertEquals("所有工序都是必需的", processSteps.size, requiredSteps.size)
    }

    /**
     * 测试工序步骤时间计算
     */
    @Test
    fun testProcessStepTimeCalculation() {
        // When: 计算总时间
        val totalTime = processSteps.sumOf { it.estimatedDuration }
        
        // Then: 验证总时间
        assertEquals("总时间应该是900秒", 900, totalTime)
        
        // When: 计算平均时间
        val averageTime = totalTime / processSteps.size
        
        // Then: 验证平均时间
        assertEquals("平均时间应该是450秒", 450, averageTime)
    }

    /**
     * 测试空列表处理
     */
    @Test
    fun testEmptyProcessStepsList() {
        // Given: 空的工序步骤列表
        val emptySteps = emptyList<ProcessStep>()
        
        // Then: 验证空列表处理
        assertEquals("空列表大小应该为0", 0, emptySteps.size)
        assertTrue("空列表应该为空", emptySteps.isEmpty())
    }

    /**
     * 测试工序步骤属性验证
     */
    @Test
    fun testProcessStepValidation() {
        processSteps.forEach { step ->
            // Then: 验证每个工序步骤的基本属性
            assertNotNull("ID不应该为null", step.id)
            assertNotNull("名称不应该为null", step.name)
            assertNotNull("描述不应该为null", step.description)
            assertFalse("ID不应该为空", step.id.isEmpty())
            assertFalse("名称不应该为空", step.name.isEmpty())
            assertTrue("顺序应该大于0", step.order > 0)
            assertTrue("预计时间应该大于等于0", step.estimatedDuration >= 0)
        }
    }
}