package com.testcenter.qrscanner.api

import android.content.Context
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import okhttp3.ConnectionPool
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import com.testcenter.qrscanner.BuildConfig
import retrofit2.converter.gson.GsonConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * REST API 客户端
 * 提供统一的 Retrofit 配置和 ApiService 实例
 */
object ApiClient {
    private const val TAG = "ApiClient"

    // 默认超时时间（秒）
    private const val CONNECT_TIMEOUT = 8L
    private const val READ_TIMEOUT = 30L
    private const val WRITE_TIMEOUT = 60L  // 照片/PDF 上传需要更长超时
    private const val QC_ANALYZE_READ_TIMEOUT = 125L

    @Volatile
    private var retrofit: Retrofit? = null

    @Volatile
    private var apiService: ApiService? = null

    @Volatile
    private var currentBaseUrl: String? = null

    /**
     * 重置实例，切换服务器地址后调用
     */
    fun resetInstance() {
        synchronized(this) {
            apiService = null
            retrofit = null
            currentBaseUrl = null
            AppLogger.log(TAG, "ApiService 实例已重置")
        }
    }

    /**
     * 获取 ApiService 实例
     * 如果 baseUrl 发生变化，会重新创建实例
     */
    fun getApiService(context: Context): ApiService {
        val preferencesManager = PreferencesManager(context)
        val baseUrl = preferencesManager.getApiBaseUrl()

        // 确保 baseUrl 以 / 结尾
        val normalizedUrl = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"

        // 快速路径：无锁检查
        val cached = apiService
        if (cached != null && currentBaseUrl == normalizedUrl) {
            return cached
        }

        // 慢路径：加锁创建
        synchronized(this) {
            if (apiService == null || currentBaseUrl != normalizedUrl) {
                AppLogger.log(TAG, "创建新的 ApiService 实例, baseUrl: $normalizedUrl")
                retrofit = createRetrofit(context, normalizedUrl)
                apiService = retrofit!!.create(ApiService::class.java)
                currentBaseUrl = normalizedUrl
            }
            return apiService!!
        }
    }


    /**
     * 创建 Retrofit 实例
     */
    private fun createRetrofit(context: Context, baseUrl: String): Retrofit {
        val okHttpClient = createOkHttpClient(context)

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    /**
     * 创建 OkHttpClient 实例
     */
    private fun createOkHttpClient(context: Context): OkHttpClient {
        val preferencesManager = PreferencesManager(context)

        // 日志拦截器
        val loggingInterceptor = HttpLoggingInterceptor { message ->
            AppLogger.log(TAG, message)
        }.apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
                    else HttpLoggingInterceptor.Level.BASIC
        }

        // 认证拦截器
        val authInterceptor = Interceptor { chain ->
            val originalRequest = chain.request()

            // 从 PreferencesManager 获取认证信息
            val username = preferencesManager.getUsername()
            val password = preferencesManager.getPassword()

            val requestBuilder = originalRequest.newBuilder()

            // 如果有认证信息，添加 Basic Auth 头
            if (!username.isNullOrEmpty() && !password.isNullOrEmpty()) {
                val credentials = okhttp3.Credentials.basic(username, password)
                requestBuilder.header("Authorization", credentials)
            }

            // 添加通用头
            requestBuilder.header("Accept", "application/json")

            chain.proceed(requestBuilder.build())
        }

        // 重试拦截器（仅重试可重试场景，避免重复触发昂贵 POST）
        val retryInterceptor = Interceptor { chain ->
            val request = chain.request()
            val method = request.method.uppercase()
            val path = request.url.encodedPath
            val isIdempotent = method == "GET" || method == "HEAD"
            val maxRetries = if (isIdempotent) 2 else 0
            val runtimeChain = if (path.endsWith("/api/qc/analyze")) {
                chain.withReadTimeout(QC_ANALYZE_READ_TIMEOUT.toInt(), TimeUnit.SECONDS)
            } else {
                chain
            }

            var attempt = 0
            while (attempt <= maxRetries) {
                try {
                    val response = runtimeChain.proceed(request)
                    if (!shouldRetryHttpStatus(response.code) || attempt >= maxRetries) {
                        if (!response.isSuccessful && method == "POST") {
                            AppLogger.log(TAG, "POST 请求失败且不重试，避免重复调用: ${request.url}, code=${response.code}")
                        }
                        return@Interceptor response
                    }

                    attempt++
                    AppLogger.log(TAG, "请求返回可重试状态(${response.code})，重试第 $attempt 次: ${request.url}")
                    response.close()
                } catch (e: IOException) {
                    if (!isIdempotent || attempt >= maxRetries) {
                        if (!isIdempotent) {
                            AppLogger.log(TAG, "POST 请求网络异常不重试: ${request.url}, err=${e.message}")
                        }
                        throw e
                    }

                    attempt++
                    AppLogger.log(TAG, "请求网络异常，重试第 $attempt 次: ${request.url}, err=${e.message}")
                }
            }

            throw IOException("请求失败且超过最大重试次数: ${request.url}")
        }

        return OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT, TimeUnit.SECONDS)
            .writeTimeout(WRITE_TIMEOUT, TimeUnit.SECONDS)
            .connectionPool(ConnectionPool(5, 5, TimeUnit.MINUTES))
            .addInterceptor(authInterceptor)
            .addInterceptor(retryInterceptor)
            .addInterceptor(loggingInterceptor)
            .build()
    }

    private fun shouldRetryHttpStatus(code: Int): Boolean {
        return code == 408 || code == 425 || code == 429 || code >= 500
    }

    /**
     * 重置客户端（用于切换服务器时）
     */
    fun reset() {
        synchronized(this) {
            retrofit = null
            apiService = null
            currentBaseUrl = null
            AppLogger.log(TAG, "ApiClient 已重置")
        }
    }
}
