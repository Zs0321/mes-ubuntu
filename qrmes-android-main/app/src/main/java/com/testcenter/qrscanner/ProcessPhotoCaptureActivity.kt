package com.testcenter.qrscanner

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.view.MenuItem
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.testcenter.qrscanner.utils.AppLogger

class ProcessPhotoCaptureActivity : AppCompatActivity() {
    
    companion object {
        const val EXTRA_PRODUCT_SERIAL = "extra_product_serial"
        const val EXTRA_PROCESS_STEP_ID = "extra_process_step_id"
        const val EXTRA_PROCESS_STEP_NAME = "extra_process_step_name"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val productSerial = intent.getStringExtra(EXTRA_PRODUCT_SERIAL)
        val processStepId = intent.getStringExtra(EXTRA_PROCESS_STEP_ID)
        val processStepName = intent.getStringExtra(EXTRA_PROCESS_STEP_NAME)
        
        AppLogger.log("ProcessPhotoCaptureActivity", "Product: $productSerial, Step: $processStepName")
        
        // TODO: Implement camera functionality for process steps
        Toast.makeText(this, "工序拍照功能待实现\n产品: $productSerial\n工序: $processStepName", Toast.LENGTH_LONG).show()
        
        // For now, just finish the activity
        finish()
    }
}