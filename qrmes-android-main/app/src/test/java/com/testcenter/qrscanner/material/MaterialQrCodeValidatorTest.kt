package com.testcenter.qrscanner.material

import com.testcenter.qrscanner.data.MaterialInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MaterialQrCodeValidatorTest {

    @Test
    fun `pcb rule accepts matching version`() {
        val material = MaterialInfo(
            name = "控制板",
            partNumber = "W12020036.A0",
            qrRuleType = "pcb",
            expectedVersion = "A0"
        )

        val result = MaterialQrCodeValidator.validate(
            material = material,
            scannedCode = "W12020036.A02546011427",
            forceVersionCheck = false
        )

        assertTrue(result.isValid)
        assertEquals("A0", result.detectedVersion)
    }

    @Test
    fun `pcb rule rejects version mismatch`() {
        val material = MaterialInfo(
            name = "控制板",
            partNumber = "W12020036.A0",
            qrRuleType = "pcb",
            expectedVersion = "A0"
        )

        val result = MaterialQrCodeValidator.validate(
            material = material,
            scannedCode = "W12020036.B12546011427",
            forceVersionCheck = false
        )

        assertFalse(result.isValid)
        assertTrue(result.message.orEmpty().contains("版本"))
    }

    @Test
    fun `missing configured version is allowed when force check disabled`() {
        val material = MaterialInfo(
            name = "控制板",
            partNumber = "W12020036.A0",
            qrRuleType = "pcb",
            expectedVersion = ""
        )

        val result = MaterialQrCodeValidator.validate(
            material = material,
            scannedCode = "W12020036.B12546011427",
            forceVersionCheck = false
        )

        assertTrue(result.isValid)
    }

    @Test
    fun `missing configured version is rejected when force check enabled`() {
        val material = MaterialInfo(
            name = "控制板",
            partNumber = "W12020036.A0",
            qrRuleType = "pcb",
            expectedVersion = ""
        )

        val result = MaterialQrCodeValidator.validate(
            material = material,
            scannedCode = "W12020036.A02546011427",
            forceVersionCheck = true
        )

        assertFalse(result.isValid)
        assertTrue(result.message.orEmpty().contains("未配置版本"))
    }

    @Test
    fun `motor rule stays compatible when version control is not configured`() {
        val material = MaterialInfo(
            name = "定子",
            partNumber = "TZ180XQS17-307-0042",
            qrRuleType = "motor",
            expectedVersion = ""
        )

        val result = MaterialQrCodeValidator.validate(
            material = material,
            scannedCode = "TZ180004226020050",
            forceVersionCheck = false
        )

        assertTrue(result.isValid)
        assertEquals(null, result.detectedVersion)
    }

    @Test
    fun `motor rule rejects configured version because parser is unsupported`() {
        val material = MaterialInfo(
            name = "定子",
            partNumber = "TZ180XQS17-307-0042",
            qrRuleType = "motor",
            expectedVersion = "A0"
        )

        val result = MaterialQrCodeValidator.validate(
            material = material,
            scannedCode = "TZ180004226020050",
            forceVersionCheck = false
        )

        assertFalse(result.isValid)
        assertTrue(result.message.orEmpty().contains("暂不支持版本号检查"))
    }
}
