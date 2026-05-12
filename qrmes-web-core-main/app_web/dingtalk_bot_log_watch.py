#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def _resolve_path(candidates: tuple[str, ...]) -> Path:
    for item in candidates:
        path = Path(item)
        if path.exists():
            return path
    return Path(candidates[0])


LIVE_LOG = _resolve_path((
    '/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime.log',
    '/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime.log',
))
LEGACY_LOG = _resolve_path((
    '/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime_legacy.log',
    '/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime_legacy.log',
))
STATE_PATH = Path.home() / '.hermes' / 'scripts' / 'state' / 'dingtalk_bot_log_watch_offsets.json'
SHARED_STATE_PATH = _resolve_path((
    '/volume2/qrmes-v3.0/qrmes-dingtalk-bot/monitor/log_watch_latest.json',
    '/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-dingtalk-bot/monitor/log_watch_latest.json',
))
MAX_BYTES = 200_000
MAX_INTERACTIONS = 20

INCOMING_RE = re.compile(r'incoming sender=(?P<sender>.*?) .*? text=(?P<text>.*)', re.DOTALL)
REPLY_RE = re.compile(r'sending reply: (?P<reply>.*)', re.DOTALL)


def load_json_file(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def load_state() -> dict:
    return load_json_file(STATE_PATH)


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def read_new_text(path: Path, state: dict) -> str:
    if not path.exists():
        return ''
    size = path.stat().st_size
    key = str(path)
    offset = int(state.get(key, 0) or 0)
    if offset < 0 or offset > size:
        offset = max(0, size - MAX_BYTES)
    with path.open('r', encoding='utf-8', errors='replace') as fh:
        fh.seek(offset)
        data = fh.read()
        state[key] = fh.tell()
    return data


def merge_lines(text: str) -> list[str]:
    blocks: list[str] = []
    current = ''
    for raw in text.splitlines():
        line = raw.rstrip('\n')
        if line.startswith('INFO:') or line.startswith('ERROR:') or line.startswith('WARNING:'):
            if current:
                blocks.append(current)
            current = line
        else:
            if current:
                current += '\n' + line
            elif line.strip():
                current = line
    if current:
        blocks.append(current)
    return blocks


def extract_interactions(blocks: list[str]) -> list[dict]:
    interactions: list[dict] = []
    pending: dict | None = None
    for block in blocks:
        if 'incoming sender=' in block:
            m = INCOMING_RE.search(block)
            if not m:
                continue
            pending = {
                'sender': m.group('sender').strip(),
                'question': m.group('text').strip(),
            }
            continue
        if 'sending reply:' in block and pending:
            m = REPLY_RE.search(block)
            if not m:
                continue
            reply = m.group('reply').strip()
            interactions.append({
                'sender': pending['sender'],
                'question': pending['question'],
                'reply': reply,
                'suspicious': is_suspicious(pending['question'], reply),
            })
            pending = None
    return interactions[-MAX_INTERACTIONS:]


def merge_interactions(previous: list[dict], fresh: list[dict]) -> list[dict]:
    merged = [item for item in (previous or []) if isinstance(item, dict)]
    for item in fresh or []:
        if not isinstance(item, dict):
            continue
        merged.append(item)
    normalized: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in reversed(merged):
        key = (
            str(item.get('sender') or ''),
            str(item.get('question') or ''),
            str(item.get('reply') or ''),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    normalized.reverse()
    return normalized[-MAX_INTERACTIONS:]


def is_suspicious(question: str, reply: str) -> bool:
    q = (question or '').strip()
    r = (reply or '').strip()
    if not q or not r:
        return False
    generic = '我可以先帮你回答常见 MES 问题'
    permission_fallback = '请直接把序列号发给我，或者发二维码/标签图片'
    if generic in r:
        return True
    if ('大模型' in q or '模型' in q or '聪明' in q) and 'Hermes' not in r:
        return True
    if ('web发布' in q or '401' in q or '403' in q or '打不开' in q or '报错' in q) and ('问题归类：' not in r and generic in r):
        return True
    if ('图片' in q or '序列号' in q) and ('请提供图片' in r or '通常用于追溯' in r):
        return True
    if any(word in q for word in ('spec', 'Spec', '实现方式', '任务', '需求', '总结')) and permission_fallback in r:
        return True
    return False


def classify_question(question: str, reply: str = '') -> str:
    q = (question or '').strip().lower()
    r = (reply or '').strip().lower()
    if any(word in q for word in ('spec', '实现方式', '任务', '需求', '总结', '排期', '方案')):
        return '需求整理类'
    if any(word in q for word in ('web发布', '401', '403', '500', '报错', '打不开', '异常', 'timeout', '失败')):
        return '诊断排障类'
    if any(word in q for word in ('图片', '标签', '二维码', '照片')):
        return '图片识别类'
    if any(word in q for word in ('序列号', '工序', '项目', '权限')):
        return 'MES查询类'
    if any(word in q for word in ('你是谁', '你叫什么', '大模型', '变聪明', '几岁', '天气')):
        return '闲聊类'
    if '我可以先帮你回答常见 mes 问题' in r:
        return '错路由类'
    return '其他类'


def build_category_stats(items: list[dict]) -> list[dict]:
    counter: dict[str, int] = {}
    suspicious_counter: dict[str, int] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        category = item.get('category') or classify_question(str(item.get('text') or ''), str(item.get('reply_full') or ''))
        counter[category] = counter.get(category, 0) + 1
        if item.get('suspicious'):
            suspicious_counter[category] = suspicious_counter.get(category, 0) + 1
    ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        {
            'category': category,
            'count': count,
            'suspicious_count': suspicious_counter.get(category, 0),
        }
        for category, count in ordered
    ]


def main() -> None:
    state = load_state()
    previous_shared = load_json_file(SHARED_STATE_PATH)
    live_text = read_new_text(LIVE_LOG, state)
    legacy_text = read_new_text(LEGACY_LOG, state)
    save_state(state)

    live_blocks = merge_lines(live_text)
    legacy_blocks = merge_lines(legacy_text)
    live_interactions = merge_interactions(previous_shared.get('live_interactions') or [], extract_interactions(live_blocks))
    legacy_interactions = merge_interactions(previous_shared.get('legacy_interactions') or [], extract_interactions(legacy_blocks))

    payload = {
        'updated_at': datetime.now().isoformat(),
        'live_log': str(LIVE_LOG),
        'legacy_log': str(LEGACY_LOG),
        'shared_state_path': str(SHARED_STATE_PATH),
        'live_exists': LIVE_LOG.exists(),
        'legacy_exists': LEGACY_LOG.exists(),
        'live_interactions': live_interactions,
        'legacy_interactions': legacy_interactions,
        'live_category_stats': build_category_stats(live_interactions),
        'legacy_category_stats': build_category_stats(legacy_interactions),
        'suspicious_live_count': sum(1 for x in live_interactions if x.get('suspicious')),
        'suspicious_legacy_count': sum(1 for x in legacy_interactions if x.get('suspicious')),
    }
    SHARED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHARED_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
