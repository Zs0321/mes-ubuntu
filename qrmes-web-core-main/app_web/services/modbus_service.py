"""Modbus TCP service utilities for instrument communication."""

from __future__ import annotations

from dataclasses import dataclass
import socket
import struct
import threading
from typing import Dict, List


class ModbusError(RuntimeError):
    """Base error for Modbus operations."""


class ModbusExceptionResponse(ModbusError):
    """Raised when slave returns Modbus exception response."""

    def __init__(self, function_code: int, exception_code: int):
        self.function_code = function_code
        self.exception_code = exception_code
        super().__init__(
            f"modbus exception response: function=0x{function_code:02X}, "
            f"exception=0x{exception_code:02X}"
        )


STATUS_TEXT_MAP: Dict[int, str] = {
    0: "待机",
    1: "错误状态",
    2: "1工位测试中",
    3: "2工位测试中",
}

TEST_RESULT_TEXT_MAP: Dict[int, str] = {
    0: "未判定",
    1: "不合格",
    2: "合格",
}

ERROR_CODE_TEXT_MAP: Dict[int, str] = {
    0: "无错误",
    1: "通信异常",
    2: "命令错误",
    3: "设备配置异常",
    4: "通信端口打开失败",
    5: "未找到匝间或反嵌标准波形",
    6: "未知错误",
}


def status_text(code: int) -> str:
    return STATUS_TEXT_MAP.get(code, f"未知状态({code})")


def result_text(code: int) -> str:
    return TEST_RESULT_TEXT_MAP.get(code, f"未知结果({code})")


def error_code_text(code: int) -> str:
    return ERROR_CODE_TEXT_MAP.get(code, f"未知错误码({code})")


def encode_ascii_to_registers(
    value: str,
    register_count: int,
    *,
    one_char_per_register: bool = False,
    encoding: str = "ascii",
) -> List[int]:
    """Encode text to holding-register values.

    - two-char mode: one register stores two bytes (high byte first).
    - one-char mode: one register stores one byte in low byte.
    """
    if register_count <= 0:
        return []

    raw = (value or "").encode(encoding, errors="ignore")
    if one_char_per_register:
        raw = raw[:register_count]
        regs = [int(b) for b in raw]
    else:
        raw = raw[: register_count * 2]
        if len(raw) % 2 == 1:
            raw += b"\x00"
        regs = []
        for i in range(0, len(raw), 2):
            regs.append((raw[i] << 8) | raw[i + 1])

    if len(regs) < register_count:
        regs.extend([0] * (register_count - len(regs)))
    else:
        regs = regs[:register_count]
    return regs


def decode_ascii_from_registers(
    registers: List[int],
    *,
    one_char_per_register: bool = False,
    encoding: str = "ascii",
) -> str:
    raw = bytearray()
    if one_char_per_register:
        for reg in registers:
            raw.append(reg & 0xFF)
    else:
        for reg in registers:
            raw.append((reg >> 8) & 0xFF)
            raw.append(reg & 0xFF)
    return bytes(raw).rstrip(b"\x00").decode(encoding, errors="ignore")


@dataclass
class ModbusTcpParams:
    host: str
    port: int = 502
    unit_id: int = 1
    timeout_sec: float = 2.0


class ModbusTcpClient:
    """Minimal Modbus TCP client (function code 0x03 / 0x04 / 0x10)."""

    def __init__(self, params: ModbusTcpParams):
        self.params = params
        self._tid = 0
        self._tid_lock = threading.Lock()

    def read_holding_registers(self, start_address: int, count: int) -> List[int]:
        return self._read_registers(0x03, start_address, count)

    def read_input_registers(self, start_address: int, count: int) -> List[int]:
        return self._read_registers(0x04, start_address, count)

    def write_multiple_registers(self, start_address: int, values: List[int]) -> Dict[str, int]:
        if not values:
            raise ModbusError("write values cannot be empty")
        if len(values) > 123:
            raise ModbusError("write count exceeds Modbus limit 123")

        payload = struct.pack(">HHB", start_address, len(values), len(values) * 2)
        payload += struct.pack(f">{len(values)}H", *values)
        body = self._send_pdu(0x10, payload)
        if len(body) < 4:
            raise ModbusError(f"invalid write response body length: {len(body)}")
        ack_start, ack_count = struct.unpack(">HH", body[:4])
        return {
            "start_address": int(ack_start),
            "count": int(ack_count),
        }

    def _read_registers(self, function_code: int, start_address: int, count: int) -> List[int]:
        if count <= 0:
            raise ModbusError("read count must > 0")
        if count > 125:
            raise ModbusError("read count exceeds Modbus limit 125")

        payload = struct.pack(">HH", start_address, count)
        body = self._send_pdu(function_code, payload)
        if len(body) < 1:
            raise ModbusError("invalid read response body length")

        byte_count = body[0]
        data = body[1:]
        if byte_count > len(data):
            raise ModbusError(
                f"invalid byte_count={byte_count}, payload_len={len(data)}"
            )
        data = data[:byte_count]
        if len(data) % 2 != 0:
            raise ModbusError(f"invalid register payload length={len(data)}")

        values = list(struct.unpack(f">{len(data) // 2}H", data))
        return values

    def _send_pdu(self, function_code: int, payload: bytes) -> bytes:
        tid = self._next_tid()
        pdu = bytes([function_code]) + payload
        frame = self._build_mbap(tid, len(pdu) + 1) + bytes([self.params.unit_id]) + pdu

        sock = socket.create_connection(
            (self.params.host, self.params.port),
            timeout=self.params.timeout_sec,
        )
        try:
            sock.settimeout(self.params.timeout_sec)
            sock.sendall(frame)

            header = self._recv_exact(sock, 7)
            resp_tid, protocol_id, length, unit_id = struct.unpack(">HHHB", header)

            if protocol_id != 0:
                raise ModbusError(f"invalid protocol_id={protocol_id}")
            if resp_tid != tid:
                raise ModbusError(f"transaction id mismatch: req={tid}, resp={resp_tid}")
            if unit_id != self.params.unit_id:
                raise ModbusError(
                    f"unit id mismatch: req={self.params.unit_id}, resp={unit_id}"
                )
            if length <= 1:
                raise ModbusError(f"invalid mbap length={length}")

            pdu_resp = self._recv_exact(sock, length - 1)
            if not pdu_resp:
                raise ModbusError("empty response pdu")

            resp_fc = pdu_resp[0]
            if resp_fc == (function_code | 0x80):
                if len(pdu_resp) < 2:
                    raise ModbusError("invalid exception response")
                raise ModbusExceptionResponse(function_code, pdu_resp[1])
            if resp_fc != function_code:
                raise ModbusError(
                    f"unexpected function code: req=0x{function_code:02X}, "
                    f"resp=0x{resp_fc:02X}"
                )
            return pdu_resp[1:]
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _next_tid(self) -> int:
        with self._tid_lock:
            self._tid = (self._tid + 1) % 0x10000
            return self._tid

    @staticmethod
    def _build_mbap(transaction_id: int, length: int) -> bytes:
        return struct.pack(">HHH", transaction_id, 0, length)

    @staticmethod
    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) != size:
            raise ModbusError(f"socket closed early, expected={size}, got={len(data)}")
        return bytes(data)
