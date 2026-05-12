#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
APK 更新检查 API
提供 APK 文件列表和下载功能
替代 SMB 直接读取 APK 目录
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional
from flask import Blueprint, request, jsonify, send_file, make_response
from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir

logger = logging.getLogger(__name__)

# 创建蓝图
apk_bp = Blueprint('apk_api', __name__, url_prefix='/api/apk')

# 数据目录配置（统一解析，避免 use_webdav 导致路径分裂）
DATA_DIR = resolve_data_dir(
    nas_local_base_path=getattr(config, "nas_local_base_path", None),
    repo_root=Path(__file__).resolve().parent.parent,
    logger=logger,
)

APK_DIR = DATA_DIR / "APK"

# APK 文件名正则表达式: AppName v1.2.3_456.apk 或 AppName v1.2.3.apk
APK_PATTERN = re.compile(r'^(.+)\s+v([0-9.]+)(?:_(\d+))?\.apk$', re.IGNORECASE)


RELEASE_NOTES_SUFFIXES = (
    ".release-notes.md",
    ".release-notes.txt",
    ".changelog.md",
    ".changelog.txt",
)

logger.info(f"[APK更新API] 数据目录: {DATA_DIR}")
logger.info(f"[APK更新API] APK目录: {APK_DIR}")


def _json_nocache(payload: Dict, status: int = 200):
    response = make_response(jsonify(payload), status)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def parse_apk_filename(filename: str) -> Optional[Dict]:
    """解析 APK 文件名，提取应用名、版本号、版本代码"""
    match = APK_PATTERN.match(filename)
    if match:
        app_name = match.group(1).strip()
        version_name = match.group(2)
        version_code = int(match.group(3)) if match.group(3) else 0
        
        return {
            'appName': app_name,
            'versionName': version_name,
            'versionCode': version_code,
            'fileName': filename
        }
    return None




def _normalize_release_notes(text: str) -> str:
    normalized_lines = []
    for raw in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if normalized_lines and normalized_lines[-1] != "":
                normalized_lines.append("")
            continue
        stripped = re.sub(r"^#{1,6}\s*", "", stripped)
        stripped = re.sub(r"^[-*]\s+", "- ", stripped)
        normalized_lines.append(stripped)
    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()
    return "\n".join(normalized_lines).strip()


def _load_release_notes(apk_path: Path) -> tuple[Optional[str], Optional[str]]:
    for suffix in RELEASE_NOTES_SUFFIXES:
        candidate = apk_path.with_name(f"{apk_path.stem}{suffix}")
        if candidate.exists() and candidate.is_file():
            try:
                notes = _normalize_release_notes(candidate.read_text(encoding='utf-8'))
                if notes:
                    return notes, candidate.name
            except Exception as exc:
                logger.warning(f"????????: {candidate} -> {exc}")
    return None, None


def _build_apk_info(file_path: Path, parsed: Optional[Dict] = None) -> Dict:
    info = dict(parsed or parse_apk_filename(file_path.name) or {
        'appName': file_path.stem,
        'versionName': 'unknown',
        'versionCode': 0,
        'fileName': file_path.name,
    })
    stat = file_path.stat()
    info['fileSize'] = stat.st_size
    info['lastModified'] = int(stat.st_mtime * 1000)
    release_notes, release_notes_file = _load_release_notes(file_path)
    info['releaseNotes'] = release_notes
    info['releaseNotesFile'] = release_notes_file
    return info


def get_apk_list() -> List[Dict]:
    """?? APK ????"""
    apk_list = []

    try:
        if not APK_DIR.exists():
            logger.warning(f"APK?????: {APK_DIR}")
            return []

        for file in APK_DIR.iterdir():
            if file.is_file() and file.suffix.lower() == ".apk":
                apk_list.append(_build_apk_info(file))

        apk_list.sort(key=lambda x: x["lastModified"], reverse=True)

    except Exception as e:
        logger.error(f"??APK????: {e}")

    return apk_list


def find_latest_version(app_name: str = None) -> Optional[Dict]:
    """查找最新版本的 APK"""
    apk_list = get_apk_list()
    
    if not apk_list:
        return None
    
    if app_name:
        # 过滤指定应用名
        apk_list = [apk for apk in apk_list if apk['appName'].lower() == app_name.lower()]
    
    if not apk_list:
        return None
    
    # 按版本代码降序排序，取最新的
    apk_list.sort(key=lambda x: (x['versionCode'], x['lastModified']), reverse=True)
    return apk_list[0]


@apk_bp.route('/list', methods=['GET'])
def list_apks():
    """获取所有 APK 文件列表"""
    try:
        apk_list = get_apk_list()
        return _json_nocache({
            'success': True,
            'apks': apk_list,
            'count': len(apk_list)
        })
    except Exception as e:
        logger.error(f"获取APK列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@apk_bp.route('/debug', methods=['GET'])
def debug_apk_config():
    """调试端点：返回 APK 目录配置和文件列表"""
    try:
        import glob
        
        debug_info = {
            'data_dir': str(DATA_DIR),
            'apk_dir': str(APK_DIR),
            'apk_dir_exists': APK_DIR.exists(),
            'use_webdav': config.use_webdav,
            'nas_local_base_path': config.nas_local_base_path,
            'files': [],
            'parsed_files': []
        }
        
        if APK_DIR.exists():
            for file in APK_DIR.iterdir():
                if file.is_file():
                    debug_info['files'].append(file.name)
                    
                    # 尝试解析文件名
                    info = parse_apk_filename(file.name)
                    if info:
                        debug_info['parsed_files'].append(info)
                    else:
                        debug_info['parsed_files'].append({
                            'fileName': file.name,
                            'parseError': '无法解析文件名'
                        })
        
        return _json_nocache({
            'success': True,
            'debug': debug_info
        })
    except Exception as e:
        logger.error(f"调试端点失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@apk_bp.route('/latest', methods=['GET'])
def get_latest_apk():
    """获取最新版本的 APK 信息"""
    try:
        app_name = request.args.get('appName')
        latest = find_latest_version(app_name)
        
        if latest:
            return _json_nocache({
                'success': True,
                'apk': latest,
                'hasUpdate': True
            })
        else:
            return _json_nocache({
                'success': True,
                'apk': None,
                'hasUpdate': False
            })
    except Exception as e:
        logger.error(f"获取最新APK失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@apk_bp.route('/check-update', methods=['GET'])
def check_update():
    """检查是否有更新"""
    try:
        current_version_code = request.args.get('versionCode', type=int, default=0)
        current_version_name = request.args.get('versionName', default='')
        app_name = request.args.get('appName')
        
        latest = find_latest_version(app_name)
        
        if not latest:
            return _json_nocache({
                'success': True,
                'hasUpdate': False,
                'message': '没有找到可用的更新'
            })

        # 比较版本代码
        has_update = latest['versionCode'] > current_version_code

        return _json_nocache({
            'success': True,
            'hasUpdate': has_update,
            'currentVersion': {
                'versionCode': current_version_code,
                'versionName': current_version_name
            },
            'latestVersion': latest if has_update else None,
            'message': '发现新版本' if has_update else '已是最新版本'
        })
    except Exception as e:
        logger.error(f"检查更新失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@apk_bp.route('/download/<filename>', methods=['GET'])
def download_apk(filename: str):
    """下载指定的 APK 文件"""
    try:
        # 安全检查：防止路径遍历攻击
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({
                'success': False,
                'error': '无效的文件名'
            }), 400
        
        file_path = APK_DIR / filename
        
        if not file_path.exists():
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404
        
        if not file_path.is_file():
            return jsonify({
                'success': False,
                'error': '不是有效的文件'
            }), 400
        
        logger.info(f"下载APK: {filename}")
        
        return send_file(
            file_path,
            mimetype='application/vnd.android.package-archive',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"下载APK失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@apk_bp.route('/info/<filename>', methods=['GET'])
def get_apk_info(filename: str):
    """获取指定 APK 文件的信息"""
    try:
        # 安全检查
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({
                'success': False,
                'error': '无效的文件名'
            }), 400
        
        file_path = APK_DIR / filename
        
        if not file_path.exists():
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404
        
        info = parse_apk_filename(filename)
        if info:
            return _json_nocache({
                'success': True,
                'apk': _build_apk_info(file_path, info)
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法解析APK文件名'
            }), 400
            
    except Exception as e:
        logger.error(f"获取APK信息失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
