"""
配置变更历史管理器
记录和管理配置文件的变更历史
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """变更类型"""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    IMPORTED = "imported"
    EXPORTED = "exported"
    RESTORED = "restored"
    MERGED = "merged"


class ConfigHistoryManager:
    """配置变更历史管理器"""
    
    def __init__(self, history_base_path: Path):
        self.history_base_path = Path(history_base_path)
        self.changes_dir = self.history_base_path / "changes"
        self.sync_log_dir = self.history_base_path / "sync_logs"
        
        # 确保目录存在
        self.changes_dir.mkdir(parents=True, exist_ok=True)
        self.sync_log_dir.mkdir(parents=True, exist_ok=True)
    
    def record_change(
        self, 
        project_name: str, 
        change_type: ChangeType, 
        description: str,
        user_id: str = None,
        old_config: Dict[str, Any] = None,
        new_config: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """记录配置变更"""
        try:
            change_id = str(uuid.uuid4())
            change_record = {
                "id": change_id,
                "projectName": project_name,
                "changeType": change_type.value,
                "description": description,
                "userId": user_id,
                "timestamp": datetime.now().isoformat(),
                "oldConfig": old_config,
                "newConfig": new_config,
                "metadata": metadata or {}
            }
            
            # 保存变更记录
            change_file = self.changes_dir / f"{project_name}_changes.json"
            changes = self._load_changes(project_name)
            changes.append(change_record)
            
            # 保持最近100条记录
            if len(changes) > 100:
                changes = changes[-100:]
            
            with open(change_file, 'w', encoding='utf-8') as f:
                json.dump(changes, f, ensure_ascii=False, indent=2)
            
            logger.info(f"记录配置变更: {project_name} - {change_type.value} - {description}")
            return change_id
            
        except Exception as e:
            logger.error(f"记录配置变更失败: {e}")
            return None
    
    def get_change_history(
        self, 
        project_name: str, 
        limit: int = 50,
        change_type: ChangeType = None,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> List[Dict[str, Any]]:
        """获取配置变更历史"""
        try:
            changes = self._load_changes(project_name)
            
            # 过滤条件
            filtered_changes = []
            for change in changes:
                # 按变更类型过滤
                if change_type and change.get("changeType") != change_type.value:
                    continue
                
                # 按时间范围过滤
                change_time = datetime.fromisoformat(change.get("timestamp", ""))
                if start_date and change_time < start_date:
                    continue
                if end_date and change_time > end_date:
                    continue
                
                filtered_changes.append(change)
            
            # 按时间倒序排列，返回最近的记录
            filtered_changes.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return filtered_changes[:limit]
            
        except Exception as e:
            logger.error(f"获取配置变更历史失败: {e}")
            return []
    
    def get_change_detail(self, project_name: str, change_id: str) -> Optional[Dict[str, Any]]:
        """获取变更详情"""
        try:
            changes = self._load_changes(project_name)
            for change in changes:
                if change.get("id") == change_id:
                    return change
            return None
            
        except Exception as e:
            logger.error(f"获取变更详情失败: {e}")
            return None
    
    def compare_configs(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> Dict[str, Any]:
        """比较两个配置的差异"""
        try:
            differences = {
                "added": {},
                "removed": {},
                "modified": {},
                "summary": {
                    "totalChanges": 0,
                    "addedCount": 0,
                    "removedCount": 0,
                    "modifiedCount": 0
                }
            }
            
            # 比较工序属性
            old_processes = {p.get("id"): p for p in old_config.get("processAttributes", [])}
            new_processes = {p.get("id"): p for p in new_config.get("processAttributes", [])}
            
            # 找出新增的工序
            for process_id, process in new_processes.items():
                if process_id not in old_processes:
                    differences["added"][f"process_{process_id}"] = process
                    differences["summary"]["addedCount"] += 1
            
            # 找出删除的工序
            for process_id, process in old_processes.items():
                if process_id not in new_processes:
                    differences["removed"][f"process_{process_id}"] = process
                    differences["summary"]["removedCount"] += 1
            
            # 找出修改的工序
            for process_id in set(old_processes.keys()) & set(new_processes.keys()):
                old_process = old_processes[process_id]
                new_process = new_processes[process_id]
                
                process_changes = {}
                for key in set(old_process.keys()) | set(new_process.keys()):
                    old_value = old_process.get(key)
                    new_value = new_process.get(key)
                    
                    if old_value != new_value:
                        process_changes[key] = {
                            "old": old_value,
                            "new": new_value
                        }
                
                if process_changes:
                    differences["modified"][f"process_{process_id}"] = process_changes
                    differences["summary"]["modifiedCount"] += 1
            
            # 比较物料属性（类似逻辑）
            old_materials = {m.get("id"): m for m in old_config.get("materialAttributes", [])}
            new_materials = {m.get("id"): m for m in new_config.get("materialAttributes", [])}
            
            # 新增物料
            for material_id, material in new_materials.items():
                if material_id not in old_materials:
                    differences["added"][f"material_{material_id}"] = material
                    differences["summary"]["addedCount"] += 1
            
            # 删除物料
            for material_id, material in old_materials.items():
                if material_id not in new_materials:
                    differences["removed"][f"material_{material_id}"] = material
                    differences["summary"]["removedCount"] += 1
            
            # 修改物料
            for material_id in set(old_materials.keys()) & set(new_materials.keys()):
                old_material = old_materials[material_id]
                new_material = new_materials[material_id]
                
                material_changes = {}
                for key in set(old_material.keys()) | set(new_material.keys()):
                    old_value = old_material.get(key)
                    new_value = new_material.get(key)
                    
                    if old_value != new_value:
                        material_changes[key] = {
                            "old": old_value,
                            "new": new_value
                        }
                
                if material_changes:
                    differences["modified"][f"material_{material_id}"] = material_changes
                    differences["summary"]["modifiedCount"] += 1
            
            # 计算总变更数
            differences["summary"]["totalChanges"] = (
                differences["summary"]["addedCount"] + 
                differences["summary"]["removedCount"] + 
                differences["summary"]["modifiedCount"]
            )
            
            return differences
            
        except Exception as e:
            logger.error(f"比较配置差异失败: {e}")
            return {"error": str(e)}
    
    def record_sync_event(
        self, 
        project_name: str, 
        sync_type: str,  # "upload", "download", "conflict"
        status: str,     # "success", "failed", "conflict"
        details: Dict[str, Any] = None
    ) -> str:
        """记录同步事件"""
        try:
            sync_id = str(uuid.uuid4())
            sync_record = {
                "id": sync_id,
                "projectName": project_name,
                "syncType": sync_type,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "details": details or {}
            }
            
            # 保存同步日志
            sync_file = self.sync_log_dir / f"{project_name}_sync.json"
            sync_logs = self._load_sync_logs(project_name)
            sync_logs.append(sync_record)
            
            # 保持最近50条记录
            if len(sync_logs) > 50:
                sync_logs = sync_logs[-50:]
            
            with open(sync_file, 'w', encoding='utf-8') as f:
                json.dump(sync_logs, f, ensure_ascii=False, indent=2)
            
            logger.info(f"记录同步事件: {project_name} - {sync_type} - {status}")
            return sync_id
            
        except Exception as e:
            logger.error(f"记录同步事件失败: {e}")
            return None
    
    def get_sync_history(self, project_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取同步历史"""
        try:
            sync_logs = self._load_sync_logs(project_name)
            sync_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return sync_logs[:limit]
            
        except Exception as e:
            logger.error(f"获取同步历史失败: {e}")
            return []
    
    def cleanup_old_records(self, days_to_keep: int = 90):
        """清理旧记录"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            # 清理变更记录
            for change_file in self.changes_dir.glob("*_changes.json"):
                try:
                    with open(change_file, 'r', encoding='utf-8') as f:
                        changes = json.load(f)
                    
                    # 过滤掉过期的记录
                    filtered_changes = []
                    for change in changes:
                        change_time = datetime.fromisoformat(change.get("timestamp", ""))
                        if change_time >= cutoff_date:
                            filtered_changes.append(change)
                    
                    # 如果有记录被清理，重新保存文件
                    if len(filtered_changes) < len(changes):
                        with open(change_file, 'w', encoding='utf-8') as f:
                            json.dump(filtered_changes, f, ensure_ascii=False, indent=2)
                        
                        logger.info(f"清理变更记录: {change_file.name}, 删除 {len(changes) - len(filtered_changes)} 条记录")
                
                except Exception as e:
                    logger.error(f"清理变更记录文件失败: {change_file.name}, {e}")
            
            # 清理同步日志
            for sync_file in self.sync_log_dir.glob("*_sync.json"):
                try:
                    with open(sync_file, 'r', encoding='utf-8') as f:
                        sync_logs = json.load(f)
                    
                    # 过滤掉过期的记录
                    filtered_logs = []
                    for log in sync_logs:
                        log_time = datetime.fromisoformat(log.get("timestamp", ""))
                        if log_time >= cutoff_date:
                            filtered_logs.append(log)
                    
                    # 如果有记录被清理，重新保存文件
                    if len(filtered_logs) < len(sync_logs):
                        with open(sync_file, 'w', encoding='utf-8') as f:
                            json.dump(filtered_logs, f, ensure_ascii=False, indent=2)
                        
                        logger.info(f"清理同步日志: {sync_file.name}, 删除 {len(sync_logs) - len(filtered_logs)} 条记录")
                
                except Exception as e:
                    logger.error(f"清理同步日志文件失败: {sync_file.name}, {e}")
            
        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")
    
    def get_project_statistics(self, project_name: str) -> Dict[str, Any]:
        """获取项目统计信息"""
        try:
            changes = self._load_changes(project_name)
            sync_logs = self._load_sync_logs(project_name)
            
            # 统计变更类型
            change_type_counts = {}
            for change in changes:
                change_type = change.get("changeType", "unknown")
                change_type_counts[change_type] = change_type_counts.get(change_type, 0) + 1
            
            # 统计同步状态
            sync_status_counts = {}
            for log in sync_logs:
                status = log.get("status", "unknown")
                sync_status_counts[status] = sync_status_counts.get(status, 0) + 1
            
            # 最近活动
            recent_changes = sorted(changes, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]
            recent_syncs = sorted(sync_logs, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]
            
            return {
                "projectName": project_name,
                "totalChanges": len(changes),
                "totalSyncs": len(sync_logs),
                "changeTypeCounts": change_type_counts,
                "syncStatusCounts": sync_status_counts,
                "recentChanges": recent_changes,
                "recentSyncs": recent_syncs,
                "lastActivity": recent_changes[0].get("timestamp") if recent_changes else None
            }
            
        except Exception as e:
            logger.error(f"获取项目统计信息失败: {e}")
            return {"error": str(e)}
    
    def _load_changes(self, project_name: str) -> List[Dict[str, Any]]:
        """加载变更记录"""
        try:
            change_file = self.changes_dir / f"{project_name}_changes.json"
            if change_file.exists():
                with open(change_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"加载变更记录失败: {e}")
            return []
    
    def _load_sync_logs(self, project_name: str) -> List[Dict[str, Any]]:
        """加载同步日志"""
        try:
            sync_file = self.sync_log_dir / f"{project_name}_sync.json"
            if sync_file.exists():
                with open(sync_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"加载同步日志失败: {e}")
            return []
    
    def export_history(self, project_name: str, export_path: Path) -> bool:
        """导出历史记录"""
        try:
            changes = self._load_changes(project_name)
            sync_logs = self._load_sync_logs(project_name)
            statistics = self.get_project_statistics(project_name)
            
            export_data = {
                "exportedAt": datetime.now().isoformat(),
                "projectName": project_name,
                "statistics": statistics,
                "changes": changes,
                "syncLogs": sync_logs
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"导出历史记录: {project_name} -> {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出历史记录失败: {e}")
            return False