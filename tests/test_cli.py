"""CLI 启动器测试: 参数解析与回落链 (显式参数 > 环境变量 > 内置默认)、
证书判定 (TLS 的开关)、配置面对账 (旋钮 ↔ 消费模块读的环境变量)。

账号与高德 Key 不在参数面里 (管理员走 /setup 首启引导, 高德在设置页
「地图设置」里保存) —— 对账清单钉死这条边界, 谁往里加 auth/amap 旋钮
当场红。真启动链路 (命令行 → uvicorn → 登录) 由 test_e2e.py 盖着。"""
import argparse
import os

from app import cli


def _all_knobs():
    """全部配置旋钮 (拉平分组)。"""
    return [k for _, knobs in cli._GROUPS for k in knobs]  # pylint: disable=protected-access


# ---------------------------------------------------------------- 配置面对账
def test_knob_surface_matches_consumer_envs():
    """配置面对账: 旋钮回落的环境变量与各消费模块 (config / settings_store /
    teslamate_engine / 缓存) 读的一一对应。新增配置项时先在消费模块读 env,
    再来这里加旋钮 —— 清单钉死, 少写或写错 env 名当场红。"""
    assert {k.env for k in _all_knobs()} == {
        "MYHOME_USERS_DB", "MYHOME_SECRET_FILE", "SESSION_DAYS",
        "TMDB_HOST", "TMDB_PORT", "TMDB_USER", "TMDB_PASS", "TMDB_NAME",
        "TMDB_CONTAINER", "DOCKER_BIN",
        "MYTESLA_DB", "MAP_CACHE_FILE", "SPEED_HIST_CACHE_FILE",
        "TZ_NAME", "CUR_SYMBOL",
    }
    assert len({k.flag for k in _all_knobs()}) == len(_all_knobs())


def test_every_flag_accepts_value():
    """全量旋钮都能从命令行喂进去 (拼一条全参数命令, 解析后逐项对上)。"""
    argv: list[str] = []
    for knob in _all_knobs():
        argv += [knob.flag, "x"]
    args = cli.build_parser().parse_args(argv)
    for knob in _all_knobs():
        assert getattr(args, knob.dest) == "x", knob.flag


# ---------------------------------------------------------------- 回落链
def test_service_defaults_and_knobs_default_none():
    """服务参数有实默认 (本模块直接消费); 配置旋钮一律 default=None ——
    默认留在各消费模块, 不在两处维护。"""
    args = cli.build_parser().parse_args([])
    assert (args.host, args.port, args.cert_dir, args.http) \
        == ("0.0.0.0", 8500, "data/certs", False)
    for knob in _all_knobs():
        assert getattr(args, knob.dest) is None, knob.flag


def test_explicit_arg_overrides_env(monkeypatch):
    """显式参数 > 环境变量 (启动器把参数落进 env, import app 前就位)。"""
    monkeypatch.setenv("TMDB_HOST", "from-env")
    cli.apply_env(cli.build_parser().parse_args(["--teslamate-host", "from-cli"]))
    assert os.environ["TMDB_HOST"] == "from-cli"


def test_absent_arg_keeps_env(monkeypatch):
    """没给的参数不动环境 —— 环境变量/内置默认照旧生效 (自动化注入通道)。"""
    monkeypatch.setenv("TMDB_HOST", "from-env")
    cli.apply_env(cli.build_parser().parse_args([]))
    assert os.environ["TMDB_HOST"] == "from-env"


def test_empty_arg_clears_env(monkeypatch):
    """显式给空串 = 清掉环境变量 (把 env 注入的值临时退回内置默认)。"""
    monkeypatch.setenv("TZ_NAME", "UTC")
    cli.apply_env(cli.build_parser().parse_args(["--tz", ""]))
    assert "TZ_NAME" not in os.environ


# ---------------------------------------------------------------- 证书判定
def test_cert_pair_detects_full_set(tmp_path):
    """证书目录里私钥+证书齐 → 返回证书对 (TLS 开); 缺一件 → None。"""
    ns = argparse.Namespace(cert_dir=str(tmp_path))
    assert cli.cert_pair(ns) is None
    (tmp_path / "privkey.pem").write_text("k", encoding="utf-8")
    assert cli.cert_pair(ns) is None                    # 只有私钥不算
    (tmp_path / "fullchain.pem").write_text("c", encoding="utf-8")
    assert cli.cert_pair(ns) == (tmp_path / "privkey.pem",
                                 tmp_path / "fullchain.pem")
