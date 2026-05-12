#!/usr/bin/env python3
"""Local edge bridge stub for camera/button integration testing.

Endpoints:
- GET  /api/health
- GET  /api/camera/frame?station_id=S01
- GET  /api/button/next?station_id=S01
- POST /api/button/press   {"station_id":"S01"}
"""

from __future__ import annotations

import io
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict

from flask import Flask, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont


app = Flask(__name__)
_EVENT_LOCK = threading.Lock()
_BUTTON_EVENTS: Dict[str, Deque[dict]] = defaultdict(deque)


def _station_id() -> str:
    arg_station = str(request.args.get("station_id") or "").strip()
    if arg_station:
        return arg_station
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        body_station = str(payload.get("station_id") or "").strip()
        if body_station:
            return body_station
    return "S01"


def _gen_frame(station_id: str) -> bytes:
    width, height = 1280, 720
    now = time.time()
    phase = int(now * 3) % 20
    x = 80 + phase * 40
    y = 140 + (phase % 7) * 20

    image = Image.new("RGB", (width, height), color=(12, 23, 36))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, width - 40, height - 40), outline=(70, 90, 120), width=3)
    draw.rectangle((x, y, x + 120, y + 120), fill=(20, 140, 220))
    draw.rectangle((width - x - 180, height - y - 90, width - x - 20, height - y - 50), fill=(20, 180, 100))

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"EDGE BRIDGE STUB  station={station_id}  {ts}"
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    draw.text((70, 74), text, fill=(230, 236, 242), font=font)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "edge_local_bridge_stub"})


@app.get("/api/camera/frame")
def camera_frame():
    station_id = _station_id()
    payload = _gen_frame(station_id)
    return send_file(
        io.BytesIO(payload),
        mimetype="image/jpeg",
        as_attachment=False,
        download_name=f"{station_id}_frame.jpg",
    )


@app.post("/api/button/press")
def button_press():
    station_id = _station_id()
    event = {
        "event_id": f"{station_id}-{int(time.time() * 1000)}",
        "station_id": station_id,
        "ts": datetime.now().isoformat(),
        "pressed": True,
    }
    with _EVENT_LOCK:
        _BUTTON_EVENTS[station_id].append(event)
        if len(_BUTTON_EVENTS[station_id]) > 100:
            _BUTTON_EVENTS[station_id].popleft()
    return jsonify({"ok": True, "event": event})


@app.get("/api/button/next")
def button_next():
    station_id = _station_id()
    with _EVENT_LOCK:
        queue = _BUTTON_EVENTS[station_id]
        if queue:
            return jsonify(queue.popleft())
    return jsonify(
        {
            "pressed": False,
            "station_id": station_id,
            "ts": datetime.now().isoformat(),
        }
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run edge local bridge stub")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19091)
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
