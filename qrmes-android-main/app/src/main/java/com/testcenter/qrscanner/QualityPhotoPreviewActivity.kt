package com.testcenter.qrscanner

import android.graphics.drawable.Drawable
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import com.bumptech.glide.Glide
import com.bumptech.glide.request.RequestListener
import com.bumptech.glide.request.target.Target
import com.testcenter.qrscanner.databinding.ActivityQualityPhotoPreviewBinding
import com.testcenter.qrscanner.quality.QualityPhotoDto
import com.testcenter.qrscanner.quality.QualityPhotoRequestFactory

class QualityPhotoPreviewActivity : AppCompatActivity() {

    private lateinit var binding: ActivityQualityPhotoPreviewBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityQualityPhotoPreviewBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupToolbar()
        loadPhoto()
    }

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            title = intent.getStringExtra(EXTRA_PHOTO_NAME).orEmpty().ifBlank { "工序图片" }
            setDisplayHomeAsUpEnabled(true)
        }
        binding.toolbar.setNavigationOnClickListener {
            onBackPressedDispatcher.onBackPressed()
        }
    }

    private fun loadPhoto() {
        val photo = QualityPhotoDto(
            name = intent.getStringExtra(EXTRA_PHOTO_NAME).orEmpty(),
            url = intent.getStringExtra(EXTRA_PHOTO_URL).orEmpty(),
            thumbnailUrl = intent.getStringExtra(EXTRA_THUMBNAIL_URL).orEmpty()
        )
        val model = QualityPhotoRequestFactory.buildModel(this, photo, preferThumbnail = false)
        if (model == null) {
            showError("图片地址无效")
            return
        }

        binding.progressBar.visibility = View.VISIBLE
        binding.photoView.visibility = View.INVISIBLE
        binding.tvError.visibility = View.GONE

        Glide.with(this)
            .load(model)
            .listener(object : RequestListener<Drawable> {
                override fun onLoadFailed(
                    e: com.bumptech.glide.load.engine.GlideException?,
                    model: Any?,
                    target: Target<Drawable>,
                    isFirstResource: Boolean
                ): Boolean {
                    showError(e?.message ?: "图片加载失败")
                    return false
                }

                override fun onResourceReady(
                    resource: Drawable,
                    model: Any,
                    target: Target<Drawable>,
                    dataSource: com.bumptech.glide.load.DataSource,
                    isFirstResource: Boolean
                ): Boolean {
                    binding.progressBar.visibility = View.GONE
                    binding.tvError.visibility = View.GONE
                    binding.photoView.visibility = View.VISIBLE
                    return false
                }
            })
            .into(binding.photoView)
    }

    private fun showError(message: String) {
        binding.progressBar.visibility = View.GONE
        binding.photoView.visibility = View.GONE
        binding.tvError.visibility = View.VISIBLE
        binding.tvError.text = message
    }

    companion object {
        const val EXTRA_PHOTO_URL = "extra_photo_url"
        const val EXTRA_THUMBNAIL_URL = "extra_thumbnail_url"
        const val EXTRA_PHOTO_NAME = "extra_photo_name"
    }
}
