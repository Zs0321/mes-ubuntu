# qrmes-v2.0 环境变量迁移到 qrmes-dingtalk-bot

本文整理 `/volume2/qrmes-v2.0/.env` 里哪些变量可以直接搬到当前 split 仓：
- `/volume2/mes_ubuntu_split_result/qrmes-dingtalk-bot`

结论先说：
- 钉钉机器人本身的 stream/http 凭据、MES 接口、数据库路径、文档配置，大多数都可以直接复用。
- Hermes 相关变量是 split 仓新增的，不能从 `qrmes-v2.0/.env` 原样拿，需要按当前实际 Hermes 地址填写。
- `qrmes-v2.0/.env` 里那批 `QWEN_* / ANTHROPIC_* / KINGDEE_* / PYTHON_BIN` 并不是当前 `qrmes-dingtalk-bot` 的直接读取项，不能简单认为“都有效”。

## 1. 可以直接复用到当前 split 仓的变量

### 1.1 钉钉连接与机器人身份
这些变量当前 `dingtalk_mes_bot/config.py` 明确读取，可直接从旧仓复制：

- `DINGTALK_BOT_MODE`
- `DINGTALK_BOT_HOST`
- `DINGTALK_BOT_PORT`
- `DINGTALK_BOT_LOG_LEVEL`（旧仓没写也没关系，可补）
- `DINGTALK_BOT_APP_KEY`
- `DINGTALK_BOT_APP_SECRET`
- `DINGTALK_BOT_CLIENT_ID`
- `DINGTALK_BOT_CLIENT_SECRET`
- `DINGTALK_BOT_ROBOT_CODE`
- `DINGTALK_BOT_CALLBACK_TOKEN`
- `DINGTALK_BOT_CALLBACK_AES_KEY`
- `DINGTALK_BOT_CALLBACK_RECEIVE_ID`
- `DINGTALK_BOT_API_BASE_URL`

说明：
- 当前代码优先取 `DINGTALK_BOT_CLIENT_ID / DINGTALK_BOT_CLIENT_SECRET`。
- 如果只保留 `APP_KEY / APP_SECRET` 也能兜底，但建议沿用旧仓里已经在用的 `CLIENT_*`。

### 1.2 机器人依赖的 MES / 数据库 / 用户映射
这些也可以直接沿用旧值：

- `MES_BOT_API_BASE`
- `DINGTALK_BOT_PROJECT_CONFIG_DB_PATH`
- `DINGTALK_BOT_WEB_USERS_DB_PATH`
- `DINGTALK_BOT_UNIFIED_DB_PATH`
- `DINGTALK_BOT_USER_ALIASES_PATH`

注意：
- `DINGTALK_BOT_USER_ALIASES_PATH` 当前默认还指向 `/volume2/qrmes-v2.0/dingtalk_mes_bot/mes_user_aliases.json`。
- 如果后面把该文件也迁到 split 仓，再改这个路径更干净；当前直接沿用旧路径是可行的。

### 1.3 文档机器人相关
如果你还要继续保留钉钉文档创建/日报能力，下面这些可以直接搬：

- `DINGTALK_BOT_DOC_WORKSPACE_ID`
- `DINGTALK_BOT_DOC_PARENT_NODE_ID`
- `DINGTALK_BOT_DOC_OPERATOR_ID`
- `DINGTALK_BOT_DOC_STATE_PATH`

建议：
- `DINGTALK_BOT_DOC_STATE_PATH` 最好改到 split 仓目录下，例如：
  - `/volume2/mes_ubuntu_split_result/qrmes-dingtalk-bot/dingtalk_mes_bot/cache/daily_docs.json`
- 旧值继续用也能跑，但会继续把运行状态写回旧目录。

### 1.4 原视觉/LLM 兼容链路配置
当前代码仍读取这些：

- `DINGTALK_BOT_LLM_BASE_URL`
- `DINGTALK_BOT_LLM_API_KEY`
- `DINGTALK_BOT_LLM_TIMEOUT`
- `DINGTALK_BOT_TEXT_MODEL`
- `DINGTALK_BOT_LLM_MODEL`（作为 `TEXT_MODEL` 的后备）
- `DINGTALK_BOT_VISION_MODEL`

说明：
- 现在文本主链路虽然已经接 Hermes，但视觉链路仍然走 `OpenAiCompatibleService`。
- 所以 `DINGTALK_BOT_VISION_MODEL` 和 `DINGTALK_BOT_LLM_BASE_URL` 仍然是有用的。

## 2. 当前 split 仓新增、不能从旧仓原样照搬的变量

这些是 split 仓新增能力，需要按当前部署环境单独填写：

- `DINGTALK_BOT_HERMES_BASE_URL`
- `DINGTALK_BOT_HERMES_WORKSPACE`

当前推荐：

```env
DINGTALK_BOT_HERMES_BASE_URL=http://172.16.20.201:8787
DINGTALK_BOT_HERMES_WORKSPACE=/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-dingtalk-bot
```

如果以后 Hermes 地址变化，只需要更新这里，不用动旧 `qrmes-v2.0` 的配置。

## 3. 旧仓里有，但当前 qrmes-dingtalk-bot 不直接读取的变量

下面这些即使在 `qrmes-v2.0/.env` 存在，也不是当前 `dingtalk_mes_bot/config.py` 的直接配置项：

### 3.1 通用上游模型变量
- `MOTOR_QC_VISION_PROVIDER`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_MODEL`
- `QWEN_MODEL_CANDIDATES`
- `DASHSCOPE_API_KEY`
- `QWEN_BASE_URL`
- `QWEN_MODEL`
- `SECONDARY_QWEN_API_KEY`
- `SECONDARY_QWEN_BASE_URL`
- `SECONDARY_QWEN_MODEL`

这些更像旧系统其它模块或外部模型封装在用，不是当前 split 仓 dingtalk bot 通过 `config.py` 直接消费的键。

### 3.2 旧目录专属或运行脚本变量
- `DINGTALK_BOT_MENTION_ALIASES`
- `MES_BOT_DATA_DIR`
- `MES_BOT_PROJECT_CONFIG_DIR`
- `MES_BOT_H2_DB_PATH`
- `PYTHON_BIN`

说明：
- 这些旧键当前 split 仓代码没有直接读取。
- `PYTHON_BIN` 是旧脚本层概念，不是当前 bot 配置对象字段。

### 3.3 Finance / Kingdee 变量
- `KINGDEE_BASE_URL`
- `KINGDEE_DB_ID`
- `KINGDEE_USERNAME`
- `KINGDEE_APP_ID`
- `KINGDEE_APP_SECRET`
- `KINGDEE_LCID`
- `KINGDEE_TIMEOUT_SECONDS`

这些当前主要是诊断提示里会提到 `KINGDEE_*`，但不是 `qrmes-dingtalk-bot` 自己通过 `config.py` 装配的运行主配置。

## 4. 建议迁移方式

最稳建议是：

1. 先从 `qrmes-v2.0/.env` 复制以下变量到当前 split 仓 `.env`
   - 钉钉凭据
   - MES_BOT_API_BASE
   - 数据库路径
   - 文档配置
   - 视觉/LLM 兼容链路配置

2. 再单独补 split 仓新增的 Hermes 变量

3. 把旧目录写状态的路径改到 split 仓下
   - 优先改：`DINGTALK_BOT_DOC_STATE_PATH`
   - 视情况再改：`DINGTALK_BOT_USER_ALIASES_PATH`

## 5. 当前已整理到仓库中的文件

已更新：
- `qrmes-dingtalk-bot/.env.example`

它现在已经按“可从 `qrmes-v2.0` 直接迁移”的思路整理好了，直接可作为当前 split 仓模板使用。
