package com.testcenter.qrscanner.scanner

import com.google.mlkit.vision.barcode.common.Barcode
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HighResScanConfigTest {

    @Test
    fun `default config enables zoom assistance for hard codes`() {
        val config = HighResScanConfig.default()

        assertTrue(config.enableAutoZoom)
        assertTrue(config.enablePotentialBarcodes)
        assertArrayEquals(
            intArrayOf(Barcode.FORMAT_QR_CODE, Barcode.FORMAT_DATA_MATRIX),
            config.allowedFormats
        )
    }

    @Test
    fun `default hint text reminds operator to center the code`() {
        val config = HighResScanConfig.default()

        assertTrue(config.hintText.contains("中心"))
        assertTrue(config.hintText.contains("Data Matrix"))
    }
}
