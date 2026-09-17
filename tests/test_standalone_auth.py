"""独立部署的鉴权接线测试: 根路径进应用 / 登录拦截 / 登录登出 /
旧地址搬家重定向 —— 独立仓与组合仓共用同一套账号配方, 这里验独立
装配那一层 (Tesla 没有 /music 式挂载, 全是路由页, 没有 307 补斜杠)。"""
from app import config
from tests.conftest import TEST_PASS, TEST_USER


def test_root_redirects_to_charging(client):
    """根路径无条件进 Tesla 应用 (独立仓没有门厅), 未登录与否都一样。"""
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tesla/charging"


def test_tesla_pages_redirect_to_scope_login(client):
    """未登录进 /tesla/*: 302 到应用 scope 内的登录页, 带原地址回跳。"""
    r = client.get("/tesla/charging", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == \
        "/tesla/login?next=%2Ftesla%2Fcharging"
    r = client.get("/tesla", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/tesla/login?next=%2Ftesla"
    # 登录页本身与静态资源放行 (表单要先看得见)
    assert client.get("/tesla/login").status_code == 200
    assert client.get("/login").status_code == 200


def test_api_unauthorized_401(client):
    """未登录的账号接口回 401 JSON (页面才 302, 接口不跳转)。"""
    r = client.get("/api/me")
    assert r.status_code == 401 and r.json() == {"detail": "未登录"}
    # 接口响应禁缓存 (改完账号浏览器不能用旧值)
    assert r.headers["cache-control"] == "no-store"


def test_login_flow(auth):
    """登录 → 会话 cookie 进 /tesla/charging; /api/me 报账号;
    登录页再进直接跳应用。"""
    r = auth.get("/tesla/charging")
    assert r.status_code == 200
    me = auth.get("/api/me").json()
    assert me == {"name": TEST_USER, "is_admin": True}
    r = auth.get("/login", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tesla/charging"
    r = auth.get("/tesla/login", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tesla/charging"


def test_login_wrong_password(client):
    """错密码 401, 不发 cookie; 限速计数涨 (第 6 次锁 60 秒)。"""
    for _ in range(config.LOGIN_MAX_FAILS):
        r = client.post("/api/login",
                        json={"user": TEST_USER, "password": "wrong"})
        assert r.status_code == 401 and "auth" not in r.cookies
    r = client.post("/api/login",
                    json={"user": TEST_USER, "password": TEST_PASS})
    assert r.status_code == 429 and "尝试次数过多" in r.json()["detail"]


def test_logout_clears_session(client, auth):  # pylint: disable=unused-argument
    """登出清 cookie: 再进 /tesla/charging 又被拦回登录页。"""
    assert client.post("/api/logout").status_code == 200
    r = client.get("/tesla/charging", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/tesla/login?next=%2Ftesla%2Fcharging"


def test_accounts_page_and_verify_file(client, auth):  # pylint: disable=unused-argument
    """账号管理页 (管理员) 在; 平台验证 TXT 不存在的一律 404
    (有则原样吐回, 见 pages.py)。"""
    assert auth.get("/accounts").status_code == 200
    assert client.get("/whatever.txt").status_code == 404


def test_legacy_moved_urls(client):
    """账号体系的旧地址 (还在 /tesla 下时留下的): 接口 307 / 页面 302
    搬到根路径, 查询串跟着走 —— 老书签和已发出的邀请链接还能用。"""
    r = client.get("/tesla/api/me", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/api/me"
    r = client.get("/tesla/api/login?x=1", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/api/login?x=1"
    r = client.get("/tesla/accounts", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/accounts"
    r = client.get("/tesla/accounts/api/accounts", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/accounts/api/accounts"
