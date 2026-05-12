package com.testcenter.qrscanner.utils

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProcessPhotoFileNameParserTest {

    @Test
    fun `extractProcessName supports filename without trailing sequence`() {
        val process = ProcessPhotoFileNameParser.extractProcessName(
            serial = "test111222",
            fileName = "test111222_后端盖打胶_20260218_164119.jpg"
        )
        assertEquals("后端盖打胶", process)
    }

    @Test
    fun `extractProcessName supports filename with trailing sequence`() {
        val process = ProcessPhotoFileNameParser.extractProcessName(
            serial = "test111222",
            fileName = "test111222_点胶_20260218_185527_001.jpg"
        )
        assertEquals("点胶", process)
    }

    @Test
    fun `extractProcessName supports sanitized serial`() {
        val process = ProcessPhotoFileNameParser.extractProcessName(
            serial = "BP2601/21",
            fileName = "BP2601_21_铁芯压装_20260218_194430.jpg"
        )
        assertEquals("铁芯压装", process)
    }

    @Test
    fun `extractProcessName returns null when serial mismatched`() {
        val process = ProcessPhotoFileNameParser.extractProcessName(
            serial = "test111223",
            fileName = "test111222_后端盖打胶_20260218_164119.jpg"
        )
        assertNull(process)
    }

    @Test
    fun `normalizeForMatch treats punctuation and underscore as same`() {
        val left = ProcessPhotoFileNameParser.normalizeForMatch("旋变转子，温感线接线等")
        val right = ProcessPhotoFileNameParser.normalizeForMatch("旋变转子_温感线接线等")
        assertEquals(left, right)
    }
}
