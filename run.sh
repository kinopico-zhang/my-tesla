#!/bin/sh
# 启动服务: 有证书时 HTTPS 与 HTTP 双开 (两个端口两个进程), 没证书只开 HTTP。
#   HTTPS  → PORT      (默认 8500, Let's Encrypt 证书由 NAS 上的 acme.sh 签发
#                       续期, 续期 reloadcmd 调 deploy/restart_service.sh)
#   HTTP   → HTTP_PORT (默认 8501, 局域网 IP 直连明文访问)
# 存在 .env 时自动加载 (AMAP_KEY / HTTP_PORT 等, 见 .env.example)。
# HTTP=1 ./run.sh 可临时只开明文 (跳过 TLS, 单进程, 调试用)。
cd "$(dirname "$0")" || exit 1
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

PY=.venv/bin/python
HOST=0.0.0.0
PORT="${PORT:-8500}"

# 没证书 (或显式 HTTP=1): 单明文进程, exec 顶替 shell (与旧版行为一致)
if [ ! -f data/certs/fullchain.pem ] || [ "${HTTP:-0}" = "1" ]; then
  exec $PY -m uvicorn app.main:app --host "$HOST" --port "$PORT"
fi

# 有证书: HTTPS (主入口) + HTTP (局域网明文) 双开。
# 两个进程各自持有轨迹缓存与登录限速表 (会话 cookie 是无状态 HMAC 签名,
# 跨进程通用); 停服务时 deploy/restart_service.sh 按命令行特征杀全部进程。
HTTP_PORT="${HTTP_PORT:-8501}"
$PY -m uvicorn app.main:app --host "$HOST" --port "$PORT" \
  --ssl-keyfile data/certs/privkey.pem --ssl-certfile data/certs/fullchain.pem &
TLS_PID=$!
$PY -m uvicorn app.main:app --host "$HOST" --port "$HTTP_PORT" &
PLAIN_PID=$!
trap 'kill $TLS_PID $PLAIN_PID 2>/dev/null' TERM INT
wait $TLS_PID $PLAIN_PID
