"""首启引导 (/setup) 的接口与页面门: 三步配齐之前是唯一入口, 不允许跳过。

isolate autouse 种了管理员 + 高德 Key (已初始化口径), 这里用 firstboot 把
账号库清空、no_amap/no_teslamate 把配置撤掉, 拼出各缺口口径 (空库 + 无
env 的死路正是引导页要救的场景)。本仓是三步版页面 (管理员 → 数据源 →
地图), 数据源/地图的保存走既有 /tesla/api/settings (test_settings.py 已
深测), 这里测引导层的接线、缺口清单与应用门 (/tesla 的 302)。"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

import app.main as m
from app import account_store, database
from app.models import User
from app.tesla.models import AppSetting

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "home" / "static"


@pytest.fixture()
def firstboot(usersdb):
    """首启口径: 撤掉 isolate 种的管理员, 账号库回到空。"""
    usersdb.execute(delete(User))
    usersdb.commit()


@pytest.fixture()
def no_amap(owndb):
    """撤掉 conftest 种的高德 Key, 回到「地图步没配」口径。"""
    row = owndb.get(AppSetting, 1)
    row.amap_key = ""
    owndb.commit()


@pytest.fixture()
def no_teslamate(owndb, monkeypatch):
    """撤掉 TeslaMate 连接 (env 与 docker 定位都掐掉): 「数据源步没配」。

    docker 候选一并 patch 掉 —— 有真 docker 的机器上 inspect 一个不存在的
    容器虽然必败, 但那要起子进程, 测试里没必要。"""
    row = owndb.get(AppSetting, 1)
    row.tmdb_host = ""
    owndb.commit()
    monkeypatch.delenv("TMDB_HOST")

    def _no_docker() -> str:
        raise RuntimeError("测试口径: 无 docker")

    monkeypatch.setattr(database, "resolve_db_host", _no_docker)


def test_setup_status_needed_on_firstboot(  # pylint: disable=redefined-outer-name
        firstboot, client):
    """首启: needed=true, 缺口只有账号一步 (数据源/地图 isolate 已配)。"""
    r = client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json() == {"needed": True, "missing": ["account"]}


def test_setup_status_false_when_initialized(client):
    """已初始化的部署 (isolate 的种子管理员 + 配置即此口径): 全配齐。"""
    assert client.get("/api/setup-status").json() == {"needed": False, "missing": []}


def test_setup_status_lists_config_gaps(  # pylint: disable=redefined-outer-name
        auth, owndb, no_amap, no_teslamate):
    """缺口清单: 数据源与地图都没配 → 两步都在; 配一步少一步。"""
    d = auth.get("/api/setup-status").json()
    assert d == {"needed": True, "missing": ["teslamate", "amap"]}
    owndb.get(AppSetting, 1).tmdb_host = "10.0.0.9"
    owndb.commit()
    d = auth.get("/api/setup-status").json()
    assert d == {"needed": True, "missing": ["amap"]}
    r = auth.post("/tesla/api/settings", json={"amap_key": "abcd1234efgh5678"})
    assert r.status_code == 200
    assert auth.get("/api/setup-status").json() == {"needed": False, "missing": []}


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
    """页面门: 首启 /setup 200; 建完管理员且配置齐 (isolate 口径) 再访
    302 回登录页。"""
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


def test_setup_page_resume_requires_login(  # pylint: disable=redefined-outer-name
        auth, no_amap):
    """中途退出的续走: 管理员已在但配置缺 → 匿名访客先去登录页拿会话
    (带 next 回来), 已登录的直接进引导页接着配。"""
    anon = TestClient(m.app)   # auth 与本用例共享同一个 client, 匿名视角另开
    r = anon.get("/setup", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (302, "/login?next=/setup")
    r = auth.get("/setup", follow_redirects=False)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_tesla_shell_gated_until_wizard_done(  # pylint: disable=redefined-outer-name
        auth, no_amap):
    """应用门: 引导没走完 (还差高德 Key), /tesla 一律 302 回 /setup;
    补齐最后一步立刻放行 (2026-10-09 「必须都配置了才能进入 app」)。"""
    r = auth.get("/tesla", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (302, "/setup")
    assert auth.post("/tesla/api/settings",
                     json={"amap_key": "abcd1234efgh5678"}).status_code == 200
    r = auth.get("/tesla", follow_redirects=False)
    assert r.status_code == 200
    assert "html" in r.headers["content-type"]


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
    """三步版接线: 三张表单 + 完成跳转 data-done + setup.js 的接口指向;
    不允许跳过 (无跳过钮, 关键字段必填), 起步步数跟着缺口走。"""
    html = client.get("/setup").text
    assert 'data-done="/tesla"' in html
    for fid in ("form1", "form2", "form3"):
        assert f'id="{fid}"' in html
    assert "skip" not in html          # 不允许跳过: 跳过钮整链退役
    assert "btn-plain" not in html
    assert re.search(r'id="tm-host"[^>]*required', html)
    assert re.search(r'id="amap-key"[^>]*required', html)
    js = client.get("/static/setup.js?v=2").text
    assert '"/api/setup-admin"' in js
    assert '"/tesla/api/settings"' in js
    assert 'data-done' in js and "dataset.done" in js
    assert ".skip" not in js and "setup-status" in js
    assert 'missing.includes("account")' in js


def test_login_js_probes_setup(client):
    """登录页探测: login.js 进页查引导状态, 只在账号步还缺 (真正的首启)
    时让位给 /setup —— 管理员已在只差配置的部署照常登录, 由应用门接手。"""
    js = client.get("/static/login.js?v=4").text
    assert '"/api/setup-status"' in js
    assert 'missing.includes("account")' in js
    assert '"/setup"' in js
