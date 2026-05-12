#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试人员管理 API
提供测试人员列表的读取和保存功能
替代 SMB 直接读写 testers.json
"""

import json
import logging
from pathlib import Path
from typing import List
from flask import Blueprint, request, jsonify
from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir

logger = logging.getLogger(__name__)

# 创建蓝图
testers_bp = Blueprint('testers_api', __name__, url_prefix='/api/testers')

# 数据目录配置（统一解析，避免 use_webdav 导致路径分裂）
DATA_DIR = resolve_data_dir(
    nas_local_base_path=getattr(config, "nas_local_base_path", None),
    repo_root=Path(__file__).resolve().parent.parent,
    logger=logger,
)

TESTERS_FILE = DATA_DIR / "testers.json"

logger.info(f"[测试人员API] 数据目录: {DATA_DIR}")
logger.info(f"[测试人员API] 测试人员文件: {TESTERS_FILE}")


def load_testers() -> List[str]:
    """加载测试人员列表"""
    try:
        if TESTERS_FILE.exists():
            with open(TESTERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'testers' in data:
                    return data['testers']
        return []
    except Exception as e:
        logger.error(f"加载测试人员列表失败: {e}")
        return []


def save_testers(testers: List[str]) -> bool:
    """保存测试人员列表"""
    try:
        # 确保目录存在
        TESTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(TESTERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(testers, f, ensure_ascii=False, indent=2)
        
        logger.info(f"保存测试人员列表成功: {len(testers)} 人")
        return True
    except Exception as e:
        logger.error(f"保存测试人员列表失败: {e}")
        return False


@testers_bp.route('', methods=['GET'])
def get_testers():
    """获取测试人员列表"""
    try:
        testers = load_testers()
        return jsonify({
            'success': True,
            'testers': testers,
            'count': len(testers)
        })
    except Exception as e:
        logger.error(f"获取测试人员列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@testers_bp.route('', methods=['POST'])
def save_testers_list():
    """保存测试人员列表"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '无效的JSON数据'
            }), 400
        
        testers = data.get('testers', [])
        if not isinstance(testers, list):
            return jsonify({
                'success': False,
                'error': 'testers 必须是数组'
            }), 400
        
        # 过滤空字符串并去重
        testers = list(set([t.strip() for t in testers if t and t.strip()]))
        
        if save_testers(testers):
            return jsonify({
                'success': True,
                'message': f'保存成功，共 {len(testers)} 人',
                'count': len(testers)
            })
        else:
            return jsonify({
                'success': False,
                'error': '保存失败'
            }), 500
            
    except Exception as e:
        logger.error(f"保存测试人员列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@testers_bp.route('/<name>', methods=['POST'])
def add_tester(name: str):
    """添加单个测试人员"""
    try:
        if not name or not name.strip():
            return jsonify({
                'success': False,
                'error': '测试人员名称不能为空'
            }), 400
        
        testers = load_testers()
        name = name.strip()
        
        if name in testers:
            return jsonify({
                'success': True,
                'message': '测试人员已存在',
                'exists': True
            })
        
        testers.append(name)
        
        if save_testers(testers):
            return jsonify({
                'success': True,
                'message': f'添加成功: {name}',
                'count': len(testers)
            })
        else:
            return jsonify({
                'success': False,
                'error': '保存失败'
            }), 500
            
    except Exception as e:
        logger.error(f"添加测试人员失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@testers_bp.route('/<name>', methods=['DELETE'])
def remove_tester(name: str):
    """删除单个测试人员"""
    try:
        testers = load_testers()
        name = name.strip()
        
        if name not in testers:
            return jsonify({
                'success': True,
                'message': '测试人员不存在',
                'exists': False
            })
        
        testers.remove(name)
        
        if save_testers(testers):
            return jsonify({
                'success': True,
                'message': f'删除成功: {name}',
                'count': len(testers)
            })
        else:
            return jsonify({
                'success': False,
                'error': '保存失败'
            }), 500
            
    except Exception as e:
        logger.error(f"删除测试人员失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
