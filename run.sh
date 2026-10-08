#!/bin/sh
# 启动服务: 部署配置全走命令行参数, 本脚本只是 python -m app 的透传壳
# (全量清单 ./run.sh --help; 旧版读 .env 的方式已退役 —— 参数没给的
# 回落同名环境变量, 再回落内置默认)。
#   有证书 (默认 data/certs/) → HTTPS 走 --port (默认 8500, Let's Encrypt
#     证书由 WSL 上的 acme.sh 签发续期, reloadcmd 调组合仓根
#     deploy/local/reload-cert.sh) + 局域网明文走 --http-port (默认 8501),
#     双端口双进程
#   没证书 → 只开 --port 的明文; --http 可强制明文 (忽略证书, 调试用)
cd "$(dirname "$0")" || exit 1

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "缺 $PY: 先 python3.13 -m venv .venv 装依赖 (见 README 快速开始)" >&2
  exit 1
fi
exec "$PY" -m app "$@"
