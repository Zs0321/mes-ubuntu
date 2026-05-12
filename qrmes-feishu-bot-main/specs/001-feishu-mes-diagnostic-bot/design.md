# Design

## Architecture
- feishu_mes_bot.bot_app
  - Flask 入口
  - 处理 URL 验证、事件回调、健康检查
- feishu_mes_bot.message_parser
  - 把飞书消息事件转换为 IncomingMessage
- feishu_mes_bot.handlers.router
  - 统一路由：先确定性排障，再 LLM 兜底
- feishu_mes_bot.services.issue_diagnosis_service
  - 问题分类、目标仓库推断、知识规则匹配、探测结果整合
- feishu_mes_bot.services.repository_catalog
  - 维护 split 仓库名、关键接口、脚本、数据库和日志路径
- feishu_mes_bot.services.probe_service
  - 基于 health URL、脚本、文件存在性做轻量探测
- feishu_mes_bot.services.feishu_client
  - tenant_access_token 获取与消息发送
- feishu_mes_bot.services.openai_compatible_service / llm_answer_service
  - 可选 LLM 兜底

## Message Flow
1. 飞书把事件推送到 /feishu/event。
2. bot_app 识别 challenge 请求并返回 challenge。
3. 普通消息回调进入 parse_feishu_event。
4. router 根据文本优先调用 issue_diagnosis_service。
5. 诊断结果通过 feishu_client 回复到 chat_id/open_id。

## Rule Strategy
- 使用关键字与领域规则，而不是重型 NLP。
- 一条消息可命中多个问题域。
- 问题域输出结合 repository_catalog 中的接口、脚本、数据库路径。
- probe_service 只做安全的只读探测：HTTP GET、脚本存在性、PID/日志/DB 文件存在性。

## Repo Naming
- 仓库：qrmes-feishu-bot
- Python 包：feishu_mes_bot
- 结构对齐 qrmes-dingtalk-bot：config/models/message_parser/runtime/reply_engine/service_factory/handlers/services/tests
