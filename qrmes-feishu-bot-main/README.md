# qrmes-feishu-bot

基于 `mes_ubuntu_split_result` 目录创建的飞书机器人仓库。

目标：
- 让用户在飞书群里 @ 机器人后，快速定位 APK、Web、后端服务、数据库、Finance、Motor QC 等问题的高概率原因。
- 复用 `qrmes-dingtalk-bot` 的组织方式，但优先做确定性排障，再用 LLM 做追问总结。
- 用 Spec Kit 风格文档固化需求、设计和任务拆分。

## 当前能力
- 支持飞书 URL 验证与事件回调
- 支持基于 `header.token` 的安全校验
- 支持群聊 @ 机器人、单聊、text/post/file/image 消息解析
- 支持 APK/Web/数据库/权限/H2/照片/Finance/Motor QC 排障
- 支持读取 split 仓库内预设健康地址、脚本、日志路径做自动探测
- 支持读取日志 tail 与 SQLite 表计数做更深诊断
- 支持可选 OpenAI Compatible LLM 做“追问建议”和兜底总结
- 提供本地部署脚本、状态脚本、systemd service 模板

## 目录
- `feishu_mes_bot/` 机器人源码
- `tests/` 单元测试
- `specs/001-feishu-mes-diagnostic-bot/` Spec Kit 风格需求/设计/任务
- `scripts/deploy_local.sh` 本地部署
- `scripts/status_local.sh` 本地状态检查
- `scripts/qrmes-feishu-bot.service` systemd 模板

## 快速启动
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. 复制 `.env.example` 为 `.env` 并填充飞书应用信息
4. `./run.sh`
5. 健康检查：`scripts/healthcheck.sh`

## 正式部署
本地部署：
- `scripts/deploy_local.sh`

查看状态：
- `scripts/status_local.sh`

systemd：
- 参考 `scripts/qrmes-feishu-bot.service`
- 按实际部署目录修改 `WorkingDirectory`、`EnvironmentFile`、`ExecStart`

## 飞书接入建议
- 事件订阅地址：`http://<host>:8898/feishu/event`
- 健康地址：`http://<host>:8898/health`
- URL 验证和事件回调都会校验 `header.token`
- 机器人需要消息接收与发送权限

## 典型提问
- `@MES助手 web发布后打不开`
- `@MES助手 APK更新失败`
- `@MES助手 登录403`
- `@MES助手 产品记录库查不到序列号`
- `@MES助手 金蝶状态异常`
- `@MES助手 相机桥接打不开`

## 开发验证
- `python3 -m unittest discover -s tests -v`
- `python3 -m py_compile $(find feishu_mes_bot tests -name '*.py')`


## Hermes 接入
当前推荐模式：
- 本地规则 / SQLite / 日志诊断：由飞书 bot 本地执行
- 追问建议 / 总结 / 兜底：走本机 Web3Hermes API

默认读取：
- `FEISHU_BOT_HERMES_BASE_URL`，默认 `http://127.0.0.1:8787`
- `FEISHU_BOT_HERMES_WORKSPACE`，当前建议设为 `/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result`

如果 Hermes API 可用，service_factory 会优先选 HermesApiService；否则再退回 OpenAI-compatible 配置。


## 飞书开放平台配置
- 详细步骤见：`docs/FEISHU_APP_SETUP.md`
- 一键验证脚本：`scripts/verify_integration.sh`
- 推荐直接复制：`.env.template` -> `.env`


## 长连接模式
- `.env` 里可设 `FEISHU_BOT_MODE=long_connection`
- 长连接模式不依赖公网回调地址
- 需要先安装：`pip install lark-oapi`
- 回调模式仍保留：`FEISHU_BOT_MODE=callback`
