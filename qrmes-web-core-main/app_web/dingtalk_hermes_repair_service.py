from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROUTE_OLD_SNIPPET = """    def route(self, message: IncomingMessage) -> str:
        text = message.text.strip()
        if not text:
            return \"请直接发送你的 MES 问题，我会尽量帮你定位。\"

        requirement_planning_reply = self._reply_for_requirement_planning(text)
        if requirement_planning_reply:
            return requirement_planning_reply

        if self.permission_query_service and self.permission_query_service.is_permission_question(text):
"""

ROUTE_NEW_SNIPPET = """    def route(self, message: IncomingMessage) -> str:
        text = message.text.strip()
        if not text:
            return \"请直接发送你的 MES 问题，我会尽量帮你定位。\"

        weather_reply = self._reply_for_non_mes_boundary(text)
        if weather_reply:
            return weather_reply

        summary_followup_reply = self._reply_for_summary_followup(text)
        if summary_followup_reply:
            return summary_followup_reply

        requirement_planning_reply = self._reply_for_requirement_planning(text)
        if requirement_planning_reply:
            return requirement_planning_reply

        mes_overview_reply = self._reply_for_mes_capability_overview(text)
        if mes_overview_reply:
            return mes_overview_reply

        if self.permission_query_service and self.permission_query_service.is_permission_question(text):
"""

CHITCHAT_OLD_SNIPPET = """        elif \"大模型\" in content or \"模型是啥\" in content or \"用的什么模型\" in content:
            base_answer = \"我当前文本问答主链路接的是 Hermes，运行在局域网里的独立 Hermes 服务上；图片识别仍保留原来的视觉识别链路。\"
        elif \"为什么你有时候答不出来\" in content:
            base_answer = \"有些问题如果还没接到真实查询接口，或者问题表达太泛，我就只能先给出基础说明，没法直接返回准确业务数据。\"
"""

CHITCHAT_NEW_SNIPPET = """        elif \"大模型\" in content or \"模型是啥\" in content or \"用的什么模型\" in content:
            base_answer = \"我当前文本问答主链路接的是 Hermes，运行在局域网里的独立 Hermes 服务上；图片识别仍保留原来的视觉识别链路。\"
        elif \"hermes\" in content.lower() or \"赫尔墨斯\" in content:
            base_answer = \"Hermes 是当前机器人接入的智能问答后端，主要负责文本理解、意图判断和回答生成；现在钉钉文本问答主链路走 Hermes。\"
        elif \"为什么你有时候答不出来\" in content:
            base_answer = \"有些问题如果还没接到真实查询接口，或者问题表达太泛，我就只能先给出基础说明，没法直接返回准确业务数据。\"
"""

REQUIREMENT_OLD_SNIPPET = """    def _reply_for_requirement_planning(self, text: str) -> str | None:
        content = (text or \"\").strip()
        if not content:
            return None
        lowered = content.lower()
        planning_keywords = (
            'spec', '需求', '实现方式', '任务', '拆解', '整理', '总结', '方案', '排期', '开发需求'
        )
        trigger_keywords = (
            '帮我', '请你', '转成', '整理', '总结', '输出', '写成', '实现方式', 'spec'
        )
        if not any(keyword in lowered or keyword in content for keyword in planning_keywords):
            return None
        if not any(keyword in lowered or keyword in content for keyword in trigger_keywords):
            return None
        prompt = (
            '你现在是 MES 需求架构与产品整理助手。请把用户这段话整理成正式、可落地的 spec 初稿，始终用简体中文，避免空话。\\n'
            '输出顺序固定为：\\n'
            '1. 需求背景\\n'
            '2. 目标\\n'
            '3. 业务流程\\n'
            '4. 状态流转\\n'
            '5. 通知规则\\n'
            '6. 功能点清单\\n'
            '7. 实现方式\\n'
            '8. 任务拆解\\n'
            '9. 验收标准\\n'
            '10. 待确认项\\n'
            '如果信息不足，也先按上述结构给出初稿，但不要编造不存在的系统现状。\\n\\n'
            f'用户原文：{content}'
        )
        return self.llm_answer_service.answer(prompt)
"""

REQUIREMENT_NEW_SNIPPET = """    def _reply_for_requirement_planning(self, text: str) -> str | None:
        content = (text or \"\").strip()
        if not content:
            return None
        lowered = content.lower()
        planning_keywords = (
            'spec', '需求', '实现方式', '任务', '拆解', '整理', '总结', '方案', '排期', '开发需求'
        )
        trigger_keywords = (
            '帮我', '请你', '转成', '整理', '总结', '输出', '写成', '实现方式', 'spec'
        )
        has_planning_keyword = any(keyword in lowered or keyword in content for keyword in planning_keywords)
        has_trigger_keyword = any(keyword in lowered or keyword in content for keyword in trigger_keywords)
        if not has_planning_keyword:
            return None
        if not has_trigger_keyword and len(content) < 30:
            return None
        prompt = (
            '你现在是 MES 需求架构与产品整理助手。请把用户这段话整理成正式、可落地的 spec 初稿，始终用简体中文，避免空话。\\n'
            '输出顺序固定为：\\n'
            '1. 需求背景\\n'
            '2. 目标\\n'
            '3. 业务流程\\n'
            '4. 状态流转\\n'
            '5. 通知规则\\n'
            '6. 功能点清单\\n'
            '7. 实现方式\\n'
            '8. 任务拆解\\n'
            '9. 验收标准\\n'
            '10. 待确认项\\n'
            '如果信息不足，也先按上述结构给出初稿，但不要编造不存在的系统现状。\\n\\n'
            f'用户原文：{content}'
        )
        return self.llm_answer_service.answer(prompt)

    def _reply_for_non_mes_boundary(self, text: str) -> str | None:
        content = (text or '').strip()
        if not content:
            return None
        lowered = content.lower()
        if '天气' not in content and 'weather' not in lowered:
            return None
        return '我目前主要支持 MES 相关查询、需求整理、系统功能说明和部分权限判断，暂不支持直接查询天气。你如果愿意，我可以继续帮你整理 MES 需求、解释 Hermes，或者介绍 MES 系统模块。'

    def _reply_for_summary_followup(self, text: str) -> str | None:
        content = (text or '').strip()
        if not content:
            return None
        followup_keywords = ('再总结一下', '再说一遍', '继续总结', '再总结', '总结一下')
        if not any(keyword in content for keyword in followup_keywords):
            return None
        if len(content) <= 12:
            return '可以继续总结。为了避免我脱离上下文，请把刚才那段内容再贴一次，或者直接说“把上面那段整理成 spec / 要点 / 结论”。'
        return self.llm_answer_service.answer(
            '请把下面这段用户输入理解为“继续总结/重新总结”的请求，用简短、自然的中文先说明你会继续承接，再把用户当前可见内容整理成 3-5 条要点，不要输出和 MES 能力介绍无关的兜底文案。\\n\\n'
            f'用户原文：{content}'
        )

    def _reply_for_mes_capability_overview(self, text: str) -> str | None:
        content = (text or '').strip()
        if not content:
            return None
        lowered = content.lower()
        overview_keywords = (
            'mes系统都有什么功能', 'mes系统有什么功能', 'mes都有什么功能', 'mes有哪些功能',
            '有哪些模块', '能做什么', '系统功能'
        )
        if not any(keyword in lowered or keyword in content for keyword in overview_keywords):
            return None
        return (
            'MES 系统一般会覆盖这些核心模块：\\n'
            '1. 生产工单与排产：工单下发、工序推进、完工回传。\\n'
            '2. 报工与状态流转：生产、测试、包装、出货检等环节流转。\\n'
            '3. 条码/序列号追踪：按序列号追踪产品、工序、人员和时间。\\n'
            '4. 质量检验：首检、巡检、终检、不良记录与返工闭环。\\n'
            '5. 物料与库存协同：领料、退料、在制品和库存联动。\\n'
            '6. 图片与过程留痕：工序照片、附件、异常记录归档。\\n'
            '7. 权限与审批：按岗位、工序、角色控制操作权限。\\n'
            '8. 统计与报表：产量、节拍、在制品、异常和项目维度统计。\\n'
            '如果你愿意，我可以继续按你们现在这套系统，给你展开某个模块的实现方式。'
        )
"""


@dataclass(slots=True)
class DingTalkHermesRepairService:
    base_url: str
    workspace: str
    model: str = 'gpt-5.5'
    timeout: float = 60.0

    def suggest_issue_fixes(self, *, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        issues = list(snapshot.get('suspicious_live_interactions') or [])
        results: list[dict[str, Any]] = []
        for index, item in enumerate(issues, start=1):
            prompt = (
                '你是钉钉机器人可疑回答分析助手。请基于下面这条可疑问答输出严格 JSON，不要输出任何多余文字。\n'
                '返回字段固定为：issue_id,question,reply,root_cause,fix_strategy。\n\n'
                f'issue_id=issue-{index}\n'
                f'question={item.get("question") or ""}\n'
                f'reply={item.get("reply") or ""}\n'
                f'sender={item.get("sender") or ""}\n'
            )
            raw = self._chat([
                {'role': 'system', 'content': '你只返回 JSON。'},
                {'role': 'user', 'content': prompt},
            ])
            if not raw:
                results.append({
                    'issue_id': f'issue-{index}',
                    'question': item.get('question') or '',
                    'reply': item.get('reply') or '',
                    'root_cause': '',
                    'fix_strategy': '',
                    'raw': '',
                })
                continue
            try:
                data = json.loads(raw)
            except Exception:
                data = {
                    'issue_id': f'issue-{index}',
                    'question': item.get('question') or '',
                    'reply': item.get('reply') or '',
                    'root_cause': 'Hermes 返回了非 JSON 内容',
                    'fix_strategy': '',
                }
            if not isinstance(data, dict):
                data = {}
            data.setdefault('issue_id', f'issue-{index}')
            data.setdefault('question', item.get('question') or '')
            data.setdefault('reply', item.get('reply') or '')
            data.setdefault('root_cause', '')
            data.setdefault('fix_strategy', '')
            data['raw'] = raw
            results.append(data)
        return results

    def suggest_fix(self, *, snapshot: dict[str, Any], source_root: Path) -> dict[str, Any]:
        target = source_root / 'dingtalk_mes_bot/handlers/router.py'
        current = target.read_text(encoding='utf-8')[:20000] if target.exists() else ''
        prompt = (
            '你是钉钉机器人 Python 修复助手。请基于最近巡检快照和 router.py 内容，输出严格 JSON，不要输出任何多余文字。\n'
            '返回字段固定为：summary,target_file,old_string,new_string,verification。\n'
            '要求：仅在非常确定时返回 old_string/new_string；无法安全修改则返回空字符串。\n\n'
            f'巡检摘要: {json.dumps(snapshot, ensure_ascii=False)[:8000]}\n'
            'router.py 内容如下:\n'
            f'{current}'
        )
        raw = self._chat([
            {'role': 'system', 'content': '你只返回 JSON。'},
            {'role': 'user', 'content': prompt},
        ])
        if not raw:
            return self._rule_based_fix(target=target)
        try:
            data = json.loads(raw)
        except Exception:
            fallback = self._rule_based_fix(target=target)
            if fallback.get('target_file'):
                fallback['summary'] = fallback.get('summary') or 'Hermes 返回了非 JSON 内容，已切到规则修复。'
                fallback['raw'] = raw
                return fallback
            return {'summary': 'Hermes 返回了非 JSON 内容', 'target_file': '', 'old_string': '', 'new_string': '', 'verification': [], 'raw': raw}
        if not isinstance(data, dict):
            return self._rule_based_fix(target=target)
        data.setdefault('summary', '')
        data.setdefault('target_file', '')
        data.setdefault('old_string', '')
        data.setdefault('new_string', '')
        data['verification'] = list(data.get('verification') or [])
        data['raw'] = raw
        if data['target_file'] and data['old_string'] and data['new_string']:
            return data
        fallback = self._rule_based_fix(target=target)
        if fallback.get('target_file'):
            fallback['summary'] = data.get('summary') or fallback.get('summary')
            fallback['raw'] = raw
            return fallback
        return data

    def _chat(self, messages: list[dict[str, Any]]) -> str | None:
        if not self.base_url.strip():
            return None
        session = self._post('/api/session/new', {'workspace': self.workspace, 'model': self.model})
        session_id = ((session or {}).get('session') or {}).get('session_id')
        if not session_id:
            return None
        merged = []
        for msg in messages:
            content = str(msg.get('content') or '').strip()
            if content:
                merged.append(f'[{msg.get("role") or "user"}] {content}')
        prompt = '\n\n'.join(merged).strip()
        if not prompt:
            return None
        answer = self._post('/api/chat', {
            'session_id': session_id,
            'workspace': self.workspace,
            'model': self.model,
            'message': prompt,
        })
        raw = (answer or {}).get('answer')
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        req = urllib.request.Request(
            self.base_url.rstrip('/') + path,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode('utf-8', errors='replace')
        except Exception:
            return None
        try:
            data = json.loads(body)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _rule_based_fix(self, *, target: Path) -> dict[str, Any]:
        if not target.exists():
            return {'summary': '', 'target_file': '', 'old_string': '', 'new_string': '', 'verification': []}
        original = target.read_text(encoding='utf-8')
        updated = original
        updated = updated.replace(ROUTE_OLD_SNIPPET, ROUTE_NEW_SNIPPET, 1)
        updated = updated.replace(CHITCHAT_OLD_SNIPPET, CHITCHAT_NEW_SNIPPET, 1)
        updated = updated.replace(REQUIREMENT_OLD_SNIPPET, REQUIREMENT_NEW_SNIPPET, 1)
        if updated == original:
            return {
                'summary': '钉钉路由修复规则已在当前源码中存在。',
                'target_file': 'dingtalk_mes_bot/handlers/router.py',
                'old_string': '',
                'new_string': '',
                'verification': [
                    '确认天气/Spec/Hermes/MES 功能/继续总结类问题不再回旧兜底文案。',
                ],
            }
        return {
            'summary': 'Hermes 未给出可应用 patch，已切换到钉钉路由规则修复模板。',
            'target_file': 'dingtalk_mes_bot/handlers/router.py',
            'old_string': original,
            'new_string': updated,
            'verification': [
                '确认“帮我写spec/整理需求/实现方式”类问题不再落入权限链路。',
                '确认“mes系统都有什么功能”“什么是Hermes”“天气”类问题不再回落到旧兜底文案。',
                '确认“再总结一下”至少返回承接上下文的继续总结提示。',
            ],
        }
