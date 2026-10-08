"""命令行启动器 (python -m app): 部署配置全走参数。

独立部署的完整配置面: 监听 / TeslaMate / 库与缓存 / 显示口径。没给的
参数回落同名环境变量 (自动化 / 测试 / 组合仓注入用), 再回落各消费模块
的内置默认 —— 显式参数 > 环境变量 > 默认值; 参数显式给空串 = 清掉对应
环境变量。

单端口: 证书目录 (默认 data/certs) 里有 fullchain.pem + privkey.pem 时
该端口走 TLS (Let's Encrypt 证书由 WSL 上的 acme.sh 签发续期), 没证书
走明文; --http 可强制明文 (忽略证书, 调试用)。

账号与高德 Key 不走参数: 空账号库首启由登录页自动引去 /setup 引导注册
管理员, 高德 Key 在设置页「地图设置」里保存 (存自有库)。

My Home 组合部署不走本模块 —— 账号归启动方: 外层装配用组合仓自己的
门厅层, 本模块只服务本仓独立启动 (自带账号层)。
"""
from __future__ import annotations

import argparse
import os
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
        """argparse 目标属性名 (--teslamate-host → teslamate_host)。"""
        return self.flag[2:].replace("-", "_")


_GROUPS: tuple[tuple[str, tuple[_Knob, ...]], ...] = (
    ("账号体系 (账号库与会话; 组合部署由外层统一)",
     (_Knob("--users-db", "MYHOME_USERS_DB",
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
               "  python -m app                           # 全默认, 浏览器打开 /setup 引导\n"
               "  python -m app --port 8600\n"
               "  python -m app --teslamate-host 192.168.31.5 --teslamate-password ***",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    svc = parser.add_argument_group("服务与监听")
    svc.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    svc.add_argument("--port", type=int, default=8500,
                     help="端口: 有证书走 TLS, 没证书走明文 (默认 8500)")
    svc.add_argument("--cert-dir", default="data/certs",
                     help="TLS 证书目录 (默认 data/certs; 内含 fullchain.pem 与 "
                          "privkey.pem 即启用 HTTPS)")
    svc.add_argument("--http", action="store_true",
                     help="强制明文, 忽略证书 (调试用)")
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
    """证书对 (私钥, 证书); 目录里不齐 → None (明文开)。"""
    directory = Path(args.cert_dir)
    if not directory.is_absolute():
        directory = PROJECT_DIR / directory
    pair = (directory / "privkey.pem", directory / "fullchain.pem")
    return pair if all(p.is_file() for p in pair) else None


def main(argv: Sequence[str] | None = None) -> None:
    """解析参数 → 落环境 → 单进程单端口起服务 (有证书走 TLS, 否则明文)。"""
    args = build_parser().parse_args(argv)
    apply_env(args)
    pair = None if args.http else cert_pair(args)
    if pair is None:
        uvicorn.run("app.main:app", host=args.host, port=args.port)
    else:
        uvicorn.run("app.main:app", host=args.host, port=args.port,
                    ssl_keyfile=str(pair[0]), ssl_certfile=str(pair[1]))
