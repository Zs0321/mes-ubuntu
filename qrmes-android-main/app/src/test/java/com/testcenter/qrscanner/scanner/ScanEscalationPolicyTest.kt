package com.testcenter.qrscanner.scanner

import org.junit.Assert.assertEquals
import org.junit.Test

class ScanEscalationPolicyTest {

    @Test
    fun `does not auto fallback before preview is ready`() {
        val policy = ScanEscalationPolicy(autoFallbackDelayMs = 1200L)

        assertEquals(
            ScanEscalationAction.NONE,
            policy.decide(
                elapsedMs = 5000L,
                hasRequestedHighRes = false,
                isPreviewReady = false,
                autoFallbackEnabled = true
            )
        )
    }

    @Test
    fun `does not auto fallback when automatic escalation is disabled`() {
        val policy = ScanEscalationPolicy(autoFallbackDelayMs = 1200L)

        assertEquals(
            ScanEscalationAction.NONE,
            policy.decide(
                elapsedMs = 5000L,
                hasRequestedHighRes = false,
                isPreviewReady = true,
                autoFallbackEnabled = false
            )
        )
    }

    @Test
    fun `auto falls back once timeout is reached after preview starts`() {
        val policy = ScanEscalationPolicy(autoFallbackDelayMs = 1200L)

        assertEquals(
            ScanEscalationAction.AUTO_HIGH_RES,
            policy.decide(
                elapsedMs = 1200L,
                hasRequestedHighRes = false,
                isPreviewReady = true,
                autoFallbackEnabled = true
            )
        )
    }

    @Test
    fun `does not auto fallback after high res launch has already been requested`() {
        val policy = ScanEscalationPolicy(autoFallbackDelayMs = 1200L)

        assertEquals(
            ScanEscalationAction.NONE,
            policy.decide(
                elapsedMs = 5000L,
                hasRequestedHighRes = true,
                isPreviewReady = true,
                autoFallbackEnabled = true
            )
        )
    }

    @Test
    fun `canceled high res returns to fast scan`() {
        val policy = ScanEscalationPolicy(autoFallbackDelayMs = 1200L)

        assertEquals(
            HighResReturnAction.RESUME_FAST_SCAN,
            policy.onHighResFinished(succeeded = false)
        )
    }

    @Test
    fun `successful high res propagates final result`() {
        val policy = ScanEscalationPolicy(autoFallbackDelayMs = 1200L)

        assertEquals(
            HighResReturnAction.PROPAGATE_RESULT,
            policy.onHighResFinished(succeeded = true)
        )
    }
}
