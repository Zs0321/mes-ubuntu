# qrmes-dingtalk-bot 运行与能力 Spec（初稿）

## 1. 背景

`qrmes-dingtalk-bot` 是从 `mes_ubuntu` 单仓拆分出来的钉钉机器人独立服务仓，当前目标不是重做一套新机器人，而是在尽量保持旧链路可运行的前提下，把钉钉消息接入、MES 查询、图片识别、权限判断、文档动作、问题诊断与 Hermes 文本问答能力沉淀到独立仓内，形成可单独部署、可维护、可继续增强的机器人服务。

从仓库现状看：
- 已具备 `stream` 与 `http` 两种接入模式。
- 文本问答主链路优先走 Hermes，视觉识别仍走 OpenAI 兼容接口。
- 根目录保留 `start.sh / stop.sh / status.sh / deploy.sh / run.sh` 启动入口。
- 仍存在部分默认路径指向旧目录或 MES 共享目录，说明当前仓虽然可运行，但还处在“独立仓运行边界持续收敛”的阶段。

## 2. 目标

### 2.1 总体目标
构建一个面向 MES 场景的独立钉钉机器人服务，能够稳定接收群消息、识别用户意图、优先命中确定性能力，再按需调用 Hermes 生成自然语言回复，并保持与旧线上链路兼容。

### 2.2 具体目标
1. 支持钉钉 `stream` 与 `http callback` 两种运行模式。
2. 维持消息处理主链路统一：`config -> runtime -> router -> service_factory -> services`。
3. 对常见 MES 问题优先走 FAQ / 查询 / 规则引擎，减少模型幻觉。
4. 文本类开放问答优先走 Hermes，避免继续依赖旧 `qwen3.5-35b-a3b` 文本兜底。
5. 图片相关问题继续保留既有图片下载与视觉识别能力。
6. 支持序列号权限判断、项目前缀识别、文档写入、日志/附件诊断等增强能力。
7. 保持 split 仓根目录级部署入口，降低上线切换成本。
8. 让运行配置尽量集中在 `.env`，避免业务逻辑中散落硬编码路径。

## 3. 非目标

当前阶段不包含以下目标：
1. 不改造 `app_web` 服务端逻辑。
2. 不重写钉钉机器人为全新架构或事件总线体系。
3. 不将所有旧目录依赖一次性彻底剥离；本阶段以“先独立可运行，再逐步去旧依赖”为原则。
4. 不替换图片识别现有视觉链路为 Hermes 多模态；视觉链路继续沿用 OpenAI 兼容接口。
5. 不在本仓内承接 MES 全量业务服务，只提供机器人问答与辅助诊断能力。

## 4. 目标用户与场景

### 4.1 用户角色
- 产线、测试、跟单、售后等 MES 一线使用人员
- 维护 MES 机器人与部署环境的开发/运维人员
- 需要在钉钉群里快速查看状态、定位问题、整理需求的人

### 4.2 典型场景
1. 用户在钉钉群中 @机器人提问 MES 常见问题。
2. 用户发送标签/二维码/工序图片，请机器人识别并返回结果。
3. 用户询问某序列号对应权限、工序权限或人员操作权限。
4. 用户要求把统计结果写入钉钉文档。
5. 用户发日志、附件或故障描述，请机器人输出排查建议。
6. 用户给一段自然语言需求，让机器人整理为 spec 初稿。

## 5. 功能范围

### 5.1 消息接入
必须支持：
- `stream` 模式：入口 `dingtalk_mes_bot.stream_app`
- `http` 模式：入口 `dingtalk_mes_bot.bot_app`

要求：
- 两种模式最终都走同一套 `build_reply(runtime, message)` 逻辑。
- 钉钉消息解析后统一转成 `IncomingMessage`。
- 仅对 `@bot` 的消息进行回复，避免误触发。

### 5.2 路由优先级
机器人必须按照“确定性优先、模型兜底靠后”的顺序处理，当前路由优先级定义为：
1. 空消息兜底
2. 非 MES 边界问题拦截（如天气）
3. 总结/继续总结类跟进
4. spec/需求整理类请求
5. MES 能力概览类说明
6. 权限查询
7. 图片查询
8. 诊断服务
9. 轻闲聊
10. FAQ
11. 文档动作
12. MES 实时/规则型回答
13. LLM/Hermes 兜底
14. 最终固定兜底文案

要求：
- FAQ、MES 查询、权限判断、图片识别命中时，不应再无意义调用 LLM。
- spec 整理类请求可以直接走 LLM，但提示词必须约束输出结构。

### 5.3 FAQ 与确定性回答
系统应内置常见 MES 问题答复能力，例如：
- 项目同步
- 待复核原因
- 401/登录/权限常见问题
- 系统能力说明

要求：
- FAQ 命中后直接返回中文答复。
- FAQ 文案应适合钉钉群聊语境，避免过长和 AI 腔。

### 5.4 Hermes 文本问答
文本问答主链路优先走 Hermes，配置来源：
- `DINGTALK_BOT_HERMES_BASE_URL`
- `DINGTALK_BOT_HERMES_WORKSPACE`
- `DINGTALK_BOT_HERMES_MODEL`

当前实现约束：
- `HermesApiService` 会先调用 `/api/session/new`，再调用 `/api/chat`。
- 发送给 Hermes 的内容为多条 messages 合并后的纯文本 prompt。
- Hermes 不可用时返回 `None`，由上层继续走兜底逻辑。

要求：
- Hermes 是文本问答默认后端。
- 若 `hermes_base_url` 为空，系统才回退到旧 OpenAI 兼容文本链路。
- 不允许因为旧文本模型配置问题导致机器人频繁返回 `None` 后只剩静态答复。

### 5.5 图片识别
图片链路继续使用：
- `DingTalkImageService` 下载图片
- `VisionRecognitionService` 做视觉识别
- `ImageQueryService` 做 MES 场景封装

能力范围：
- 标签/二维码识别
- 图片内容辅助查询
- 与项目、序列号、MES 查询联动

要求：
- 图片消息优先于普通文本问答处理。
- 图片消息命中时不应无必要调用文本 LLM。

### 5.6 权限查询
应支持：
- 从文本中提取序列号并查询权限
- 从图片中识别序列号并查询权限
- 结合发送人 staff_id / nick 返回权限判断结果

要求：
- 若识别到权限问题但没有序列号或图片，应返回明确引导语。
- 权限结果必须基于 MES 数据和用户映射，不得纯模型猜测。

### 5.7 文档动作
应支持把统计/结果写入钉钉文档。

当前依赖配置：
- `DINGTALK_BOT_DOC_WORKSPACE_ID`
- `DINGTALK_BOT_DOC_PARENT_NODE_ID`
- `DINGTALK_BOT_DOC_OPERATOR_ID`
- `DINGTALK_BOT_DOC_STATE_PATH`

要求：
- 文档动作优先于 LLM。
- 文档状态建议写入 split 仓路径，不继续污染旧仓运行态目录。

### 5.8 诊断能力
应支持问题诊断服务，包括但不限于：
- Web 发布异常
- APK 更新/发布问题
- 登录/权限类问题
- 产品记录库相关问题
- Finance 相关问题
- 日志/附件深诊断

当前要求：
- 路由层允许 `diagnosis_service` 在 LLM 之前处理消息。
- 诊断结果应偏“排查建议 + 证据方向”，而不是空泛安慰语。

### 5.9 spec 整理能力
当用户输入包含“spec / 需求 / 实现方式 / 拆解 / 方案 / 排期”等关键词时，机器人应将原始描述整理为结构化 spec。

固定输出结构：
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
- 信息不足时允许输出初稿，但必须标出待确认项。
- 不允许编造不存在的系统现状。

## 6. 技术架构

### 6.1 模块结构
建议以当前实际代码结构作为正式边界：
- `dingtalk_mes_bot/config.py`：配置装载
- `dingtalk_mes_bot/service_factory.py`：服务装配
- `dingtalk_mes_bot/handlers/router.py`：消息路由与优先级控制
- `dingtalk_mes_bot/stream_app.py`：钉钉 stream 入口
- `dingtalk_mes_bot/bot_app.py`：HTTP callback 入口
- `dingtalk_mes_bot/message_parser.py`：消息结构解析
- `dingtalk_mes_bot/reply_engine.py`：回复编排
- `dingtalk_mes_bot/services/*`：具体能力服务

### 6.2 核心链路
1. 钉钉消息进入 `stream_app` 或 `bot_app`
2. 原始 payload 转换为标准消息对象
3. 运行时装载配置与 router
4. router 按优先级依次判断能力
5. 命中某服务后返回文本结果
6. 通过 session webhook 回发到钉钉

### 6.3 设计原则
1. 规则与查询优先，LLM 兜底。
2. 同一类能力只保留一个主入口，避免多处散落判断。
3. 配置驱动，少写环境强绑定。
4. 与旧线上参数兼容，但新能力统一挂到 split 仓配置中。
5. 根目录启动脚本作为对外稳定入口，不把部署入口埋到深层 scripts 内。

## 7. 配置规范

### 7.1 必需配置
最小运行需要：
- `DINGTALK_BOT_MODE`
- `DINGTALK_BOT_CLIENT_ID`
- `DINGTALK_BOT_CLIENT_SECRET`
- `DINGTALK_BOT_ROBOT_CODE`

HTTP callback 模式附加需要：
- `DINGTALK_BOT_CALLBACK_TOKEN`
- `DINGTALK_BOT_CALLBACK_AES_KEY`
- `DINGTALK_BOT_CALLBACK_RECEIVE_ID`

### 7.2 关键增强配置
- `MES_BOT_API_BASE`
- `DINGTALK_BOT_PROJECT_CONFIG_DB_PATH`
- `DINGTALK_BOT_WEB_USERS_DB_PATH`
- `DINGTALK_BOT_UNIFIED_DB_PATH`
- `DINGTALK_BOT_USER_ALIASES_PATH`
- `DINGTALK_BOT_DOC_*`
- `DINGTALK_BOT_LLM_BASE_URL`
- `DINGTALK_BOT_LLM_API_KEY`
- `DINGTALK_BOT_VISION_MODEL`
- `DINGTALK_BOT_HERMES_BASE_URL`
- `DINGTALK_BOT_HERMES_WORKSPACE`
- `DINGTALK_BOT_HERMES_MODEL`

### 7.3 配置治理要求
1. 新增运行配置优先写入 `config.py` 和 `.env.example`。
2. 默认值允许保底，但必须避免把旧仓专属路径当成长期正式配置。
3. 代码中不应继续新增硬编码业务路径。
4. 与 split 仓相关的状态文件，默认应落在本仓可写目录。

## 8. 兼容性要求

### 8.1 与旧仓兼容
- 优先兼容旧钉钉 stream 参数：`CLIENT_ID / CLIENT_SECRET / ROBOT_CODE`
- 保留 `APP_KEY / APP_SECRET` 作为兜底读取来源
- 允许继续引用旧数据库或共享目录，但应逐步显式化

### 8.2 与 split 仓约束兼容
- 根目录保留 `start.sh / stop.sh / status.sh / deploy.sh`
- 不要求改动 `app_web`
- 文本链路切 Hermes 时尽量沿用旧 stream 模式，不重构原消息接入方式

## 9. 已识别的当前问题

基于当前仓代码，以下问题应视为已知待治理项：
1. 仓根 `SPLIT_README.md` 仍表述为“首轮拆分结果”，说明正式文档不足。
2. `config.py` 的部分默认路径仍指向旧目录，例如用户别名、文档状态文件。
3. `service_factory.py` 中 `IssueDiagnosisService` 的 `h2_db_path` 仍为硬编码路径，未纳入配置治理。
4. README 体系偏零散，缺少一份完整的产品/技术 spec 说明仓边界。
5. Hermes 服务调用失败时只返回 `None`，缺少更细粒度错误可观测性。
6. 当前 `HermesApiService` 每次对话重新创建 session，适合无状态问答，但不利于多轮连续上下文复用。

## 10. 验收标准

### 10.1 运行验收
1. `stream` 模式可正常启动并在群里回复 @bot 消息。
2. `http` 模式 `/health` 返回正常，`/callback` 可处理明文与加密回调。
3. 根目录 `start.sh / stop.sh / status.sh / deploy.sh` 可作为统一入口使用。

### 10.2 功能验收
1. FAQ 类问题命中时不触发 LLM 兜底。
2. 图片消息可走图片识别链路并返回结果。
3. 权限问题可按序列号或图片返回权限判断。
4. 文本开放问答优先走 Hermes。
5. spec 整理类输入可输出固定结构的中文 spec。
6. 诊断类请求在命中时优先于 LLM 返回排查建议。

### 10.3 测试验收
应至少保留并跑通以下测试类别：
- `dingtalk_mes_bot/tests/test_router.py`
- `dingtalk_mes_bot/tests/test_hermes_api_service.py`
- `tests/test_service_factory.py`
- 图片、权限、诊断、消息解析相关单元测试

### 10.4 文档验收
需要至少具备：
- 运行说明
- 环境变量说明
- 当前仓能力边界说明
- 消息路由顺序说明
- Hermes 与视觉链路职责说明

## 11. 后续迭代建议

### P1
1. 把硬编码数据路径继续收敛到配置层。
2. 补一份更完整的 README，和本 spec 形成“一页看懂 + 一页细节”的文档组合。
3. 为 Hermes 调用增加日志与错误观测字段。
4. 明确 diagnosis 能力清单与输入样例。

### P2
1. 评估是否要做多轮会话复用与上下文缓存。
2. 评估是否把部分 FAQ/规则路由抽成可配置策略。
3. 评估是否将旧目录依赖进一步迁入 split 仓。

## 12. 待确认项

1. 线上正式运行目前以 `stream` 还是 `http` 为主，`http` 是否只保留兼容能力。
2. 诊断服务当前的真实能力边界、数据来源和输出格式是否需要再标准化。
3. 图片识别是否后续仍坚持旧视觉链路，还是逐步切到统一智能后端。
4. 文档动作的正式业务范围，是只做日报/统计，还是扩展到需求整理、巡检报告等。
5. 是否要把本 spec 继续展开成 implementation plan，拆到具体文件、测试和改造步骤。
