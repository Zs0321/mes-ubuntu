"""电机项目配置管理器"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import re

from qrmes_shared_core.project_config_manager import ProjectConfigManager

class MotorProjectManager:
    """电机项目配置管理器（参照 ProjectConfigManager）"""

    def __init__(self, config_dir: Path):
        self.base_dir = Path(config_dir)
        self.config_dir = self.base_dir / "motor_projects"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.system_config_manager = ProjectConfigManager(self.base_dir)

    def _validate_project_id(self, project_id: str) -> str:
        """
        Prevent directory traversal / arbitrary file read-write via project_id.
        Allow Unicode names, but forbid any path separators and dot-dot segments.
        """
        pid = str(project_id or "").strip()
        if not pid:
            raise ValueError("project_id is required")
        if len(pid) > 128:
            raise ValueError("project_id too long")
        if "/" in pid or "\\" in pid:
            raise ValueError("invalid project_id (path separator)")
        if ".." in pid:
            raise ValueError("invalid project_id ('..')")
        if pid.startswith("."):
            raise ValueError("invalid project_id (hidden path)")
        return pid

    def _read_json_file(self, path: Path) -> Optional[Dict]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _collect_processes_from_system_config(self, config: Dict) -> List[Dict]:
        """从系统项目配置中提取质检相关工序"""
        processes: List[Dict] = []

        # Schema 2.x: productTypes[].processSteps[]
        for product_type in config.get("productTypes", []) or []:
            type_name = product_type.get("typeName", "")
            for step in product_type.get("processSteps", []) or []:
                if not isinstance(step, dict) or not step.get("name"):
                    continue
                attachment_type = (step.get("attachmentType") or "photo").lower()
                if attachment_type not in ("photo", "pdf", "both"):
                    attachment_type = "photo"
                processes.append({
                    "id": step.get("id"),
                    "name": step.get("name"),
                    "order": step.get("order", 0),
                    "product_type": type_name,
                    "attachmentType": attachment_type,
                    "photoRequired": bool(step.get("photoRequired", True)),
                    "required": bool(step.get("required", True)),
                    "subChecks": step.get("subChecks") or [],
                    "rules": step.get("rules") or {},
                    "expectedScrewCount": step.get("expectedScrewCount", step.get("expected_screw_count", 0)),
                    "specialProcesses": step.get("specialProcesses", step.get("special_processes", "")),
                    "specialParts": step.get("specialParts", step.get("special_parts", "")),
                    "extraFocus": step.get("extraFocus", step.get("extra_focus", "")),
                    "prePrompt": step.get("prePrompt", step.get("pre_prompt", "")),
                })

        # 兼容旧结构: processAttributes[]
        if not processes:
            for step in config.get("processAttributes", []) or []:
                if not isinstance(step, dict) or not step.get("name"):
                    continue
                attachment_type = (step.get("attachmentType") or "photo").lower()
                if attachment_type not in ("photo", "pdf", "both"):
                    attachment_type = "photo"
                processes.append({
                    "id": step.get("id"),
                    "name": step.get("name"),
                    "order": step.get("order", 0),
                    "product_type": step.get("productType", ""),
                    "attachmentType": attachment_type,
                    "photoRequired": bool(step.get("photoRequired", True)),
                    "required": bool(step.get("required", True)),
                    "subChecks": step.get("subChecks") or [],
                    "rules": step.get("rules") or {},
                    "expectedScrewCount": step.get("expectedScrewCount", step.get("expected_screw_count", 0)),
                    "specialProcesses": step.get("specialProcesses", step.get("special_processes", "")),
                    "specialParts": step.get("specialParts", step.get("special_parts", "")),
                    "extraFocus": step.get("extraFocus", step.get("extra_focus", "")),
                    "prePrompt": step.get("prePrompt", step.get("pre_prompt", "")),
                })

        processes.sort(key=lambda x: x.get("order", 0))
        return processes

    def _build_system_motor_project(self, project_stem: str, config: Dict) -> Optional[Dict]:
        if not isinstance(config, dict):
            return None

        processes = self._collect_processes_from_system_config(config)

        model = ""
        for product_type in config.get("productTypes", []) or []:
            model = (product_type or {}).get("modelNumber") or ""
            if model:
                break

        project_name = (
            config.get("projectName")
            or config.get("project_name")
            or project_stem
        )
        project_code = config.get("projectCode") or project_stem

        return {
            "project_id": project_stem,
            "project_code": project_code,
            "name": project_name,
            "model": model,
            "vision_provider": "qwen",
            "processes": processes,
            "source": "system_projects",
        }

    def _list_system_projects(self) -> List[Dict]:
        projects: List[Dict] = []
        projects_dir = self.system_config_manager.projects_config_dir
        if not projects_dir.exists():
            return projects

        for config_file in projects_dir.glob("*.json"):
            config = self._read_json_file(config_file)
            project = self._build_system_motor_project(config_file.stem, config or {})
            if project:
                projects.append(project)

        projects.sort(key=lambda x: str(x.get("name", "")))
        return projects

    def load_project(self, project_id: str) -> Optional[Dict]:
        """加载项目配置"""
        project_id = self._validate_project_id(project_id)
        config_file = self.config_dir / f"{project_id}.json"
        if config_file.exists():
            config = self._read_json_file(config_file)
            if config:
                if isinstance(config, dict):
                    config["project_id"] = config_file.stem
                return config

        # 兼容历史数据：文件名与 project_id 字段不一致时，按字段反查
        for candidate in self.config_dir.glob("*.json"):
            config = self._read_json_file(candidate)
            if not isinstance(config, dict):
                continue
            legacy_project_id = str(config.get("project_id", "")).strip()
            if legacy_project_id and legacy_project_id == project_id:
                config["project_id"] = candidate.stem
                return config

        # 回退到系统项目配置（projects/*.json）
        system_file = self.system_config_manager.projects_config_dir / f"{project_id}.json"
        if system_file.exists():
            config = self._read_json_file(system_file)
            if config:
                return self._build_system_motor_project(project_id, config)
        return None

    def save_project(self, project_id: str, config: Dict):
        """保存项目配置"""
        project_id = self._validate_project_id(project_id)
        config_file = self.config_dir / f"{project_id}.json"
        config_file.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def list_projects(self) -> List[Dict]:
        """列出所有项目"""
        projects = []
        for config_file in self.config_dir.glob("*.json"):
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
                if isinstance(config, dict):
                    # 以前存在 project_id 与文件名不一致，导致 inspect 路由 404
                    config["project_id"] = config_file.stem
                    config.setdefault("name", config.get("projectName", config_file.stem))
                    config.setdefault("model", "")
                    config.setdefault("processes", [])
                    config.setdefault("vision_provider", "qwen")
                    config.setdefault("source", "motor_projects")
                    projects.append(config)
            except (json.JSONDecodeError, IOError):
                continue

        merged: Dict[str, Dict] = {}
        for item in projects:
            merged[str(item.get("project_id", ""))] = item

        # 合并系统项目，避免只看到本地测试项目导致无法关联真实数据
        for item in self._list_system_projects():
            project_id = str(item.get("project_id", ""))
            if not project_id:
                continue
            if project_id not in merged:
                merged[project_id] = item

        result = list(merged.values())
        result.sort(key=lambda x: str(x.get("name", "")))
        return result

    def delete_project(self, project_id: str) -> bool:
        """删除项目配置"""
        project_id = self._validate_project_id(project_id)
        config_file = self.config_dir / f"{project_id}.json"
        if config_file.exists():
            config_file.unlink()
            return True
        return False

    def create_project(self, project_data: Dict) -> Dict:
        """创建新项目"""
        project_id = self._validate_project_id(project_data.get("project_id"))

        # 添加时间戳
        project_data["created_at"] = datetime.now().isoformat()
        project_data["updated_at"] = datetime.now().isoformat()

        # 保存配置
        self.save_project(project_id, project_data)
        return project_data
