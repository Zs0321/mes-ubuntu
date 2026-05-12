#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
活动测试状态管理 API
提供活动测试（正在进行中的测试）的读取、添加、更新和删除功能
替代 SMB 直接读写 active_tests.json
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from flask import Blueprint, request, jsonify
from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir

logger = logging.getLogger(__name__)

# 创建蓝图
active_tests_bp = Blueprint('active_tests_api', __name__, url_prefix='/api/active-tests')

# 数据目录配置（统一解析，避免 use_webdav 导致路径分裂）
DATA_DIR = resolve_data_dir(
    nas_local_base_path=getattr(config, "nas_local_base_path", None),
    repo_root=Path(__file__).resolve().parent.parent,
    logger=logger,
)

ACTIVE_TESTS_FILE = DATA_DIR / "active_tests.json"

logger.info(f"[活动测试API] 数据目录: {DATA_DIR}")
logger.info(f"[活动测试API] 活动测试文件: {ACTIVE_TESTS_FILE}")


def load_active_tests() -> List[Dict]:
    """加载活动测试列表"""
    try:
        if ACTIVE_TESTS_FILE.exists():
            with open(ACTIVE_TESTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'tests' in data:
                    return data['tests']
        return []
    except Exception as e:
        logger.error(f"加载活动测试列表失败: {e}")
        return []


def save_active_tests(tests: List[Dict]) -> bool:
    """保存活动测试列表"""
    try:
        # 确保目录存在
        ACTIVE_TESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(ACTIVE_TESTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tests, f, ensure_ascii=False, indent=2)
        
        logger.info(f"保存活动测试列表成功: {len(tests)} 条")
        return True
    except Exception as e:
        logger.error(f"保存活动测试列表失败: {e}")
        return False


def find_test_by_serial(tests: List[Dict], serial: str) -> Optional[Dict]:
    """根据序列号查找测试"""
    for test in tests:
        if test.get('serial') == serial:
            return test
    return None


@active_tests_bp.route('', methods=['GET'])
def get_active_tests():
    """获取所有活动测试"""
    try:
        tests = load_active_tests()
        return jsonify({
            'success': True,
            'tests': tests,
            'count': len(tests)
        })
    except Exception as e:
        logger.error(f"获取活动测试列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@active_tests_bp.route('/<serial>', methods=['GET'])
def get_active_test(serial: str):
    """获取指定序列号的活动测试"""
    try:
        tests = load_active_tests()
        test = find_test_by_serial(tests, serial)
        
        if test:
            return jsonify({
                'success': True,
                'test': test,
                'exists': True
            })
        else:
            return jsonify({
                'success': True,
                'test': None,
                'exists': False
            })
    except Exception as e:
        logger.error(f"获取活动测试失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@active_tests_bp.route('', methods=['POST'])
def upsert_active_test():
    """添加或更新活动测试"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                'success': False,
                'error': '无效的JSON数据'
            }), 400
        
        serial = data.get('serial')
        tester = data.get('tester')
        start_time = data.get('startTime')
        
        if not serial:
            return jsonify({
                'success': False,
                'error': '序列号不能为空'
            }), 400
        
        if not tester:
            return jsonify({
                'success': False,
                'error': '测试人员不能为空'
            }), 400
        
        # 如果没有提供开始时间，使用当前时间
        if not start_time:
            start_time = datetime.now().isoformat()
        
        tests = load_active_tests()
        existing = find_test_by_serial(tests, serial)
        
        new_test = {
            'serial': serial,
            'tester': tester,
            'startTime': start_time
        }
        
        if existing:
            # 更新现有测试
            tests = [t for t in tests if t.get('serial') != serial]
            tests.append(new_test)
            action = 'updated'
        else:
            # 添加新测试
            tests.append(new_test)
            action = 'created'
        
        if save_active_tests(tests):
            return jsonify({
                'success': True,
                'message': f'活动测试已{action}',
                'test': new_test,
                'action': action
            })
        else:
            return jsonify({
                'success': False,
                'error': '保存失败'
            }), 500
            
    except Exception as e:
        logger.error(f"添加/更新活动测试失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@active_tests_bp.route('/<serial>', methods=['DELETE'])
def remove_active_test(serial: str):
    """删除活动测试（测试完成时调用）"""
    try:
        tests = load_active_tests()
        existing = find_test_by_serial(tests, serial)
        
        if not existing:
            return jsonify({
                'success': True,
                'message': '活动测试不存在',
                'exists': False
            })
        
        tests = [t for t in tests if t.get('serial') != serial]
        
        if save_active_tests(tests):
            return jsonify({
                'success': True,
                'message': f'活动测试已删除: {serial}',
                'count': len(tests)
            })
        else:
            return jsonify({
                'success': False,
                'error': '保存失败'
            }), 500
            
    except Exception as e:
        logger.error(f"删除活动测试失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@active_tests_bp.route('/clear', methods=['POST'])
def clear_active_tests():
    """清空所有活动测试（管理员功能）"""
    try:
        if save_active_tests([]):
            return jsonify({
                'success': True,
                'message': '所有活动测试已清空'
            })
        else:
            return jsonify({
                'success': False,
                'error': '清空失败'
            }), 500
            
    except Exception as e:
        logger.error(f"清空活动测试失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
