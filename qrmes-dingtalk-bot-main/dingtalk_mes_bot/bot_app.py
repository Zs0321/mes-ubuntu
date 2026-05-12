from __future__ import annotations

import json

from flask import Flask, jsonify, request

from .config import load_config
from .message_parser import parse_message
from .protocol import (
    DingTalkDecryptError,
    DingTalkSignatureError,
    build_encrypted_success_response,
    decrypt_payload,
    parse_callback_envelope,
    verify_signature,
)
from .reply_engine import build_reply
from .runtime import create_runtime
from .services.webhook_sender import send_text_reply


def create_app() -> Flask:
    config = load_config()
    runtime = create_runtime(config)
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"success": True, "mode": "http", "message": "dingtalk bot is running"})

    @app.post("/callback")
    def callback():
        payload = request.get_json(silent=True) or {}
        source_payload = payload

        if isinstance(payload, dict) and payload.get("encrypt"):
            if not config.callback_token or not config.callback_aes_key:
                return jsonify({"errcode": 400, "errmsg": "missing callback token/aes key"}), 400

            envelope = parse_callback_envelope(payload, request.args.to_dict())
            try:
                verify_signature(
                    envelope.signature,
                    config.callback_token,
                    envelope.timestamp,
                    envelope.nonce,
                    envelope.encrypt,
                )
                decrypted = decrypt_payload(envelope.encrypt, config.callback_aes_key, config.callback_receive_id)
                payload = json.loads(decrypted) if decrypted else {}
            except DingTalkSignatureError as exc:
                return jsonify({"errcode": 403, "errmsg": f"signature verify failed: {exc}"}), 403
            except (DingTalkDecryptError, json.JSONDecodeError) as exc:
                return jsonify({"errcode": 400, "errmsg": f"decrypt failed: {exc}"}), 400

        message = parse_message(payload if isinstance(payload, dict) else {}, config.robot_code)
        if message and message.at_bot:
            reply = build_reply(runtime, message)
            if reply and message.session_webhook:
                send_text_reply(message.session_webhook, reply)

        if isinstance(source_payload, dict) and source_payload.get("encrypt"):
            encrypted_ack = build_encrypted_success_response(
                "success",
                config.callback_token,
                config.callback_aes_key,
                config.callback_receive_id,
            )
            return jsonify(encrypted_ack)

        return jsonify({"errcode": 0, "errmsg": "ok"})

    return app


if __name__ == "__main__":
    cfg = load_config()
    create_app().run(host=cfg.host, port=cfg.port)
