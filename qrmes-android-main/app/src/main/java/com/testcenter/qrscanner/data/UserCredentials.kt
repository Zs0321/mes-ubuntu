package com.testcenter.qrscanner.data

data class UserCredentials(
    val username: String,
    val password: String,
    val domain: String = ""
)
