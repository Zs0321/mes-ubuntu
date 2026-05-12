package com.testcenter.qrscanner

import org.junit.Assert.fail
import org.junit.Test
import java.lang.reflect.InvocationTargetException

class QualityProcessDetailDialogFragmentTest {

    @Test
    fun showErrorAfterBindingClearedDoesNotCrash() {
        val fragment = QualityProcessDetailDialogFragment()
        val method = QualityProcessDetailDialogFragment::class.java
            .getDeclaredMethod("showError", String::class.java)
            .apply { isAccessible = true }

        try {
            method.invoke(fragment, "load failed")
        } catch (e: InvocationTargetException) {
            fail("showError should not crash after binding is cleared: ${e.targetException}")
        }
    }
}
