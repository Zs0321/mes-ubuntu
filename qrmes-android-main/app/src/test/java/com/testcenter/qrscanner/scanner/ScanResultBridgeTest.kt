package com.testcenter.qrscanner.scanner

import com.google.zxing.client.android.Intents
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ScanResultBridgeTest {

    @Test
    fun `success extras use zxing scan contract keys`() {
        val extras = ScanResultBridge.success(
            rawValue = "D120200572551010786",
            formatName = "QR_CODE"
        ).toExtras()

        assertEquals("D120200572551010786", extras[Intents.Scan.RESULT])
        assertEquals("QR_CODE", extras[Intents.Scan.RESULT_FORMAT])
        assertFalse(extras.containsKey("com.google.zxing.client.android.SCAN_RESULT"))
        assertFalse(extras.containsKey("com.google.zxing.client.android.SCAN_RESULT_FORMAT"))
    }
}
