"""E2E 首启引导: 空账号库 + 无 AUTH_PASS 起真服务, 全程走 HTTP。

test_e2e.py 验的是「已初始化」的常态; 这里验的是 env 一字不设的死路
场景 —— 过去这个口径永远登不进 (邀请注册要管理员发邀请), 现在由 /setup
引导救活。流程: needed=true → /setup 可开 → POST 建管理员 (注册即登录,
cookie 直接过应用页与设置接口) → 窗口关闭 (再 POST 409, /setup 302)。
数据文件照旧落 pytest 临时目录, TeslaMate 指必拒连口, 不碰真实库。
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
APP_PATH = "/tesla"                  # 本仓业务前缀 (money/music 仓各改各的)
SETUP_USER = "owner"
SETUP_PASS = "e2e-setup-pass"


def _free_port() -> int:
    """让系统分一个空闲口 (bind 0 后立刻放手, 给 uvicorn 用)。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[str]:
    """首启口径起真服务: AUTH_PASS 留空 = 不种管理员, 整个模块共享。"""
    tmp = tmp_path_factory.mktemp("e2e_setup")
    log = open(tmp / "server.log", "w+b")           # pylint: disable=consider-using-with
    env = {
        **os.environ,
        "AUTH_PASS": "",                            # 首启: env 不种, /setup 接管
        "MYHOME_USERS_DB": str(tmp / "users.db"),
        "MYHOME_SECRET_FILE": str(tmp / "session_secret"),
        "MYTESLA_DB": f"sqlite:///{(tmp / 'mytesla.db').as_posix()}",
        # TeslaMate 指到必拒连的本地口: 不探 docker, 永不碰真实库
        "TMDB_HOST": "127.0.0.1", "TMDB_PORT": "1",
        "TMDB_USER": "e2e", "TMDB_PASS": "e2e", "TMDB_NAME": "e2e",
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


@pytest.fixture(scope="module")
def client(server) -> Iterator[httpx.Client]:  # pylint: disable=redefined-outer-name
    """带自动 cookie 的客户端 (base_url 已设, 重定向默认跟随)。"""
    with httpx.Client(base_url=server, timeout=10.0, follow_redirects=True) as c:
        yield c


def test_firstboot_status_needed(client):  # pylint: disable=redefined-outer-name
    """首启: 匿名可查引导状态, needed=true。"""
    r = client.get("/api/setup-status")
    assert r.status_code == 200, r.text[:200]
    assert r.json() == {"needed": True}


def test_setup_page_renders(client):  # pylint: disable=redefined-outer-name
    """首启: /setup 页面可开, 引导表单在场。"""
    r = client.get("/setup")
    assert r.status_code == 200
    assert "html" in r.headers["content-type"]
    assert 'id="form1"' in r.text


def test_setup_admin_full_flow(client):  # pylint: disable=redefined-outer-name
    """建管理员 → 注册即登录全站通行 → 窗口即刻关闭。

    cookie 过 /api/me 与应用页; /tesla/api/settings 同会话可取 (引导
    第 2/3 步的预填链路); 之后再 POST 409、/setup 302 回登录页、
    setup-status 翻成 needed=false。"""
    r = client.post("/api/setup-admin",
                    json={"name": SETUP_USER, "password": SETUP_PASS})
    assert r.status_code == 200, r.text[:200]
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {"name": SETUP_USER, "is_admin": True}
    page = client.get(APP_PATH)
    assert page.status_code == 200
    assert "html" in page.headers["content-type"]
    settings = client.get("/tesla/api/settings")
    assert settings.status_code == 200
    assert isinstance(settings.json(), dict)

    again = client.post("/api/setup-admin",
                        json={"name": "intruder", "password": "hacked-123"})
    assert again.status_code == 409
    gate = client.get("/setup", follow_redirects=False)
    assert gate.status_code == 302
    assert gate.headers["location"] == "/login"
    assert client.get("/api/setup-status").json() == {"needed": False}
