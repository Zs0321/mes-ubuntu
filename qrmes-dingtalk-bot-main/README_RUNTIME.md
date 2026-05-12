# qrmes-dingtalk-bot runtime notes

快速启动：
1. 安装依赖：`python3.11 -m pip install -r requirements.txt`
2. 复制并填写 `.env`（可直接套用旧版钉钉机器人的 stream 参数）
3. 启动：`./start.sh`
4. 查看状态：`./status.sh`
5. 停止：`./stop.sh`
6. 重启部署：`./deploy.sh`

说明：
- 默认按 `DINGTALK_BOT_MODE=stream` 启动，模块为 `dingtalk_mes_bot.stream_app`
- 若改成 `DINGTALK_BOT_MODE=http`，则自动切到 `dingtalk_mes_bot.bot_app`
- 因此同一套增强逻辑同时支持 stream/http，两边都走同一个 `service_factory -> router`
- 旧机器人可直接复用 `DINGTALK_BOT_CLIENT_ID` / `DINGTALK_BOT_CLIENT_SECRET` / `DINGTALK_BOT_ROBOT_CODE`
- app_web 服务端不在这个仓库里，本次改动只作用于钉钉机器人进程

如与 `qrmes-shared-core` 同级放置，可先执行 `scripts/install_shared_core.sh` 安装共享层。

新增说明：
- 文本问答已支持优先走本机 Hermes API：`DINGTALK_BOT_HERMES_BASE_URL`
- 推荐 Hermes 工作区：`DINGTALK_BOT_HERMES_WORKSPACE=/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-dingtalk-bot`
- 当前增强了 Web 发布、APK 更新、登录/权限、产品记录库、Finance 等诊断问题
- 已支持附件/日志文件深诊断
- 图片识别仍保留现有视觉链路；文本总结/兜底切到 Hermes
