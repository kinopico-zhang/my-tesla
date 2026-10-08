"""命令行启动器 (python -m app, ./run.sh 原样透传): 部署配置全走参数。

独立部署的完整配置面: 监听 / 账号种子 / TeslaMate / 高德 / 库与缓存 /
显示口径。没给的参数回落同名环境变量 (自动化 / 测试 / 组合仓注入用),
再回落各消费模块的内置默认 —— 显式参数 > 环境变量 > 默认值; 参数显式
给空串 = 清掉对应环境变量。

证书目录 (默认 data/certs) 里有 fullchain.pem + privkey.pem 时双端口
双进程: TLS 走 --port (Let's Encrypt 证书由 WSL 上的 acme.sh 签发续期),
局域网明文走 --http-port, 本进程退化为看护者 (转发信号, 任一子进程退出
就全组收); --http 或没证书时单明文进程, 本进程直接就是服务。会话
cookie 是无状态 HMAC 签名, 两个口通用。

My Home 组合部署不走本模块 —— 账号归启动方: 外层装配用组合仓自己的
门厅层, 本模块只服务本仓独立启动 (自带账号层)。
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import types
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import uvicorn

PROJECT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class _Knob:
    """一个配置旋钮: 命令行参数 ↔ 回落的环境变量。

    默认值只写进帮助文案, 解析一律 default=None —— 实际默认留在各消费
    模块 (config / settings_store / teslamate_engine), 不在两处维护。"""

    flag: str
    env: str
    help: str

    @property
    def dest(self) -> str:
        """argparse 目标属性名 (--auth-user → auth_user)。"""
        return self.flag[2:].replace("-", "_")


_GROUPS: tuple[tuple[str, tuple[_Knob, ...]], ...] = (
    ("账号体系 (独立部署自带; My Home 组合部署由外层统一)",
     (_Knob("--auth-user", "AUTH_USER",
            "首启种子管理员用户名 (默认 admin, 只在空账号库时种)"),
      _Knob("--auth-pass", "AUTH_PASS",
            "首启种子密码 (不设则浏览器打开 /setup 引导注册)"),
      _Knob("--users-db", "MYHOME_USERS_DB",
            "账号库 (默认 data/users.db; 裸路径相对仓根, 也认 sqlite:///… URL)"),
      _Knob("--secret-file", "MYHOME_SECRET_FILE",
            "会话签名密钥文件 (默认 .session_secret; 与组合仓共用同一枚)"),
      _Knob("--session-days", "SESSION_DAYS",
            "会话有效期天数 (默认 90)"))),
    ("TeslaMate 连接 (PostgreSQL; 可全留空后填, 设置页里存的优先)",
     (_Knob("--teslamate-host", "TMDB_HOST",
            "PostgreSQL 主机 (未设回落 docker 容器定位)"),
      _Knob("--teslamate-port", "TMDB_PORT", "端口 (默认 5432)"),
      _Knob("--teslamate-user", "TMDB_USER", "用户 (默认 teslamate)"),
      _Knob("--teslamate-password", "TMDB_PASS", "密码"),
      _Knob("--teslamate-db", "TMDB_NAME", "库名 (默认 teslamate)"),
      _Knob("--teslamate-container", "TMDB_CONTAINER",
            "docker 容器名兜底定位 (默认 teslamate_cn_database_1)"),
      _Knob("--docker-bin", "DOCKER_BIN",
            "docker 可执行文件 (默认 PATH 里依次找)"))),
    ("高德开放平台 (个人开发者免费, console.amap.com; 也可设置页里保存)",
     (_Knob("--amap-key", "AMAP_KEY",
            "Web端 (JS API) Key —— 服务平台必须选「Web端 (JS API)」"),
      _Knob("--amap-security-code", "AMAP_SECURITY_CODE",
            "安全密钥 (Key 详情页)"),
      _Knob("--amap-web-key", "AMAP_WEB_KEY",
            "Web 服务 Key (足迹道路拟合 / 逆地理, 与 JS Key 是两种)"))),
    ("数据与缓存",
     (_Knob("--mytesla-db", "MYTESLA_DB",
            "自有库, 轨迹断档补路等自产数据 (默认 sqlite:///data/mytesla.db)"),
      _Knob("--map-cache", "MAP_CACHE_FILE",
            "轨迹盘缓存 (默认 data/tracks_cache.json)"),
      _Knob("--speed-cache", "SPEED_HIST_CACHE_FILE",
            "速度直方图盘缓存 (默认 data/speed_hist_cache.json)"))),
    ("显示口径",
     (_Knob("--tz", "TZ_NAME", "时区 (默认 Asia/Shanghai)"),
      _Knob("--currency", "CUR_SYMBOL", "货币符号 (默认 ¥)"))),
)


def build_parser() -> argparse.ArgumentParser:
    """全量参数的解析器 (帮助文案即部署文档)。"""
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="My Tesla 独立部署启动器: 部署配置全走命令行参数",
        epilog="没给的参数回落同名环境变量 (如 --teslamate-host → TMDB_HOST),\n"
               "再回落内置默认; 显式给空串可清掉环境变量。示例:\n"
               "  ./run.sh                                # 全默认, 浏览器打开 /setup 引导\n"
               "  ./run.sh --port 8600 --http-port 8601\n"
               "  ./run.sh --teslamate-host 192.168.31.5 --teslamate-password *** \\\n"
               "             --amap-key *** --amap-security-code ***",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    svc = parser.add_argument_group("服务与监听")
    svc.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    svc.add_argument("--port", type=int, default=8500,
                     help="主端口: 有证书走 TLS, 没证书走明文 (默认 8500)")
    svc.add_argument("--http-port", type=int, default=8501,
                     help="局域网明文端口, 有证书时与主端口双开 (默认 8501)")
    svc.add_argument("--cert-dir", default="data/certs",
                     help="TLS 证书目录 (默认 data/certs; 内含 fullchain.pem 与 "
                          "privkey.pem 即启用 HTTPS)")
    svc.add_argument("--http", action="store_true",
                     help="强制明文单开, 忽略证书 (调试用)")
    for title, knobs in _GROUPS:
        group = parser.add_argument_group(title)
        for knob in knobs:
            group.add_argument(knob.flag, default=None,
                               help=f"{knob.help} (回落 {knob.env})")
    return parser


def apply_env(args: argparse.Namespace) -> None:
    """把显式给的参数写进环境变量 —— app 各模块按 env 读配置, 必须在
    import app.main 之前就位; 没给的参数不动环境 (回落链生效), 给空串
    = 显式清掉。"""
    for _, knobs in _GROUPS:
        for knob in knobs:
            value = getattr(args, knob.dest)
            if value is None:
                continue
            if value == "":
                os.environ.pop(knob.env, None)
            else:
                os.environ[knob.env] = value


def cert_pair(args: argparse.Namespace) -> tuple[Path, Path] | None:
    """证书对 (私钥, 证书); 目录里不齐 → None (单明文开)。"""
    directory = Path(args.cert_dir)
    if not directory.is_absolute():
        directory = PROJECT_DIR / directory
    pair = (directory / "privkey.pem", directory / "fullchain.pem")
    return pair if all(p.is_file() for p in pair) else None


def main(argv: Sequence[str] | None = None) -> None:
    """解析参数 → 落环境 → 单进程明文直跑, 有证书时看护双进程。"""
    args = build_parser().parse_args(argv)
    apply_env(args)
    pair = None if args.http else cert_pair(args)
    if pair is None:
        # 单明文进程: 本进程就是服务, 信号直通 uvicorn (与旧 run.sh 的
        # exec 顶替同 —— 少一层父进程, systemd 视角行为不变)
        uvicorn.run("app.main:app", host=args.host, port=args.port)
        return
    # 有证书: 本进程退化为看护者, TLS (主入口) 与局域网明文各一个子进程
    # —— 与旧 run.sh 双进程同构 (两个服务进程各自持有轨迹缓存与登录
    # 限速表; 会话 cookie 无状态 HMAC 签名, 跨进程通用)。
    # 不用「本进程跑 TLS + finally 收子进程」: uvicorn 优雅退出后会恢复
    # 默认信号处置并重抛收到的信号, 进程当场死亡, finally 走不到 ——
    # 看护者只 wait 不服务, 信号转发才是稳的。
    base = [sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", args.host]
    commands = [
        base + ["--port", str(args.port),
                "--ssl-keyfile", str(pair[0]), "--ssl-certfile", str(pair[1])],
        base + ["--port", str(args.http_port)]]
    procs = [subprocess.Popen(cmd, cwd=str(PROJECT_DIR))  # pylint: disable=consider-using-with
             for cmd in commands]

    def _forward(signum: int, _frame: types.FrameType | None) -> None:
        """看护者收到信号 → 转发给两个子进程再退 (不留孤儿)。"""
        for proc in procs:
            if proc.poll() is None:
                proc.send_signal(signum)
        sys.exit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _forward)
    try:
        while all(proc.poll() is None for proc in procs):
            time.sleep(0.2)     # 任一子进程先退 (崩溃/被停) 就全组收
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
