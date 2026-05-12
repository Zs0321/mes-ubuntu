# qrmes-web-core runtime notes

推荐直接使用仓库根目录脚本。

临时部署到 8899：
- `MESAPP_PORT=8899 ./deploy.sh`

切到 8891 正式端口部署：
- `MESAPP_PORT=8891 ./deploy.sh`

日常启动：
- `./start.sh`

查看状态：
- `./status.sh`

停止服务：
- `./stop.sh`

说明：
- `deploy.sh` 会自动创建 `.venv`、安装依赖、安装 `qrmes-shared-core` 并启动服务。
- 首次用 `MESAPP_PORT=8899 ./deploy.sh` 或 `MESAPP_PORT=8891 ./deploy.sh` 后，端口会写入 `runtime.env`，后续直接 `./start.sh` 即可沿用。
- 如果需要从当前端口切换到另一个端口，重新显式执行一次对应端口的 `deploy.sh` 即可。
- 健康检查地址：
  - `http://127.0.0.1:$MESAPP_PORT/health`
  - `http://127.0.0.1:$MESAPP_PORT/api/h2/health`
