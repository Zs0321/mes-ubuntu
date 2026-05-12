package com.testcenter.qrscanner.utils

import android.content.Context
import com.google.gson.Gson
import com.testcenter.qrscanner.repository.ProjectRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

class ProjectManager(private val context: Context) {

    private val gson = Gson()
    private val projectsFileName = "projects_cache.json"
    private val legacyProjectsFileName = "projects.json"
    private val preferencesManager = PreferencesManager(context)
    private val projectRepository = ProjectRepository(context)

    @Volatile
    private var isRefreshingProjectCache = false

    data class ProjectData(
        val projects: MutableList<String> = mutableListOf()
    )

    private fun getProjectsFile(): File = File(context.filesDir, projectsFileName)

    private fun getLegacyProjectsFile(): File = File(context.filesDir, legacyProjectsFileName)

    private fun migrateLegacyProjectsCacheIfNeeded(targetFile: File) {
        try {
            if (targetFile.exists()) return
            val legacyFile = getLegacyProjectsFile()
            if (!legacyFile.exists()) return
            legacyFile.copyTo(targetFile, overwrite = true)
            AppLogger.log("ProjectManager", "Migrated legacy projects.json to projects_cache.json")
        } catch (e: Exception) {
            AppLogger.log("ProjectManager", "Error migrating legacy project cache", e)
        }
    }

    private fun readProjectListFromLocalCache(): List<String> {
        return try {
            val file = getProjectsFile()
            migrateLegacyProjectsCacheIfNeeded(file)
            if (!file.exists()) {
                emptyList()
            } else {
                val jsonString = file.readText()
                val projectData = gson.fromJson(jsonString, ProjectData::class.java) ?: ProjectData()
                projectData.projects.filter { it.isNotBlank() }
            }
        } catch (e: Exception) {
            AppLogger.log("ProjectManager", "Error reading local project cache", e)
            emptyList()
        }
    }

    fun getProjectList(): List<String> {
        return try {
            val projects = readProjectListFromLocalCache()
            if (projects.isEmpty()) {
                AppLogger.log("ProjectManager", "No local projects found, returning empty list")
            } else {
                AppLogger.log("ProjectManager", "Loaded ${projects.size} projects from local cache (DB-backed API source)")
            }

            // Return cached data immediately, but keep cache warm in background.
            syncFromNetwork()
            projects
        } catch (e: Exception) {
            AppLogger.log("ProjectManager", "Error loading project list", e)
            emptyList()
        }
    }

    fun saveProjectList(projects: List<String>): Boolean {
        return try {
            saveProjectListLocally(projects)
            syncToNetwork(projects)
            true
        } catch (e: Exception) {
            AppLogger.log("ProjectManager", "Error saving project list", e)
            false
        }
    }

    fun saveProjectListLocally(projects: List<String>): Boolean {
        return try {
            val projectData = ProjectData(projects.toMutableList())
            val jsonString = gson.toJson(projectData)
            val file = getProjectsFile()
            file.writeText(jsonString)
            AppLogger.log("ProjectManager", "Project list cache saved locally: ${projects.size} projects")
            true
        } catch (e: Exception) {
            AppLogger.log("ProjectManager", "Error saving project list locally", e)
            false
        }
    }

    fun addProject(projectName: String): Boolean {
        val currentProjects = getProjectList().toMutableList()
        if (!currentProjects.contains(projectName)) {
            currentProjects.add(projectName)
            return saveProjectList(currentProjects)
        }
        return false
    }

    fun removeProject(projectName: String): Boolean {
        val currentProjects = getProjectList().toMutableList()
        if (currentProjects.remove(projectName)) {
            return saveProjectList(currentProjects)
        }
        return false
    }

    fun getSelectedProject(): String? = preferencesManager.getSelectedProject()

    fun setSelectedProject(projectName: String) {
        preferencesManager.setSelectedProject(projectName)
        AppLogger.log("ProjectManager", "Selected project: $projectName")
    }

    fun getSelectedProcessProject(): String? = preferencesManager.getSelectedProcessProject()

    fun setSelectedProcessProject(projectName: String) {
        preferencesManager.setSelectedProcessProject(projectName)
        AppLogger.log("ProjectManager", "Selected process project: $projectName")
    }

    fun clearSelectedProcessProject() {
        preferencesManager.clearSelectedProcessProject()
    }

    private fun syncFromNetwork(force: Boolean = false, maxCacheAgeMs: Long = 60_000L) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                refreshProjectListCache(force = force, maxCacheAgeMs = maxCacheAgeMs)
            } catch (e: Exception) {
                AppLogger.log("ProjectManager", "Error syncing from network: ${e.message}", e)
            }
        }
    }

    fun refreshProjectListCacheInBackground(force: Boolean = false, maxCacheAgeMs: Long = 60_000L) {
        syncFromNetwork(force = force, maxCacheAgeMs = maxCacheAgeMs)
    }

    private fun syncToNetwork(projects: List<String>) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val result = projectRepository.saveProjectList(projects)
                result.fold(
                    onSuccess = {
                        AppLogger.log("ProjectManager", "Successfully synced ${projects.size} projects to REST API")
                    },
                    onFailure = { e ->
                        AppLogger.log("ProjectManager", "Failed to sync projects to REST API: ${e.message}")
                        retryNetworkSync(projects)
                    }
                )
            } catch (e: Exception) {
                AppLogger.log("ProjectManager", "Error syncing to network: ${e.message}", e)
            }
        }
    }

    private fun retryNetworkSync(projects: List<String>) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                kotlinx.coroutines.delay(5000)
                AppLogger.log("ProjectManager", "Retrying network sync for ${projects.size} projects")

                val result = projectRepository.saveProjectList(projects)
                result.fold(
                    onSuccess = {
                        AppLogger.log("ProjectManager", "Retry successful: synced ${projects.size} projects to REST API")
                    },
                    onFailure = { e ->
                        AppLogger.log("ProjectManager", "Retry failed: ${e.message}")
                    }
                )
            } catch (e: Exception) {
                AppLogger.log("ProjectManager", "Retry error: ${e.message}", e)
            }
        }
    }

    fun forceNetworkSync() {
        val projects = getProjectList()
        AppLogger.log("ProjectManager", "Force syncing ${projects.size} projects to network")
        syncToNetwork(projects)
    }

    fun clearLocalCache(): Boolean {
        return try {
            val file = getProjectsFile()
            if (file.exists()) {
                file.delete()
                getLegacyProjectsFile().takeIf { it.exists() }?.delete()
                AppLogger.log("ProjectManager", "Local project cache cleared")
                true
            } else {
                AppLogger.log("ProjectManager", "No local cache to clear")
                false
            }
        } catch (e: Exception) {
            AppLogger.log("ProjectManager", "Error clearing local cache", e)
            false
        }
    }

    suspend fun forceRefreshFromNetwork(): List<String> = refreshProjectListCache(force = true, maxCacheAgeMs = 0L)

    suspend fun refreshProjectListCache(force: Boolean = false, maxCacheAgeMs: Long = 60_000L): List<String> =
        withContext(Dispatchers.IO) {
            val localProjects = readProjectListFromLocalCache()
            val cacheFile = getProjectsFile()
            val cacheAgeMs = if (cacheFile.exists()) {
                (System.currentTimeMillis() - cacheFile.lastModified()).coerceAtLeast(0L)
            } else {
                Long.MAX_VALUE
            }

            if (!force && localProjects.isNotEmpty() && cacheAgeMs < maxCacheAgeMs) {
                AppLogger.log(
                    "ProjectManager",
                    "Skip project cache refresh: cache still fresh (${cacheAgeMs}ms < ${maxCacheAgeMs}ms)"
                )
                return@withContext localProjects
            }

            if (isRefreshingProjectCache) {
                AppLogger.log("ProjectManager", "Project cache refresh already in progress, reusing local cache")
                return@withContext localProjects
            }

            isRefreshingProjectCache = true
            try {
                AppLogger.log(
                    "ProjectManager",
                    if (force) "Force refreshing projects from REST API"
                    else "Refreshing projects from REST API (cacheAgeMs=$cacheAgeMs)"
                )
                val result = projectRepository.fetchProjectList()
                result.fold(
                    onSuccess = { networkProjects ->
                        if (networkProjects.isEmpty() && localProjects.isNotEmpty()) {
                            AppLogger.log("ProjectManager", "Server returned empty project list, keeping local cache")
                            localProjects
                        } else {
                            AppLogger.log("ProjectManager", "Fetched ${networkProjects.size} projects from REST API: $networkProjects")
                            saveProjectListLocally(networkProjects)
                            networkProjects
                        }
                    },
                    onFailure = { e ->
                        AppLogger.log("ProjectManager", "Error refreshing from REST API: ${e.message}")
                        localProjects
                    }
                )
            } catch (e: Exception) {
                AppLogger.log("ProjectManager", "Error refreshing from network: ${e.message}", e)
                localProjects
            } finally {
                isRefreshingProjectCache = false
            }
        }
}
