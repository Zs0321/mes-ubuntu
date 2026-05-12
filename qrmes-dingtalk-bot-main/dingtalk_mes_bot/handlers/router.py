from __future__ import annotations

from dataclasses import dataclass

from ..models import IncomingMessage
from ..services.doc_action_service import DocActionService
from ..services.faq_service import FaqService
from ..services.image_query_service import ImageQueryService
from ..services.llm_answer_service import LlmAnswerService
from ..services.mes_answer_service import MesAnswerService


@dataclass(slots=True)
class MessageRouter:
    faq_service: FaqService
    mes_answer_service: MesAnswerService
    llm_answer_service: LlmAnswerService
    image_query_service: ImageQueryService
    doc_action_service: DocActionService | None = None
    permission_query_service: object | None = None
    diagnosis_service: object | None = None

    def route(self, message: IncomingMessage) -> str:
        text = message.text.strip()
        if not text:
            return "请直接发送你的 MES 问题，我会尽量帮你定位。"

        weather_reply = self._reply_for_non_mes_boundary(text)
        if weather_reply:
            return weather_reply

        summary_followup_reply = self._reply_for_summary_followup(text)
        if summary_followup_reply:
            return summary_followup_reply

        requirement_planning_reply = self._reply_for_requirement_planning(text)
        if requirement_planning_reply:
            return requirement_planning_reply

        usage_ranking_reply = self._reply_for_usage_ranking(text)
        if usage_ranking_reply:
            return usage_ranking_reply

        quote_capability_reply = self._reply_for_quote_capability(text)
        if quote_capability_reply:
            return quote_capability_reply

        mes_overview_reply = self._reply_for_mes_capability_overview(text)
        if mes_overview_reply:
            return mes_overview_reply

        lowered_text = text.lower()
        if ('权限太高' in text or '权限过高' in text or '直接改代码' in text or '改代码' in text) and ('代码' in text or '权限' in text or 'code' in lowered_text):
            return (
                '不会因为普通群聊提问就直接改代码。\n\n'
                '我在钉钉里主要负责回答 MES 问题、整理需求、说明系统能力和辅助排查；如果涉及代码修改，也应该先形成明确问题、修改范围和验证结果，再由部署/审核流程控制上线。'
            )

        if self.permission_query_service and self.permission_query_service.is_permission_question(text):
            if message.image_download_codes:
                return self.permission_query_service.reply_for_images(
                    message.image_download_codes,
                    user_text=text,
                    sender_staff_id=message.sender_staff_id,
                    sender_nick=message.sender_nick,
                )
            serial = self.permission_query_service.extract_serial(text)
            if serial:
                return self.permission_query_service.reply_for_serial(
                    serial,
                    sender_staff_id=message.sender_staff_id,
                    sender_nick=message.sender_nick,
                )
            return "请直接把序列号发给我，或者发二维码/标签图片，我来帮你判断当前提问人有没有对应工序权限。"

        if message.image_download_codes:
            return self.image_query_service.reply_for_images(message.image_download_codes, user_text=text)

        if self.diagnosis_service:
            if hasattr(self.diagnosis_service, 'diagnose_message'):
                diagnosis_reply = self.diagnosis_service.diagnose_message(message)
                if diagnosis_reply:
                    return diagnosis_reply
            elif self.diagnosis_service.can_handle(text):
                return self.diagnosis_service.diagnose(text)

        chitchat = self._reply_for_chitchat(text)
        if chitchat:
            return chitchat

        faq = self.faq_service.answer(text)
        if faq:
            return faq

        if self.doc_action_service:
            doc_reply = self.doc_action_service.maybe_handle(message)
            if doc_reply:
                return doc_reply

        mes = self.mes_answer_service.answer(text)
        if mes:
            return mes

        llm = self.llm_answer_service.answer(text)
        if llm:
            return llm

        return "我可以先帮你回答常见 MES 问题，也支持序列号查询、照片统计和部分权限判断。你可以直接问，比如“如何同步项目”“为什么待复核”“为什么401”。"

    def _reply_for_chitchat(self, text: str) -> str | None:
        content = (text or "").strip()
        if not content:
            return None

        base_answer = None
        if "我是谁" in content:
            base_answer = "我只能看到你在钉钉里的昵称和当前会话信息；如果你是在问机器人身份，我是 MES小客服。"
        elif "你叫什么" in content or "你是谁" in content:
            base_answer = "我叫 MES小客服，是这套 MES 系统里的群聊助手。"
        elif "你来自哪里" in content:
            base_answer = "我来自你们当前这套 MES 机器人能力，和 MES 服务部署在一起。"
        elif "客服" in content and ("专业" in content or "专业性" in content):
            base_answer = "收到，我会按专业客服的方式回答：先确认问题，再给清晰、可执行的处理建议。"
        elif "谁发明" in content or "谁开发" in content:
            base_answer = "我是你们这套 MES 项目里扩展出来的机器人能力，由 MES 的开发与运维一起做出来。"
        elif "你能帮我做什么" in content or "你会做什么" in content:
            base_answer = "我现在主要能帮助回答常见 MES 问题、查询部分实时统计、识别标签图片并辅助做基础排查。"
        elif "小艾是谁" in content or ("客服" in content and "谁" in content):
            base_answer = "小艾就是当前 MES 系统的群聊助手，也就是我。"
        elif "变聪明" in content or "更聪明" in content:
            base_answer = "如果有变聪明，是因为后台模型和知识库在持续更新；有问题你可以继续问，我尽量答得更准。"
        elif "大模型" in content or "模型是啥" in content or "用的什么模型" in content:
            base_answer = "我当前文本问答主链路接的是 Hermes，运行在局域网里的独立 Hermes 服务上；图片识别仍保留原来的视觉识别链路。"
        elif "hermes" in content.lower() or "赫尔墨斯" in content:
            base_answer = "Hermes 是当前机器人接入的智能问答后端，主要负责文本理解、意图判断和回答生成；现在钉钉文本问答主链路走 Hermes。"
        elif "为什么你有时候答不出来" in content:
            base_answer = "有些问题如果还没接到真实查询接口，或者问题表达太泛，我就只能先给出基础说明，没法直接返回准确业务数据。"
        elif "怎么问你更容易答对" in content:
            base_answer = "最容易答对的方式是把问题说具体一点，最好带上序列号、项目名、日期或你想查询的统计口径。"

        if not base_answer:
            return None

        polished = self.llm_answer_service.answer(
            f"请基于这句固定事实，用自然、简短、口语化的中文补充 1 句话说明，不要改变事实，不要编造：{base_answer}"
        )
        if polished and polished != base_answer:
            polished_clean = polished.strip()
            base_clean = base_answer.strip()
            if polished_clean and base_clean not in polished_clean and polished_clean not in base_clean:
                return base_answer + chr(10) + polished_clean
        return base_answer

    def _reply_for_requirement_planning(self, text: str) -> str | None:
        content = (text or "").strip()
        if not content:
            return None
        lowered = content.lower()
        planning_keywords = (
            'spec', '需求', '实现方式', '任务', '拆解', '整理', '总结', '方案', '排期', '开发需求'
        )
        trigger_keywords = (
            '帮我', '请你', '你可以', '可以帮', '能不能', '能否', '转成', '转化', '整理', '总结', '输出', '写成', '实现方式', 'spec'
        )
        idea_keywords = (
            '我有一个想法', '能不能做到', '能否做到', '可不可以做到', '想做一个', '做一个',
            '提醒', '通知', '状态流转', '流程流转', '断点', '闭环', '审批', '待办', '节点'
        )
        has_planning_keyword = any(keyword in lowered or keyword in content for keyword in planning_keywords)
        has_trigger_keyword = any(keyword in lowered or keyword in content for keyword in trigger_keywords)
        has_idea_keyword = any(keyword in lowered or keyword in content for keyword in idea_keywords)
        long_business_idea = len(content) >= 30 and has_idea_keyword and ('mes' in lowered or '系统' in content or 'app' in lowered)
        if not has_planning_keyword and not long_business_idea:
            return None
        if not has_trigger_keyword and not long_business_idea and len(content) < 30:
            return None
        prompt = (
            '你现在是 MES 需求架构与产品整理助手。请把用户这段话整理成正式、可落地的 spec 初稿，始终用简体中文，避免空话。\n'
            '输出顺序固定为：\n'
            '1. 需求背景\n'
            '2. 目标\n'
            '3. 业务流程\n'
            '4. 状态流转\n'
            '5. 通知规则\n'
            '6. 功能点清单\n'
            '7. 实现方式\n'
            '8. 任务拆解\n'
            '9. 验收标准\n'
            '10. 待确认项\n'
            '如果信息不足，也先按上述结构给出初稿，但不要编造不存在的系统现状。\n\n'
            f'用户原文：{content}'
        )
        planned = self.llm_answer_service.answer(prompt)
        if planned:
            return planned
        return (
            '我先基于你当前这段话整理一个 spec 初稿；信息不足的地方先标为待确认。\n\n'
            f'用户原文：{content}\n\n'
            '1. 需求背景\n'
            '- 当前需要把群聊或口头描述中的需求整理成可执行的 MES 需求文档和开发任务。\n\n'
            '2. 目标\n'
            '- 明确要解决的问题、涉及对象、期望结果和上线后的验收口径。\n\n'
            '3. 业务流程\n'
            '- 梳理从需求触发、数据录入、状态变化、人员处理到结果反馈的完整流程。\n\n'
            '4. 状态流转\n'
            '- 待确认：需要补充有哪些业务状态、每个状态由谁触发、能流转到哪些下一状态。\n\n'
            '5. 通知规则\n'
            '- 待确认：需要补充哪些节点要通知、通知对象是谁、通过钉钉还是 MES 站内消息提醒。\n\n'
            '6. 功能点清单\n'
            '- 需求录入与查看。\n'
            '- 状态更新与流转记录。\n'
            '- 责任人、时间、处理结果留痕。\n'
            '- 查询、筛选和统计入口。\n\n'
            '7. 实现方式\n'
            '- 后端增加对应数据模型、接口和权限校验。\n'
            '- 前端增加列表、详情、编辑和状态操作入口。\n'
            '- 如涉及提醒，接入现有钉钉机器人或消息通知链路。\n\n'
            '8. 任务拆解\n'
            '- 确认字段、状态和权限范围。\n'
            '- 设计数据库表和接口。\n'
            '- 开发前端页面与操作入口。\n'
            '- 联调通知、日志和权限。\n'
            '- 测试典型流程和异常流程。\n\n'
            '9. 验收标准\n'
            '- 用户能按预期创建、查看、处理和追踪该需求相关业务。\n'
            '- 状态流转、通知对象、权限控制和操作留痕符合现场规则。\n\n'
            '10. 待确认项\n'
            '- 具体业务对象、字段清单、角色权限、状态枚举、通知节点、统计口径和期望上线范围。'
        )

    def _reply_for_usage_ranking(self, text: str) -> str | None:
        content = (text or '').strip()
        if not content:
            return None
        lowered = content.lower()
        usage_keywords = ('使用率', '使用排行', '使用排名', '谁用得最多', '谁使用最多', '活跃度', '登录次数', '操作次数')
        mes_keywords = ('mes', '系统', '后台')
        if not any(keyword in content or keyword in lowered for keyword in usage_keywords):
            return None
        if not any(keyword in content or keyword in lowered for keyword in mes_keywords):
            return None
        return (
            '这个问题需要按统计口径来查，不能直接凭感觉回答。\n\n'
            'MES 使用率一般可以按这几种口径看：\n'
            '1. 登录次数：谁打开系统最多。\n'
            '2. 操作次数：谁提交、扫码、报工、审核等动作最多。\n'
            '3. 活跃天数：谁持续使用最稳定。\n'
            '4. 模块使用量：谁在生产、质检、仓库、项目等模块里操作最多。\n\n'
            '你补一个时间范围，比如“今天 / 本周 / 本月”，我再按对应口径帮你整理查询方式或统计结果。'
        )

    def _reply_for_quote_capability(self, text: str) -> str | None:
        content = (text or '').strip()
        if not content:
            return None
        lowered = content.lower()
        quote_keywords = ('报价', '询价', 'quote')
        capability_keywords = ('能', '可以', '会', '支持', '还能')
        if not any(keyword in content or keyword in lowered for keyword in quote_keywords):
            return None
        if not any(keyword in content or keyword in lowered for keyword in capability_keywords):
            return None
        return (
            '能。\n\n'
            '我可以做这几类报价相关工作：\n'
            '1. BOM/物料报价：按材质、重量、工艺、机加工、表处、装配等信息给出估算价。\n'
            '2. 方案对比报价：对比量产/非量产、开模/机加、不同材质或工艺路线的价格差异。\n'
            '3. 表格整理与结果输出：你发 BOM 表、Excel、图片表格或直接粘贴几行数据都可以。\n'
            '4. 异常项复核：如果某些零件报价和经验价差很多，我可以帮你定位原因。\n\n'
            '你直接发物料名称、材质、重量、工艺和数量，或者直接把清单发来，我就可以开始报。'
        )

    def _reply_for_non_mes_boundary(self, text: str) -> str | None:
        content = (text or '').strip()
        if not content:
            return None
        lowered = content.lower()
        if '天气' in content or 'weather' in lowered:
            return '我目前主要支持 MES 相关查询、需求整理、系统功能说明和部分权限判断，暂不支持直接查询天气。你如果愿意，我可以继续帮你整理 MES 需求、解释 Hermes，或者介绍 MES 系统模块。'
        time_keywords = ('几点了', '现在几点', '当前时间', '现在时间', 'time')
        if any(keyword in content or keyword in lowered for keyword in time_keywords):
            return '我目前主要支持 MES 相关查询、需求整理、系统功能说明和部分权限判断，暂不支持直接查询时间。你如果愿意，我可以继续帮你整理 MES 需求、解释 Hermes，或者介绍 MES 系统模块。'
        return None

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
            '请把下面这段用户输入理解为“继续总结/重新总结”的请求，用简短、自然的中文先说明你会继续承接，再把用户当前可见内容整理成 3-5 条要点，不要输出和 MES 能力介绍无关的兜底文案。\n\n'
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
            'MES 系统一般会覆盖这些核心模块：\n'
            '1. 生产工单与排产：工单下发、工序推进、完工回传。\n'
            '2. 报工与状态流转：生产、测试、包装、出货检等环节流转。\n'
            '3. 条码/序列号追踪：按序列号追踪产品、工序、人员和时间。\n'
            '4. 质量检验：首检、巡检、终检、不良记录与返工闭环。\n'
            '5. 物料与库存协同：领料、退料、在制品和库存联动。\n'
            '6. 图片与过程留痕：工序照片、附件、异常记录归档。\n'
            '7. 权限与审批：按岗位、工序、角色控制操作权限。\n'
            '8. 统计与报表：产量、节拍、在制品、异常和项目维度统计。\n'
            '如果你愿意，我可以继续按你们现在这套系统，给你展开某个模块的实现方式。'
        )
