"""E2E 无 env 首启: TeslaMate 连接信息一字不设也能起服务、进引导。

2026-10-09 前这里就是死路: build_db_url 定位不到库主机直接 RuntimeError,
lifespan 起不来 (单测的 conftest 一直种着 TMDB_HOST 把病盖住, 跨机装机的
真实第一秒才炸)。现在引擎落 .invalid 占位主机 (懒连接), /setup 照常服务,
引导缺口三步俱全; 依赖数据源的后台预热/worker 挂起等配置, 向导第二步
存好真地址才开动。本模块只验「起得来 + 门诚实」, 三步走完的完整流程在
test_e2e_setup。数据文件照旧落 pytest 临时目录, 不碰真实库与生产缓存。
"""
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    """让系统分一个空闲口 (bind 0 后立刻放手, 给 uvicorn 用)。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[str]:
    """无 TMDB_* 首启口径起真服务: 数据源完全没配, 引导是唯一入口。"""
    tmp = tmp_path_factory.mktemp("e2e_firstboot_noenv")
    log = open(tmp / "server.log", "w+b")           # pylint: disable=consider-using-with
    env = {
        # 本进程若带着 TMDB_* / DOCKER_BIN (比如跑测时 shell 注入), 一并
        # 摘掉 —— 本模块验的就是「一个都不给」
        **{k: v for k, v in os.environ.items()
           if not k.startswith(("TMDB_", "DOCKER_BIN"))},
        "AUTH_PASS": "",                            # 首启: env 不种, /setup 接管
        "MYHOME_USERS_DB": str(tmp / "users.db"),
        "MYHOME_SECRET_FILE": str(tmp / "session_secret"),
        "MYTESLA_DB": f"sqlite:///{(tmp / 'mytesla.db').as_posix()}",
        # 盘缓存重定向: 绝不落仓内 data/ (生产缓存在那)
        "MAP_CACHE_FILE": str(tmp / "tracks_cache.json"),
        "SPEED_HIST_CACHE_FILE": str(tmp / "speed_hist_cache.json"),
    }
    port = _free_port()
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30.0
    try:
        while time.monotonic() < deadline:
            assert proc.poll() is None, "服务启动即退出:\n" + _tail(log)
            try:
                httpx.get(base + "/login", timeout=1.0, follow_redirects=True)
                break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise AssertionError("服务 30s 未就绪:\n" + _tail(log))
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def _tail(log) -> str:
    """服务日志尾 (失败诊断用)。"""
    log.flush()
    log.seek(0)
    return b"".join(log.readlines()[-30:]).decode("utf-8", "replace")


def test_noenv_boot_setup_status(server):  # pylint: disable=redefined-outer-name
    """无 env 起得来 (lifespan 不再被定位不到库主机炸死), 引导缺口三步
    俱全 —— 数据源不再由 env 顶着, 首启要的就是这个口径。"""
    r = httpx.get(server + "/api/setup-status", timeout=10.0)
    assert r.status_code == 200, r.text[:200]
    assert r.json() == {"needed": True,
                        "missing": ["account", "teslamate", "amap"]}


def test_noenv_setup_page_served(server):  # pylint: disable=redefined-outer-name
    """/setup 引导页在场: 什么都没配的状态也能服务到用户眼前。"""
    r = httpx.get(server + "/setup", timeout=10.0)
    assert r.status_code == 200
    assert 'id="form1"' in r.text
