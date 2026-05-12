from __future__ import annotations

from flask import Flask, jsonify, request

from .config import load_config
from .message_parser import parse_feishu_event
from .reply_engine import build_reply
from .runtime import create_runtime
from .security import verify_event_token
from .service_factory import create_feishu_client, create_resource_enrichment_service


def create_app() -> Flask:
    config = load_config()
    runtime = create_runtime(config)
    feishu_client = create_feishu_client(config)
    resource_enrichment_service = create_resource_enrichment_service(config)
    app = Flask(__name__)

    @app.get('/health')
    def health():
        return jsonify({'success': True, 'message': 'feishu mes bot is running', 'mode': config.mode})

    @app.post('/feishu/event')
    def feishu_event():
        payload = request.get_json(silent=True) or {}
        if payload.get('type') == 'url_verification':
            if not verify_event_token(payload, config.verification_token):
                return jsonify({'code': 403, 'msg': 'invalid token'}), 403
            return jsonify({'challenge': payload.get('challenge', '')})

        if not verify_event_token(payload, config.verification_token):
            return jsonify({'code': 403, 'msg': 'invalid token'}), 403

        message = parse_feishu_event(payload, bot_open_id=config.bot_open_id, bot_name=config.bot_name)
        if message and message.at_bot:
            message = resource_enrichment_service.enrich(message)
            reply = build_reply(runtime, message)
            if reply:
                feishu_client.send_text(message.receive_id, message.receive_id_type, reply)
        return jsonify({'code': 0, 'msg': 'ok'})

    return app


def run_callback_server(config=None):
    cfg = config or load_config()
    create_app().run(host=cfg.host, port=cfg.port)


if __name__ == '__main__':
    run_callback_server()
