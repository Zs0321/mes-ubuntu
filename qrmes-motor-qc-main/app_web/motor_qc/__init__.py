"""Motor QC Vision - 电机质检模块"""
from pathlib import Path

from flask import Blueprint

_APP_WEB_ROOT = Path(__file__).resolve().parents[1]

motor_qc_bp = Blueprint(
    'motor_qc',
    __name__,
    url_prefix='/motor-qc',
    template_folder=str(_APP_WEB_ROOT / 'templates'),
    static_folder=str(_APP_WEB_ROOT / 'static')
)

from . import routes
