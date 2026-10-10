"""E2E 冒烟: 起真服务子进程打真 HTTP —— CI 三平台矩阵跑的就是这套。

不走 TestClient: 完整过一遍 命令行启动 → lifespan 建库 → /setup 引导建
管理员 → 登录 → 页面 / 静态资源, 与生产路径同构 (python -m app, 配置
全走参数)。全部数据文件落在 pytest 临时目录, 不碰仓库 data/ 里的真实
库; TeslaMate 指到必拒连的本地口 (引擎懒连接 + 预热线程自兜底), e2e
不依赖真实数据源。
"""
import os
import re
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
E2E_USER = "admin"
E2E_PASS = "e2e-smoke-pass"


def _free_port() -> int:
    """让系统分一个空闲口 (bind 0 后立刻放手, 给 uvicorn 用)。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[str]:
    """起一个真服务, 就绪后返回 base_url; 整模块共享, 收尾硬收进程。"""
    tmp = tmp_path_factory.mktemp("e2e")
    log = open(tmp / "server.log", "w+b")           # pylint: disable=consider-using-with
    port = _free_port()
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-m", "app",
         "--http",                          # 强制明文 (本机有证书也不进 TLS)
         "--host", "127.0.0.1", "--port", str(port),
         "--users-db", str(tmp / "users.db"),
         "--secret-file", str(tmp / "session_secret"),
         "--mytesla-db", f"sqlite:///{(tmp / 'mytesla.db').as_posix()}",
         # TeslaMate 指到必拒连的本地口: 不探 docker, 永不碰真实库
         "--teslamate-host", "127.0.0.1", "--teslamate-port", "1",
         "--teslamate-user", "e2e", "--teslamate-password", "e2e",
         "--teslamate-db", "e2e"],
        cwd=str(ROOT), env={**os.environ},
        stdout=log, stderr=subprocess.STDOUT)
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
        # 空库首启: 管理员走 /setup 引导建 (与生产同路径, 启动器不种账号)
        r = httpx.post(base + "/api/setup-admin",
                       json={"name": E2E_USER, "password": E2E_PASS},
                       timeout=5.0)
        assert r.status_code == 200, r.text[:200]
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


def test_app_page_requires_login(client):  # pylint: disable=redefined-outer-name
    """未登录进业务页: 302 到登录页 (不越出 scope)。"""
    r = client.get(APP_PATH, follow_redirects=False)
    assert r.status_code == 302, r.text[:200]
    assert "/login" in r.headers["location"]


def test_login_page_renders(client):  # pylint: disable=redefined-outer-name
    """登录页本身可渲染。"""
    r = client.get("/login")
    assert r.status_code == 200
    assert "html" in r.headers["content-type"]


def test_wrong_password_rejected(client):  # pylint: disable=redefined-outer-name
    """错密码 401 (单次失败, 不触 5 次锁 60s)。"""
    r = client.post("/api/login", json={"user": E2E_USER, "password": "wrong"})
    assert r.status_code in (401, 403), r.text[:200]


def test_login_session_and_app_page(client):  # pylint: disable=redefined-outer-name
    """正确登录种 cookie → 引导没走完时应用门拦回 /setup, 补上高德 Key
    (引导最后一步) 后业务页 200 / /api/me 报账号。"""
    r = client.post("/api/login", json={"user": E2E_USER, "password": E2E_PASS})
    assert r.status_code == 200, r.text[:200]
    gate = client.get(APP_PATH, follow_redirects=False)
    assert (gate.status_code, gate.headers["location"]) == (302, "/setup")
    assert client.post("/tesla/api/settings",
                       json={"amap_key": "e2e-amap-key",
                             "amap_web_key": "e2e-web-key"}).status_code == 200
    r = client.get(APP_PATH)
    assert r.status_code == 200
    assert "html" in r.headers["content-type"]
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["name"] == E2E_USER


def test_settings_api_after_login(client):  # pylint: disable=redefined-outer-name
    """设置接口走自有库 (不依赖 TeslaMate 连通)。"""
    client.post("/api/login", json={"user": E2E_USER, "password": E2E_PASS})
    r = client.get(APP_PATH + "/api/settings")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_static_assets_serve(client):  # pylint: disable=redefined-outer-name
    """登录页引用的静态资源可取 (静态挂载 + 不可变缓存链路通)。"""
    client.post("/api/login", json={"user": E2E_USER, "password": E2E_PASS})
    html = client.get("/login").text
    m = re.search(r'(?:src|href)="(/[^"]+\.(?:js|css)(?:\?[^"]*)?)"', html)
    assert m, "登录页里没抓到静态资源地址"
    r = client.get(m.group(1))
    assert r.status_code == 200, m.group(1)
