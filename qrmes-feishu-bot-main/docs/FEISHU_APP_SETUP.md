# 飞书开放平台配置清单

## 1. 创建应用
在飞书开放平台创建“自建应用”，拿到：
- App ID
- App Secret

填入 `.env`：
- `FEISHU_BOT_APP_ID`
- `FEISHU_BOT_APP_SECRET`

## 2. 开启机器人能力
在应用功能里启用机器人能力。

## 3. 事件订阅
订阅地址：
- `http://<你的主机IP>:8898/feishu/event`

如果走反向代理/公网：
- `https://<你的域名>/feishu/event`

URL 验证会使用：
- `FEISHU_BOT_VERIFICATION_TOKEN`

## 4. 事件权限
至少订阅：
- `im.message.receive_v1`

## 5. 应用权限
至少开启：
- 接收消息
- 发送消息
- 读取图片/文件（如果要让机器人分析图片或日志文件）

## 6. 机器人入群
把机器人加入目标飞书群。

## 7. 本地服务验证
先确认 Hermes：
- `curl http://127.0.0.1:8787/health`

再确认飞书 bot：
- `curl http://127.0.0.1:8898/health`

## 8. 正式联调
在飞书群里 @机器人 测试：
- `@MES助手 web发布后打不开`
- `@MES助手 SN123456 产品记录库查不到`
- `@MES助手 上传错误日志帮我看下`
