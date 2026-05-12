# qrmes-dingtalk-bot 产品与技术 Spec

## 1. 文档目标

这份文档用于明确 `qrmes-dingtalk-bot` 的产品边界、消息处理规则、技术结构、配置约束、验收口径和后续治理方向，作为当前 split 仓独立运行的正式说明。

适用对象：
- 维护钉钉机器人运行与部署的开发/运维
- 在钉钉群中使用机器人做 MES 查询、诊断、需求整理的业务人员
- 后续继续增强机器人能力的开发人员

## 2. 背景

`qrmes-dingtalk-bot` 来自 `mes_ubuntu` 单仓拆分，目标不是推翻旧链路重做一套新机器人，而是在尽量保留旧线上接入方式和使用习惯的前提下，把钉钉机器人收敛为一个可独立部署、可持续维护、可继续增强的 split 仓服务。

当前仓库已经具备这些基础：
- 支持 `stream` 与 `http callback` 两种接入模式
- 文本问答优先切到 Hermes
- 图片识别继续沿用 OpenAI 兼容视觉链路
- 根目录保留 `start.sh / stop.sh / status.sh / deploy.sh / run.sh` 入口
- 已有 router、service_factory、config、runtime、reply_engine 等清晰的核心装配层
- 已覆盖 router、Hermes、message parser、permission、image query、diagnosis 等测试

同时也存在现实约束：
- 部分默认数据路径仍指向旧目录或共享目录
- 个别运行时参数还没有完全纳入配置治理
- 机器人对 Hermes 调用失败的可观测性还偏弱
- 现阶段仍以兼容旧链路优先，不做激进架构替换

## 3. 目标

### 3.1 总体目标

建设一个面向 MES 场景的独立钉钉机器人服务：
- 能稳定收消息、识别意图、命中确定性能力、必要时调用 Hermes 生成回答
- 能在群聊里承担 FAQ、MES 查询、权限查询、图片辅助识别、文档动作、问题诊断、需求/spec 整理等职责
- 能在 split 仓内独立维护和上线，不依赖单仓思维继续堆逻辑

### 3.2 具体目标

1. 支持 `stream` 和 `http` 两种运行模式，且共用统一回复主链路。
2. 文本开放问答默认走 Hermes，不再依赖旧文本模型作为主方案。
3. FAQ、MES 查询、权限判断、图片查询、诊断、文档动作优先于 LLM。
4. 需求/spec 整理请求可直接输出固定结构的中文初稿。
5. 保持 split 仓根目录级运维入口，降低部署和切换成本。
6. 运行配置尽量集中在 `.env` 和 `config.py`，减少代码中的环境硬编码。
7. 在不改动 `app_web` 的前提下，只增强机器人本身能力。

## 4. 非目标

当前阶段不包含以下事项：
1. 不重构 `app_web` 服务端。
2. 不重写为新的事件总线或复杂 agent 框架。
3. 不把所有旧目录依赖一次性全部迁出；先可运行，再逐步治理。
4. 不把图片识别统一改成 Hermes 多模态。
5. 不在本仓承接 MES 全量业务逻辑；本仓聚焦机器人问答与辅助处理。

## 5. 用户与典型场景

### 5.1 用户角色
- MES 一线使用人员：产线、测试、售后、跟单等
- 维护系统的开发/运维人员
- 需要在群里快速定位问题、查看能力说明、整理需求的人

### 5.2 典型场景
1. 用户在群里 @机器人提问 MES 常见问题。
2. 用户发标签、二维码或工序图片，请机器人识别后辅助查询。
3. 用户发序列号或权限问题，请机器人判断当前人员是否具备工序权限。
4. 用户要求把统计结果写入钉钉文档。
5. 用户发日志、附件或故障描述，请机器人输出排查建议。
6. 用户给一段自然语言需求，请机器人整理成结构化 spec 初稿。
7. 用户询问“这个机器人能做什么”“Hermes 是什么”“MES 有哪些模块”等介绍性问题。

## 6. 产品范围

### 6.1 消息接入

必须支持：
- `dingtalk_mes_bot.stream_app`：stream 模式
- `dingtalk_mes_bot.bot_app`：http callback 模式

处理要求：
- 统一解析为 `IncomingMessage`
- 统一走 `build_reply(runtime, message)`
- 仅对符合机器人回复条件的消息进行响应
- 空回复不发送，避免噪声

### 6.2 路由原则

核心原则：确定性能力优先，LLM 靠后。

当前应以 `dingtalk_mes_bot/handlers/router.py` 为准，路由优先级如下：
1. 空消息兜底
2. 非 MES 边界问题拦截
3. 总结/继续总结类跟进
4. spec/需求整理类请求
5. 报价能力说明类问题
6. MES 能力概览类说明
7. 权限查询
8. 图片查询
9. 诊断服务
10. 轻闲聊
11. FAQ
12. 文档动作
13. MES 实时/规则型回答
14. LLM/Hermes 兜底
15. 最终固定兜底文案

产品要求：
- FAQ 命中后不能再走 LLM
- 图片命中后不能再走文本 LLM
- 权限命中后必须基于真实数据判断，不能模型猜
- spec 整理允许直接走 LLM，但要约束结构
- 诊断服务优先于普通 LLM 问答

### 6.3 FAQ 与固定说明

机器人需要直接回答高频固定问题，例如：
- 项目同步
- 待复核原因
- 401/登录/权限常见问题
- 机器人能力范围说明
- Hermes / MES 模块介绍

要求：
- 输出用中文
- 适合钉钉群聊语境
- 不要 AI 腔、不要空泛安慰
- 能固定回答的场景不调用模型

### 6.4 Hermes 文本问答

文本问答默认走 Hermes，对应配置：
- `DINGTALK_BOT_HERMES_BASE_URL`
- `DINGTALK_BOT_HERMES_WORKSPACE`
- `DINGTALK_BOT_HERMES_MODEL`

当前代码行为：
- `service_factory.py` 中若 `hermes_base_url` 非空，则文本客户端使用 `HermesApiService`
- `HermesApiService` 先调 `/api/session/new`，再调 `/api/chat`
- 发送给 Hermes 的内容是 merge 后的纯文本 prompt
- 若 Hermes 返回失败，则上层继续走兜底逻辑

产品要求：
- Hermes 是文本问答主后端
- 仅当 `hermes_base_url` 为空时，才回退到旧 OpenAI 兼容文本服务
- 不能因为旧文本模型配置失效导致机器人长期只剩静态 fallback

### 6.5 图片识别与图片查询

图片链路继续保留：
- `DingTalkImageService`：下载图片
- `VisionRecognitionService`：视觉识别
- `ImageQueryService`：MES 场景封装

能力范围：
- 标签、二维码、序列号识别
- 从图片中提取项目/条码信息
- 联动 MES 查询与权限判断

要求：
- 图片消息优先于普通文本问答处理
- 图片命中后不再走文本 LLM
- 图片能力继续沿用现有视觉链路，不强制切 Hermes 多模态

### 6.6 权限查询

应支持：
- 从文本中抽取序列号做权限判断
- 从图片中识别序列号后做权限判断
- 结合发送人 `staff_id / nick` 返回权限结果

要求：
- 无序列号、无图片时给出明确引导
- 结果基于项目配置、用户映射、MES 数据，不得纯猜测

### 6.7 文档动作

应支持把统计结果写入钉钉文档，依赖配置：
- `DINGTALK_BOT_DOC_WORKSPACE_ID`
- `DINGTALK_BOT_DOC_PARENT_NODE_ID`
- `DINGTALK_BOT_DOC_OPERATOR_ID`
- `DINGTALK_BOT_DOC_STATE_PATH`

要求：
- 文档动作在普通 LLM 前处理
- 文档状态文件优先落在 split 仓可写目录
- 输出中要包含文档创建/更新结果

### 6.8 诊断能力

诊断服务用于处理实际排障请求，包括但不限于：
- Web 发布异常
- APK 发布/更新问题
- 登录与权限问题
- 产品记录库问题
- Finance 相关问题
- 日志与附件诊断

要求：
- 优先输出“排查建议 + 证据方向”
- 允许结合文件/日志/消息内容生成针对性建议
- 不要只给安慰式回答

### 6.9 spec / 需求整理能力

当用户输入包含 `spec / 需求 / 实现方式 / 任务 / 拆解 / 方案 / 排期 / 开发需求` 等关键词时，机器人应把原始描述整理成结构化 spec。

当前 router 中的固定输出结构要求为：
1. 需求背景
2. 目标
3. 业务流程
4. 状态流转
5. 通知规则
6. 功能点清单
7. 实现方式
8. 任务拆解
9. 验收标准
10. 待确认项

要求：
- 信息不足时可以输出初稿
- 必须显式列出待确认项
- 不允许编造系统现状
- 语气自然直接，不要模板腔

## 7. 技术架构

### 7.1 当前正式代码边界

以现有仓库代码为准，核心模块如下：
- `dingtalk_mes_bot/config.py`：配置装载
- `dingtalk_mes_bot/runtime.py`：运行时封装
- `dingtalk_mes_bot/reply_engine.py`：统一回复入口
- `dingtalk_mes_bot/service_factory.py`：服务装配
- `dingtalk_mes_bot/handlers/router.py`：消息路由
- `dingtalk_mes_bot/message_parser.py`：消息解析
- `dingtalk_mes_bot/stream_app.py`：stream 入口
- `dingtalk_mes_bot/bot_app.py`：http callback 入口
- `dingtalk_mes_bot/services/*`：FAQ、查询、权限、诊断、图片、文档、Hermes 等能力

### 7.2 核心链路

1. 钉钉消息进入 `stream_app` 或 `bot_app`
2. payload 被解析为 `IncomingMessage`
3. `load_config()` 读取环境变量
4. `create_runtime()` 装载 router
5. `build_reply()` 调用 `router.route(message)`
6. router 按优先级逐个命中服务
7. 命中服务后返回文本结果
8. 最终通过钉钉回调或 session webhook 发回群聊

### 7.3 服务装配规则

以 `service_factory.py` 为当前实现基准：
- 文本模型：Hermes 优先，OpenAI 兼容服务为后备
- 视觉模型：仍走 OpenAI 兼容服务
- MES 查询：`MesQueryService + MesAnswerService`
- 图片查询：`ImageQueryService`
- 权限查询：`PermissionQueryService`
- 文档动作：`DocActionService + DingTalkDocService`
- 诊断服务：`IssueDiagnosisService`

### 7.4 设计原则

1. 规则与查询优先，LLM 后置。
2. 能命中固定能力时，不走生成式回答。
3. 新增配置先入 `config.py` 和 `.env.example`。
4. 与旧链路兼容，但不继续扩散旧路径硬编码。
5. 根目录脚本是正式运维入口，不把上线入口埋到深层目录。

## 8. 配置规范

### 8.1 最小运行配置

最小必需项：
- `DINGTALK_BOT_MODE`
- `DINGTALK_BOT_CLIENT_ID`
- `DINGTALK_BOT_CLIENT_SECRET`
- `DINGTALK_BOT_ROBOT_CODE`

HTTP callback 模式附加项：
- `DINGTALK_BOT_CALLBACK_TOKEN`
- `DINGTALK_BOT_CALLBACK_AES_KEY`
- `DINGTALK_BOT_CALLBACK_RECEIVE_ID`

### 8.2 关键增强配置

当前代码中已使用或应重点治理的配置：
- `MES_BOT_API_BASE`
- `DINGTALK_BOT_PROJECT_CONFIG_DB_PATH`
- `DINGTALK_BOT_WEB_USERS_DB_PATH`
- `DINGTALK_BOT_USER_ALIASES_PATH`
- `DINGTALK_BOT_UNIFIED_DB_PATH`
- `DINGTALK_BOT_DOC_WORKSPACE_ID`
- `DINGTALK_BOT_DOC_PARENT_NODE_ID`
- `DINGTALK_BOT_DOC_OPERATOR_ID`
- `DINGTALK_BOT_DOC_STATE_PATH`
- `DINGTALK_BOT_LLM_BASE_URL`
- `DINGTALK_BOT_LLM_API_KEY`
- `DINGTALK_BOT_TEXT_MODEL`
- `DINGTALK_BOT_VISION_MODEL`
- `DINGTALK_BOT_HERMES_BASE_URL`
- `DINGTALK_BOT_HERMES_WORKSPACE`
- `DINGTALK_BOT_HERMES_MODEL`

### 8.3 配置治理要求

1. 新增运行配置必须优先进入 `config.py`。
2. `.env.example` 需要反映真实可用配置项。
3. 不再新增旧单仓专属硬编码路径。
4. 运行态文件默认写到本仓可写目录。
5. 共享目录依赖允许保留，但必须显式可配置。

## 9. 兼容性要求

### 9.1 与旧钉钉接入兼容
- 继续兼容 `CLIENT_ID / CLIENT_SECRET / ROBOT_CODE`
- 允许 `APP_KEY / APP_SECRET` 作为兜底读取来源
- 保持 stream 模式优先，不强行替换成熟在线调用方式

### 9.2 与 split 仓约束兼容
- 保留根目录级启动入口
- 不影响 `app_web`
- 本仓只负责机器人进程
- 已有运行参数和共享库依赖允许分阶段收敛

## 10. 当前已识别问题

基于当前代码，已明确的问题包括：
1. `config.py` 仍存在默认路径直接指向旧目录或共享目录。
2. `service_factory.py` 中 `IssueDiagnosisService` 的 `h2_db_path` 仍为硬编码，尚未配置化。
3. Hermes 调用失败目前只表现为 `None`，缺少更细粒度日志与错误分类。
4. `HermesApiService` 每次对话新建 session，适合无状态问答，但不利于多轮承接。
5. 文档体系仍偏分散，已有 `README_RUNTIME.md`、`SPLIT_README.md` 和 runtime spec，但缺一份完整产品/技术主说明。

## 11. 验收标准

### 11.1 运行验收

1. `stream` 模式可启动并回复群里 @bot 消息。
2. `http` 模式 `/health` 正常，`/callback` 可处理回调。
3. 根目录 `start.sh / stop.sh / status.sh / deploy.sh` 可正常作为统一入口。

### 11.2 功能验收

1. FAQ 问题命中时不触发 LLM。
2. 图片消息可走图片链路并返回结果。
3. 权限问题可按文本序列号或图片返回权限判断。
4. 文本开放问答默认优先走 Hermes。
5. spec 整理类请求可输出固定结构中文 spec。
6. 诊断类问题在命中时优先于普通 LLM 返回。

### 11.3 测试验收

至少应覆盖并跑通以下测试：
- `dingtalk_mes_bot/tests/test_router.py`
- `dingtalk_mes_bot/tests/test_hermes_api_service.py`
- `dingtalk_mes_bot/tests/test_message_parser.py`
- `dingtalk_mes_bot/tests/test_permission_query_service.py`
- `dingtalk_mes_bot/tests/test_image_query_service.py`
- `dingtalk_mes_bot/tests/test_issue_diagnosis_service.py`
- `tests/test_service_factory.py`

### 11.4 文档验收

至少应具备：
- 运行方式说明
- 配置说明
- 仓库能力边界说明
- 消息路由顺序说明
- Hermes 与视觉链路职责划分说明

## 12. 后续迭代建议

### P1
1. 把 `IssueDiagnosisService` 的硬编码路径纳入配置治理。
2. 给 Hermes 调用增加错误日志、失败分类、关键字段观测。
3. 补一份更完整的 README 首页，把 README 与本 spec 形成“一页看懂 + 一页细节”。
4. 明确 diagnosis 的输入样例、命中规则和输出模板。

### P2
1. 评估是否支持多轮 session 复用。
2. 评估是否把 FAQ / 路由规则抽成可配置策略。
3. 逐步收敛旧目录默认路径。
4. 评估 spec 整理能力是否需要区分“产品 spec”和“开发 implementation plan”两种输出模式。

## 13. 待确认项

1. 线上正式运行是否长期以 `stream` 为主，`http` 是否只作为兼容保留。
2. 诊断服务当前真实业务范围是否要继续标准化到明确枚举。
3. 文档动作后续是否只做统计结果写入，还是扩展到巡检报告、需求整理等。
4. spec 整理能力是否要进一步支持“按仓库代码上下文输出实施方案”。
5. Hermes 失败时，是否需要在群里给出更明确的降级提示而不是仅默默 fallback。
