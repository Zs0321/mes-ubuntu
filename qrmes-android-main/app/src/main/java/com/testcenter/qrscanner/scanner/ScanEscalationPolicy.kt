package com.testcenter.qrscanner.scanner

enum class ScanEscalationAction {
    NONE,
    AUTO_HIGH_RES
}

enum class HighResReturnAction {
    RESUME_FAST_SCAN,
    PROPAGATE_RESULT
}

data class ScanEscalationPolicy(
    val autoFallbackDelayMs: Long = 2800L
) {
    fun decide(
        elapsedMs: Long,
        hasRequestedHighRes: Boolean,
        isPreviewReady: Boolean,
        autoFallbackEnabled: Boolean
    ): ScanEscalationAction {
        if (hasRequestedHighRes || !isPreviewReady || !autoFallbackEnabled) {
            return ScanEscalationAction.NONE
        }
        return if (elapsedMs >= autoFallbackDelayMs) {
            ScanEscalationAction.AUTO_HIGH_RES
        } else {
            ScanEscalationAction.NONE
        }
    }

    fun onHighResFinished(succeeded: Boolean): HighResReturnAction {
        return if (succeeded) {
            HighResReturnAction.PROPAGATE_RESULT
        } else {
            HighResReturnAction.RESUME_FAST_SCAN
        }
    }
}
