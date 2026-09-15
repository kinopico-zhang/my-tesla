#!/bin/sh
# 重启 My Tesla 服务 (走仓库根的 run.sh: 自动带 .env 与 HTTPS 证书;
# admin 身份、后台运行、日志 /tmp/my-tesla.log)。
# 手动重启用; acme.sh 续完证书的 reloadcmd 也是它 —— root 调时先把
# 证书属主交给 admin (服务以 admin 跑, 读不了 root 600)。
cd "$(dirname "$0")/.." || exit 1
if [ "$(id -u)" = "0" ] && [ -f data/certs/privkey.pem ]; then
  chown admin data/certs/privkey.pem data/certs/fullchain.pem 2>/dev/null
  chmod 600 data/certs/privkey.pem
fi
# QNAP 没有 pkill (静默失败会端口冲突), 用 ps+kill 找 pid
PIDS=$(ps | grep 'uvicorn app.main:app' | grep -v grep | awk '{print $1}')
[ -n "$PIDS" ] && kill $PIDS 2>/dev/null
sleep 2
/usr/bin/sudo -u admin sh -c 'exec /bin/setsid /share/CACHEDEV1_DATA/Public/my-tesla/run.sh >> /tmp/my-tesla.log 2>&1 < /dev/null &'
