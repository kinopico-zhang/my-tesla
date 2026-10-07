"""首启引导 (/setup) 的接口与页面门: 无管理员时才是入口。

isolate autouse 种了管理员, 这里用 firstboot 夹具把账号库清空回到首启
口径 (空库 + 无 env 的死路正是引导页要救的场景)。本仓是三步版页面
(管理员 → 数据源 → 地图), 数据源/地图的保存走既有 /tesla/api/settings
(test_settings.py 已深测), 这里只测引导层的接线与门。"""
import re
from pathlib import Path

import pytest
from sqlalchemy import delete

from app import account_store
from app.models import User

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "home" / "static"


@pytest.fixture()
def firstboot(usersdb):
    """首启口径: 撤掉 isolate 种的管理员, 账号库回到空。"""
    usersdb.execute(delete(User))
    usersdb.commit()


def test_setup_status_needed_on_firstboot(  # pylint: disable=redefined-outer-name
        firstboot, client):
    """首启: needed=true (匿名可查, 只暴露这一个布尔)。"""
    r = client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json() == {"needed": True}


def test_setup_status_false_when_initialized(client):
    """已初始化的部署 (isolate 的种子管理员即此口径): needed=false。"""
    assert client.get("/api/setup-status").json() == {"needed": False}


def test_setup_admin_creates_and_logs_in(  # pylint: disable=redefined-outer-name
        firstboot, client, usersdb):
    """建管理员: is_admin 落库, 注册即登录 (cookie 直接过 /api/me)。"""
    r = client.post("/api/setup-admin",
                    json={"name": "owner", "password": "first-boot-pass"})
    assert r.status_code == 200, r.text
    user = account_store.find_by_name(usersdb, "owner")
    assert user is not None and user.is_admin
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {"name": "owner", "is_admin": True}


def test_setup_admin_rejected_when_initialized(client, usersdb):
    """已有管理员: 409 不新建 —— 公开端点只在首启窗口开口。"""
    r = client.post("/api/setup-admin",
                    json={"name": "intruder", "password": "hacked-123"})
    assert r.status_code == 409
    assert "已初始化" in r.json()["detail"]
    assert account_store.find_by_name(usersdb, "intruder") is None


def test_setup_admin_validation(  # pylint: disable=redefined-outer-name
        firstboot, client):
    """名称/密码不合规矩: 400 带中文原因。"""
    r = client.post("/api/setup-admin",
                    json={"name": "x", "password": "123456"})
    assert r.status_code == 400
    assert "名称" in r.json()["detail"]
    r = client.post("/api/setup-admin",
                    json={"name": "owner", "password": "12345"})
    assert r.status_code == 400
    assert "密码" in r.json()["detail"]


def test_setup_page_gate_opens_only_on_firstboot(  # pylint: disable=redefined-outer-name
        firstboot, client):
    """页面门: 首启 /setup 200; 建完管理员再访 302 回登录页。"""
    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert (client.post("/api/setup-admin",
                        json={"name": "owner",
                              "password": "first-boot-pass"}).status_code == 200)
    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_setup_page_redirects_when_initialized(client):
    """已初始化: /setup 一律 302 登录页, 不再出现引导面。"""
    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_setup_page_standards(  # pylint: disable=redefined-outer-name
        firstboot, client):
    """引导页面标准: 独立 App meta / manifest / 无刷新跳转 / js+css 引用
    一律版本化 (头部照本仓 login.html, 无 no-zoom/禁缩放是既有分叉)。"""
    html = client.get("/setup").text
    assert 'name="apple-mobile-web-app-capable"' in html
    assert 'href="/static/manifest.json"' in html
    assert "http-equiv" not in html
    for m in re.finditer(r'(?:src|href)="(/static/[^"]+\.(?:js|css)(?:\?[^"]*)?)"',
                         html):
        assert "?v=" in m.group(1), m.group(1)
    css = (STATIC_DIR / "css" / "setup-page.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in css
    assert "touch-action: manipulation" in css
    assert "touch-action: pan-y" in css


def test_setup_page_wiring(  # pylint: disable=redefined-outer-name
        firstboot, client):
    """三步版接线: 三张表单 + 完成跳转 data-done + setup.js 的接口指向。"""
    html = client.get("/setup").text
    assert 'data-done="/tesla"' in html
    for fid in ("form1", "form2", "form3"):
        assert f'id="{fid}"' in html
    js = client.get("/static/setup.js?v=1").text
    assert '"/api/setup-admin"' in js
    assert '"/tesla/api/settings"' in js
    assert 'data-done' in js and "dataset.done" in js


def test_login_js_probes_setup(client):
    """登录页探测: login.js 进页查引导状态, needed 时让位给 /setup。"""
    js = client.get("/static/login.js?v=3").text
    assert '"/api/setup-status"' in js
    assert '"/setup"' in js
