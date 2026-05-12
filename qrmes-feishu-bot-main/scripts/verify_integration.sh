#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

echo "[1/5] 检查 Hermes API ..."
curl -fsS "${FEISHU_BOT_HERMES_BASE_URL:-http://127.0.0.1:8787}/health"
echo

echo "[2/5] 检查飞书 bot 健康接口 ..."
curl -fsS "http://127.0.0.1:${FEISHU_BOT_PORT:-8898}/health"
echo

echo "[3/5] URL 验证 token 测试 ..."
HTTP_CODE=$(curl -sS -o /tmp/qrmes_feishu_verify.out -w '%{http_code}'   -X POST "http://127.0.0.1:${FEISHU_BOT_PORT:-8898}/feishu/event"   -H 'Content-Type: application/json'   -d "{"type":"url_verification","challenge":"ok123","header":{"token":"${FEISHU_BOT_VERIFICATION_TOKEN:-}"}}")
echo "HTTP ${HTTP_CODE}"
cat /tmp/qrmes_feishu_verify.out

echo
echo "[4/5] Python 语法检查 ..."
python3 -m py_compile $(find feishu_mes_bot tests -name '*.py')

echo "[5/5] 单元测试 ..."
python3 -m unittest discover -s tests -v

echo
echo "验证完成。"
