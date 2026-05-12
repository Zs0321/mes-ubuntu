from __future__ import annotations

import base64
import hashlib
import os
import struct
import time
from dataclasses import dataclass


class DingTalkSignatureError(Exception):
    pass


class DingTalkDecryptError(Exception):
    pass


def _pkcs7_pad(data: bytes, block_size: int = 32) -> bytes:
    pad = block_size - (len(data) % block_size)
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data: bytes, block_size: int = 32) -> bytes:
    if not data:
        raise DingTalkDecryptError("empty payload")
    pad = data[-1]
    if pad < 1 or pad > block_size:
        raise DingTalkDecryptError("invalid pkcs7 padding")
    return data[:-pad]


def _sha1_signature(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    values = [token, timestamp, nonce, encrypted]
    values.sort()
    return hashlib.sha1("".join(values).encode("utf-8")).hexdigest()


def verify_signature(signature: str, token: str, timestamp: str, nonce: str, encrypted: str) -> None:
    expected = _sha1_signature(token, timestamp, nonce, encrypted)
    if signature != expected:
        raise DingTalkSignatureError("signature mismatch")


def _load_cipher(aes_key: str):
    key = base64.b64decode(aes_key + "=")
    iv = key[:16]
    try:
        from Crypto.Cipher import AES  # type: ignore

        class _A:
            def encrypt(self, payload: bytes) -> bytes:
                return AES.new(key, AES.MODE_CBC, iv).encrypt(payload)

            def decrypt(self, payload: bytes) -> bytes:
                return AES.new(key, AES.MODE_CBC, iv).decrypt(payload)

        return _A()
    except Exception as exc:
        raise DingTalkDecryptError("AES backend unavailable") from exc


def decrypt_payload(encrypted: str, aes_key: str, receive_id: str = "") -> str:
    cipher = _load_cipher(aes_key)
    payload = _pkcs7_unpad(cipher.decrypt(base64.b64decode(encrypted)))
    msg_len = struct.unpack("!I", payload[16:20])[0]
    msg = payload[20 : 20 + msg_len]
    recv = payload[20 + msg_len :].decode("utf-8", errors="ignore")
    if receive_id and recv and recv != receive_id:
        raise DingTalkDecryptError("receive_id mismatch")
    return msg.decode("utf-8", errors="replace")


def build_encrypted_success_response(plaintext: str, token: str, aes_key: str, receive_id: str = "") -> dict[str, str]:
    cipher = _load_cipher(aes_key)
    nonce = os.urandom(8).hex()
    timestamp = str(int(time.time()))
    plain = plaintext.encode("utf-8")
    packed = os.urandom(16) + struct.pack("!I", len(plain)) + plain + receive_id.encode("utf-8")
    encrypted = base64.b64encode(cipher.encrypt(_pkcs7_pad(packed))).decode("utf-8")
    signature = _sha1_signature(token, timestamp, nonce, encrypted)
    return {"msg_signature": signature, "encrypt": encrypted, "timeStamp": timestamp, "nonce": nonce}


@dataclass(slots=True)
class CallbackEnvelope:
    encrypt: str
    signature: str
    timestamp: str
    nonce: str


def parse_callback_envelope(payload: dict, args: dict | None = None) -> CallbackEnvelope:
    args = args or {}
    return CallbackEnvelope(
        encrypt=str(payload.get("encrypt") or ""),
        signature=str(args.get("msg_signature") or payload.get("msg_signature") or ""),
        timestamp=str(args.get("timestamp") or payload.get("timeStamp") or payload.get("timestamp") or ""),
        nonce=str(args.get("nonce") or payload.get("nonce") or ""),
    )
