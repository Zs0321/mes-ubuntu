# qrmes-dingtalk-bot 当前能力 Spec

## 1. 需求背景
- 当前问题：`qrmes-dingtalk-bot` 已从单仓拆出并可独立运行，但仓内现有说明偏碎片化，缺一份直接对应当前代码行为的能力 spec，导致后续继续扩展路由、配置、部署和验收时容易口径不一致。
- 触发场景：需要给开发、运维、业务使用方一份统一文档，说明机器人现在到底能做什么、优先级怎么走、哪些是正式行为、哪些还是待治理项。
- 为什么现在要做：当前仓已经具备 Hermes 文本问答、图片识别、权限判断、文档动作、诊断、spec 整理等多种能力，如果没有一份贴着 `router.py / service_factory.py / config.py` 的 spec，后续改造容易偏离现状。
- 涉及角色：
  - 钉钉群内使用机器人的业务人员
  - 维护机器人运行的开发/运维
  - 后续继续增强 split 仓机器人的开发人员

## 2. 目标
- 业务目标：让业务侧明确机器人支持的提问方式、回复范围和兜底方式，减少“以为支持 / 实际不支持”的误用。
- 系统目标：以当前代码为准，固化消息入口、路由顺序、服务边界、配置项和兼容要求。
- 结果目标：后续新增功能、修复问题、验收测试、部署切换时，都以这份 spec 为统一口径。

## 3. 业务流程
1. 用户在钉钉群内通过 `stream` 或 `http callback` 方式向机器人发消息。
2. 服务把原始钉钉 payload 解析成统一的 `IncomingMessage`。
3. 运行时加载 `.env` 与 `config.py` 中的配置，组装 `router + services`。
4. `MessageRouter.route()` 按固定优先级依次尝试确定性能力与增强服务。
5. 若命中 FAQ、权限、图片、文档、诊断、MES 查询等能力，则直接返回对应结果。
6. 若前面都没有命中，再由 Hermes 文本问答兜底；若 Hermes 仍无结果，则返回固定中文兜底文案。
7. 成功结果回发到钉钉群；空消息或无法处理场景返回引导性文本而不是静默失败。

## 4. 状态流转
- 初始状态：机器人进程启动，完成配置装载、路由装配、钉钉接入监听。
- 处理中：收到消息后依次执行边界拦截、总结跟进、需求整理、能力说明、权限、图片、诊断、FAQ、文档、MES 查询、LLM 兜底。
- 成功：任一能力返回非空文本，即视为本次请求成功并直接结束路由。
- 失败：
  - 配置缺失或外部依赖不可用时，能力层返回空值或引导语；
  - 最终没有任何能力产出时，返回固定兜底说明。
- 重试/终止条件：
  - 权限查询缺少序列号或图片时，提示用户补充材料；
  - spec 整理信息不足时，先输出初稿并显式列出待确认项；
  - Hermes 返回空时，不在本轮反复重试，由固定兜底接管。

## 5. 通知规则
- 谁会收到通知：当前以钉钉群聊中的提问人和群成员为主，没有单独异步通知中心。
- 什么时候通知：消息被路由命中后即时回复；文档动作、权限查询、图片识别、诊断、需求整理都在当前会话内直接返回结果。
- 通知渠道：钉钉群消息回发。
- 通知文案要求：
  - 用中文
  - 适合群聊直接阅读
  - 不要 AI 腔和空话
  - 确定性能力优先给结论和引导，不要先讲原理

## 6. 功能点清单
1. 消息接入
   - 输入：钉钉 `stream` 或 `http callback` 消息
   - 处理：统一进入 `stream_app.py` / `bot_app.py`，转为 `IncomingMessage`
   - 输出：标准化消息对象供 `build_reply()` 使用
2. 非 MES 边界拦截
   - 输入：与天气等无关 MES 的问题
   - 处理：在 router 最前面识别并直接拦截
   - 输出：提示机器人主要支持 MES 查询、需求整理、权限判断等能力
3. 总结跟进
   - 输入：如“再总结一下”“继续总结”
   - 处理：识别跟进类短句，要求用户补回上下文
   - 输出：引导用户贴回原文或明确整理目标
4. spec / 需求整理
   - 输入：包含 `spec/需求/实现方式/任务/拆解/方案/排期/开发需求` 等关键词的文本
   - 处理：拼出固定结构 prompt，交给 `llm_answer_service`
   - 输出：按 10 段结构生成中文 spec 初稿
5. 报价能力说明
   - 输入：询问“能不能报价”“支持哪些报价”类问题
   - 处理：命中固定能力说明
   - 输出：返回 BOM/物料报价、方案对比、表格整理、异常项复核等说明
6. MES 能力概览/闲聊说明
   - 输入：如“你是谁”“你能做什么”“你用的什么模型”
   - 处理：先给固定事实，再尝试用 LLM 润色补一句
   - 输出：自然、简短的机器人说明
7. 权限查询
   - 输入：文本序列号、图片标签、发送人 staff_id / nick
   - 处理：先判断是否权限问题，再走文本或图片权限分支
   - 输出：权限判断结果，或提示用户补充序列号/图片
8. 图片识别与图片查询
   - 输入：图片下载码 + 可选文本
   - 处理：下载图片、做视觉识别、结合前缀和 MES 查询封装回答
   - 输出：标签/二维码/项目等识别与查询结果
9. 故障诊断
   - 输入：日志描述、文件、附件、问题文本
   - 处理：优先调用 `IssueDiagnosisService`
   - 输出：排查建议、证据方向、可能的定位路径
10. FAQ
   - 输入：常见 MES 问题
   - 处理：`FaqService.answer()` 直接命中
   - 输出：固定中文答复
11. 文档动作
   - 输入：统计结果、文档动作指令
   - 处理：通过 `DocActionService + DingTalkDocService` 写入钉钉文档
   - 输出：文档创建/更新结果
12. MES 查询
   - 输入：MES 业务问题
   - 处理：`MesQueryService + MesAnswerService`
   - 输出：规则型或实时查询回答
13. LLM/Hermes 兜底
   - 输入：未命中前述确定性能力的问题
   - 处理：优先走 `HermesApiService`，仅 `hermes_base_url` 为空时回退 OpenAI 兼容文本客户端
   - 输出：自然语言回答；若为空则进入最终固定兜底

## 7. 实现方式
- 入口文件：
  - `dingtalk_mes_bot/stream_app.py`
  - `dingtalk_mes_bot/bot_app.py`
  - `dingtalk_mes_bot/reply_engine.py`
- 涉及模块：
  - `dingtalk_mes_bot/handlers/router.py`：当前正式路由顺序与能力优先级
  - `dingtalk_mes_bot/service_factory.py`：服务装配与 Hermes/视觉客户端选择
  - `dingtalk_mes_bot/config.py`：环境变量读取与默认值治理
  - `dingtalk_mes_bot/services/*`：FAQ、MES、权限、图片、文档、诊断、Hermes 等具体服务
- 配置项：
  - 基础运行：`DINGTALK_BOT_MODE`、`DINGTALK_BOT_CLIENT_ID`、`DINGTALK_BOT_CLIENT_SECRET`、`DINGTALK_BOT_ROBOT_CODE`
  - HTTP 回调：`DINGTALK_BOT_CALLBACK_TOKEN`、`DINGTALK_BOT_CALLBACK_AES_KEY`、`DINGTALK_BOT_CALLBACK_RECEIVE_ID`
  - Hermes：`DINGTALK_BOT_HERMES_BASE_URL`、`DINGTALK_BOT_HERMES_WORKSPACE`、`DINGTALK_BOT_HERMES_MODEL`
  - 视觉/OpenAI 兼容：`DINGTALK_BOT_LLM_BASE_URL`、`DINGTALK_BOT_LLM_API_KEY`、`DINGTALK_BOT_VISION_MODEL`
  - 数据依赖：`MES_BOT_API_BASE`、`DINGTALK_BOT_PROJECT_CONFIG_DB_PATH`、`DINGTALK_BOT_WEB_USERS_DB_PATH`、`DINGTALK_BOT_UNIFIED_DB_PATH`、`DINGTALK_BOT_USER_ALIASES_PATH`
  - 文档：`DINGTALK_BOT_DOC_*`
- 数据来源：
  - MES API
  - 项目配置数据库
  - Web 用户数据库
  - 统一数据库
  - 钉钉消息与图片下载接口
  - Hermes API
- 是否依赖第三方接口：是，依赖钉钉 API、Hermes API、OpenAI 兼容视觉接口。
- 兼容/回退策略：
  - 文本问答：Hermes 优先，Hermes 未配置时才退回旧 OpenAI 兼容文本服务
  - 视觉识别：继续走 OpenAI 兼容服务，不强制切换到 Hermes 多模态
  - 空回复：由固定兜底文案收口

## 8. 任务拆解
### 8.1 后端
- [ ] 以当前 `router.py` 行为为基准，补齐正式 README 中的能力说明，避免仓根文档仍停留在“首轮拆分结果”。
- [ ] 把 `service_factory.py` 中 `IssueDiagnosisService` 的硬编码 `h2_db_path='/volume2/MES/QRMES/record/product_records.db'` 收敛为配置项。
- [ ] 把 `config.py` 中仍默认指向旧目录的别名文件、文档状态文件路径继续治理到 split 仓可写目录。
- [ ] 为 spec 整理、能力说明、诊断等路由补更多边界测试，防止后续调整顺序误伤旧在线行为。

### 8.2 前端/交互
- [ ] 统一机器人在群内的引导语口径，让“你能做什么”“怎么提问更容易答对”与当前能力一致。
- [ ] 如果后续接 web 运维面板，保持只展示机器人能力和状态，不改 `app_web` 主业务逻辑。

### 8.3 测试与验证
- [ ] 覆盖 `MessageRouter` 主要优先级：非 MES、总结跟进、spec、权限、图片、诊断、FAQ、LLM fallback。
- [ ] 覆盖 `service_factory` 中 Hermes 优先、OpenAI fallback 的装配逻辑。
- [ ] 验证配置缺失时能给出明确兜底，不出现静默失败。
- [ ] 验证图片命中和权限命中后不会再多余调用文本 LLM。

### 8.4 部署与回滚
- [ ] 保持根目录 `start.sh / stop.sh / status.sh / deploy.sh / run.sh` 为正式入口。
- [ ] 继续兼容旧 stream 启动方式，避免为了接新能力去改动已经在线可用的钉钉接入链路。
- [ ] 配置切换失败时，允许快速回退到上一个可用 `.env` 与进程启动方式。

## 9. 验收标准
- [ ] `stream` 与 `http` 两种模式都能走统一回复主链路。
- [ ] spec 整理请求会优先进入结构化输出，不会误落到权限或普通 FAQ。
- [ ] FAQ、权限、图片、诊断、MES 查询命中后不会被普通 LLM 抢答。
- [ ] 文本问答默认使用 Hermes；未配置 Hermes 时才回退旧 OpenAI 兼容文本服务。
- [ ] 图片识别继续可用，不受文本模型切换影响。
- [ ] 配置缺失、依赖异常、未命中能力时，都有明确中文兜底说明。
- [ ] 不影响现有根目录部署入口和旧在线 stream 运行方式。

## 10. 待确认项
- `IssueDiagnosisService` 未来是否继续使用本地硬编码 H2/SQLite 文件，还是统一改为配置驱动。
- `DINGTALK_BOT_USER_ALIASES_PATH` 与 `DINGTALK_BOT_DOC_STATE_PATH` 是否需要全部迁到本仓 `data/` 或 `runtime/` 目录。
- spec 整理能力后续是否需要支持“直接落地到 markdown 文件/钉钉文档”，还是继续只在群内输出文本。
- 诊断能力是否要继续扩展到更多日志类型与自动巡检结果联动。
