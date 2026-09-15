"""鉴权 / 路由 / 中间件测试。"""
import hashlib
import hmac
import struct
import time
import zlib
from pathlib import Path

from fastapi.testclient import TestClient

from app import account_store, authentication, config
import app.main as m

# 全部对外页面 (账号层 + Tesla 应用), 多处遍历用
ALL_PAGES = ["/login", "/register", "/tesla/charging", "/tesla/stats",
             "/tesla/chargemap", "/tesla/map", "/tesla/changelog", "/tesla/trips",
             "/tesla/groups", "/tesla/live", "/tesla/settings", "/accounts"]


def _unfilter_png(raw: bytes, w: int, ch: int) -> list[bytearray]:
    """逆 PNG 行滤镜 (8-bit, 滤镜 0-4), 返回每行的 RGB(A) 字节 (不引 Pillow)。"""
    stride = w * ch + 1
    rows: list[bytearray] = []
    for y in range(len(raw) // stride):
        f = raw[y * stride]
        row = bytearray(raw[y*stride+1:(y+1)*stride])
        up = rows[y - 1] if y else None
        for x in range(w * ch):
            a = row[x - ch] if x >= ch else 0
            b = up[x] if up is not None else 0
            c = up[x - ch] if up is not None and x >= ch else 0
            if f == 1:
                row[x] = (row[x] + a) & 255
            elif f == 2:
                row[x] = (row[x] + b) & 255
            elif f == 3:
                row[x] = (row[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc
                                    else b if pb <= pc else c)) & 255
        rows.append(row)
    return rows


# ---------------------------------------------------------------- 登录
def test_all_pages_have_standalone_meta(auth):
    """全部页面 (含登录/注册) 都带全屏 App meta。

    桌面图标是全屏 web app, 有独立 cookie 存储: 首次启动必然 302 到登录页。
    登录页一旦缺 meta, 整个 App 会被弹回 Safari 露地址栏, 之后再也回不去
    全屏 (2026-09-12 用户踩坑)。任何新增页面都必须带上。
    """
    anon = TestClient(m.app)
    for path in ALL_PAGES:
        # /login 对已登录者是 302 进应用, 匿名视角才看得到登录页本身
        html = (anon if path == "/login" else auth).get(path).text
        assert 'name="apple-mobile-web-app-capable" content="yes"' in html, path
        assert 'content="black-translucent"' in html, path
        # manifest 各用各的: 账号层一份, Tesla 应用一份
        manifest = ("/static/manifest.json" if not path.startswith("/tesla")
                    else "/tesla/static/manifest.json")
        assert f'<link rel="manifest" href="{manifest}">' in html, path


def test_all_pages_disable_double_tap_zoom_on_controls(auth):
    """触屏双击控件不再整页放大 (2026-09-13 用户踩坑)。

    iOS 忽略 user-scalable=no, 双击按钮/链接/菜单会被 Safari 当双击缩放;
    touch-action: manipulation 只去掉双击缩放, 平移和捏合缩放保留
    (地图手势区是 div, 不受影响)。全站统一, 登录页也要有。
    """
    for path in ALL_PAGES:
        html = auth.get(path).text
        assert "button, a, summary { touch-action: manipulation; }" in html, path


def test_all_pages_have_refresh_button(auth):
    """每页顶栏都有刷新按钮 (2026-09-13 用户反馈: 不是每个页面都有)。

    行程页首倡的胶囊刷新按钮 (busy 时图标旋转) 铺到全部业务页; 每页接
    自己的重载入口 —— 列表页重拉后回顶, 地图页不带首载遮罩 (refresh(false)),
    设置页拉完设置再补司机列表; 账号页 = 重拉用户与邀请。
    """
    # 页面路径 -> (该页 JS 文件, 点击后接的重载调用)
    wiring = {
        "/tesla/charging": ("index.js", "await refetch();"),
        "/tesla/stats": ("stats.js", "await refetch();"),
        "/tesla/chargemap": ("chargemap.js", "await refresh(false);"),
        "/tesla/map": ("map.js", "await refresh(false);"),
        "/tesla/trips": ("trips-list.js", "await refreshList();"),
        "/tesla/groups": ("groups.js", "await load();"),
        "/tesla/live": ("live.js", "await poll();"),
        "/tesla/settings": ("settings.js", "await loadSettings();"),
        "/tesla/changelog": ("/static/changelog-page.js", "await load();"),
        "/accounts": ("accounts.js", "await loadAll();"),
    }
    for path, (js_file, call) in wiring.items():
        html = auth.get(path).text
        assert '<button id="refresh-btn"' in html, path        # 按钮在顶栏
        assert "refresh-spin" in html, path                    # busy 旋转动画
        prefix = "/static" if path == "/accounts" else "/tesla/static"
        js_path = js_file if js_file.startswith("/") else f"{prefix}/{js_file}"
        js = auth.get(f"{js_path}?v=1").text
        assert '$("#refresh-btn").addEventListener' in js, path
        assert call in js, f"{path} 刷新按钮没接上 {call}"
        # 刷新按钮始终顶栏最右: 有时间菜单的页菜单吃 auto 边距, 按钮跟在后面;
        # 没有的页 (分组/驾驶/设置/日志/账号) 按钮自己吃 auto 边距
        if 'id="time-menu"' not in html:
            block = html[html.index("#refresh-btn {"):]
            assert "margin-left: auto" in block[:block.index("}")], path


def test_pages_remember_last_page(auth):
    """上次停留页: 业务页 head 挂 lastpage.js (冷启动在任何渲染前跳转,
    不闪启动页), 登录页/注册页不挂 (不是停留目标); 登录成功回上次页而非
    写死充电页。

    iOS 主屏图标每次都从添加时定格的 start_url 启动, 不记得停在哪页 ——
    localStorage 记 path+search, 冷启动 (sessionStorage 无标记) 且 standalone
    才 replace 过去; 行程弹层开合只动 URL 不重载, 靠 visibilitychange 补记。"""
    # lastpage 是 Tesla 应用内的概念: 登录/注册/账号管理都不挂
    home_layer = ("/login", "/register", "/accounts")
    for path in [p for p in ALL_PAGES if p not in home_layer]:
        html = auth.get(path).text
        tag = '<script src="/tesla/static/lastpage.js?v=1"></script>'
        assert tag in html, path
        assert html.index(tag) < html.index("<title>"), "要放 <title> 前 (首渲染前执行)"
    # /login 已登录会 302 进应用, 匿名视角看登录页本身 (不该挂 lastpage)
    assert "lastpage.js" not in TestClient(m.app).get("/login").text
    assert "lastpage.js" not in auth.get("/register").text
    # 登录成功去哪: 逻辑在 login.js —— 应用内的登录页回该应用 (或 next 参数
    # 带来的原地址, 只认本应用 scope), 账号层的回上次停留页 (白名单正则,
    # 站外/坏值回落充电页), 不再写死充电页
    login_html = auth.get("/static/login.js?v=1").text
    assert 'localStorage.getItem("mytesla-last-page")' in login_html
    assert ("/^\\/(tesla\\/(charging|stats|chargemap|map|trips|groups|live|settings"
            "|changelog))(\\?|$)/.test(last)") in login_html
    assert '? last : "/tesla/charging"' in login_html
    assert 'function pickNext()' in login_html
    assert 'const APP_TITLES = { "/tesla": "My Tesla" };' in login_html

    r = auth.get("/tesla/static/lastpage.js")
    assert r.status_code == 200
    js = r.text
    for frag in [
        '"/tesla/charging", "/tesla/stats", "/tesla/chargemap",',   # 白名单业务页
        '"/tesla/changelog"]',
        "PAGES.indexOf(path) === -1) return",                  # login/静态不记不跳
        "sessionStorage.getItem(LAUNCH)",                      # 冷启动判据 (会话标记)
        "catch (e) { return; }",                               # 隐私模式防回弹循环
        "navigator.standalone === true",                       # 只在主屏全屏 App 里跳
        'location.replace(saved)',                             # 目标过白名单才跳
        'if (document.hidden) record()',                       # 后台时补记 (弹层开合)
    ]:
        assert frag in js, f"lastpage.js 缺少 {frag}"


def test_webapp_manifests_scoped_per_app(auth):
    """Web App Manifest: 应用页一份 (圈 /tesla), 账号层一份 (登录页装的也是
    My Tesla, 直接进应用) —— 名字一致, scope 都圈 /tesla, 不圈 "/":
    同源多张 manifest 都圈 "/" 时, iOS 会把入口归给先装的那张
    (2026-09-14 用户实测跳错应用)。scope 收窄后会话过期 302 /login 越界的
    旧坑 (2026-09-12) 由应用 scope 内自带登录页解决 (见
    test_app_login_pages_in_scope)。图标各用各的, 加主屏互不干扰。"""
    for url, name, scope, start in (
            ("/tesla/static/manifest.json", "My Tesla", "/tesla", "/tesla/charging"),
            ("/static/manifest.json", "My Tesla", "/tesla", "/tesla/charging")):
        r = auth.get(url)
        assert r.status_code == 200, url
        manifest = r.json()
        assert manifest["name"] == name
        assert manifest["scope"] == scope
        assert manifest["display"] == "standalone"
        assert manifest["start_url"] == start
        assert any(i["sizes"] == "192x192" for i in manifest["icons"])
        assert any(i["sizes"] == "512x512" for i in manifest["icons"])
    for icon in ("/tesla/static/icon-192.png", "/tesla/static/icon-512.png",
                 "/static/icon-192.png", "/static/icon-512.png"):
        assert auth.get(icon).status_code == 200, icon


def test_login_ok_sets_cookie_attributes(client):
    r = client.post("/api/login",
                    json={"user": config.AUTH_USER, "password": config.AUTH_PASS})
    assert r.status_code == 200
    # 两个 set-cookie: 删旧 path=/tesla 残留 + 签新 path=/ (全站通用)
    cookies = "; ".join(c.lower() for c in r.headers.get_list("set-cookie"))
    assert "auth=" in cookies
    assert "path=/;" in cookies, cookies          # 新 cookie 挂全站 (非 /tesla 子路径)
    assert "httponly" in cookies
    assert "max-age=" in cookies                  # 90 天
    assert "samesite=lax" in cookies
    assert "path=/tesla" in cookies, cookies      # 旧 cookie 同帧删除


def test_login_wrong_password_returns_reason(client):
    r = client.post("/api/login",
                    json={"user": config.AUTH_USER, "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "账号或密码错误"


def test_login_rate_limited_after_5_failures(client):
    for _ in range(5):
        r = client.post("/api/login",
                        json={"user": config.AUTH_USER, "password": "nope"})
        assert r.status_code == 401
    r = client.post("/api/login",
                    json={"user": config.AUTH_USER, "password": "nope"})
    assert r.status_code == 429
    assert "尝试次数过多" in r.json()["detail"]
    # 锁定期间正确密码也进不去
    r = client.post("/api/login",
                    json={"user": config.AUTH_USER, "password": config.AUTH_PASS})
    assert r.status_code == 429


def test_token_roundtrip_tamper_and_expiry():
    uuid = "ab" * 16
    assert authentication.check_token(authentication.make_token(uuid)) == uuid
    assert authentication.check_token("") is None
    assert authentication.check_token("garbage") is None
    assert authentication.check_token("1.2.3") is None       # 三段但签名格式不对
    # 有效期但签名被篡改
    exp = str(int(time.time()) + 100)
    assert authentication.check_token(f"{exp}.{uuid}.deadbeef") is None
    # 已过期的合法签名
    exp = str(int(time.time()) - 1)
    secret = authentication._secret.value  # pylint: disable=protected-access
    sig = hmac.new(secret, f"{exp}.{uuid}".encode(), hashlib.sha256).hexdigest()
    assert authentication.check_token(f"{exp}.{uuid}.{sig}") is None


def test_legacy_two_part_token_maps_to_admin(usersdb, client):
    """单用户时代的两段式 cookie 仍被认 (按管理员处理, 升级不强制重登 Tesla 侧)。"""
    exp = str(int(time.time()) + 100)
    legacy = authentication._legacy_secret.value  # pylint: disable=protected-access
    sig = hmac.new(legacy, exp.encode(), hashlib.sha256).hexdigest()
    token = f"{exp}.{sig}"
    assert authentication.check_token(token) == authentication.LEGACY_ADMIN
    client.cookies.set("auth", token)
    assert client.get("/tesla/charging").status_code == 200
    me = client.get("/api/me").json()
    assert me["is_admin"] is True
    # 过期的旧 cookie 无效
    exp = str(int(time.time()) - 1)
    sig = hmac.new(legacy, exp.encode(), hashlib.sha256).hexdigest()
    assert authentication.check_token(f"{exp}.{sig}") is None


def test_logout_clears_only_this_device(client, usersdb):
    """登出只清本设备 cookie, 不再轮换会话密钥 (多用户下轮换会踢掉所有人)。"""
    other = account_store.create_user(usersdb, "二号账号", "password123")
    client.post("/api/login",
                json={"user": config.AUTH_USER, "password": config.AUTH_PASS})
    assert client.get("/tesla/charging").status_code == 200
    assert client.post("/api/logout").status_code == 200
    r = client.get("/tesla/charging", follow_redirects=False)
    assert r.status_code == 302
    # 应用页的登录跳转留在本应用 scope 内 (带原地址, 登录完回来)
    assert r.headers["location"] == "/tesla/login?next=%2Ftesla%2Fcharging"
    # 别人的会话不受影响
    client2 = TestClient(m.app)
    client2.cookies.set("auth", authentication.make_token(other.uuid))
    assert client2.get("/tesla/charging").status_code == 200


# ---------------------------------------------------------------- 中间件
def test_unauthed_pages_redirect_to_login(client):
    """页面未登录 302 登录页: 应用页跳自己 scope 内的登录页 (带上原地址,
    登录完回去), 账号层 (/, /accounts) 跳根路径 /login。"""
    from urllib.parse import quote
    for path, login in (("/", "/login"), ("/accounts", "/login"),
                        ("/tesla", "/tesla/login"),
                        ("/tesla/charging", "/tesla/login"),
                        ("/tesla/stats", "/tesla/login"),
                        ("/tesla/chargemap", "/tesla/login"),
                        ("/tesla/map", "/tesla/login"),
                        ("/tesla/changelog", "/tesla/login"),
                        ("/tesla/trips", "/tesla/login"),
                        ("/tesla/groups", "/tesla/login"),
                        ("/tesla/live", "/tesla/login"),
                        ("/tesla/settings", "/tesla/login")):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 302, path
        expected = login if path == login else login + "?next=" + quote(path, safe="")
        assert r.headers["location"] == expected, path


def test_app_login_pages_in_scope(client):
    """应用 scope 内的登录页: 未登录直接可开 (不再 302 到根路径 /login
    越出 scope), 内容就是账号层那张登录页; 已登录访问直接回应用主页
    (独立 client, 不带上面的未登录态)。"""
    r = client.get("/tesla/login", follow_redirects=False)
    assert r.status_code == 200
    assert 'src="/static/login.js?v=1"' in r.text
    authed = TestClient(m.app)
    assert authed.post("/api/login", json={"user": config.AUTH_USER,
                                           "password": config.AUTH_PASS}
                       ).status_code == 200
    r = authed.get("/tesla/login", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (302, "/tesla/charging")


def test_unauthed_apis_return_401_json(client):
    for path in ("/tesla/charging/api/summary", "/tesla/charging/api/sessions",
                 "/tesla/map/api/summary", "/tesla/map/api/tracks",
                 "/tesla/map/api/tracks/detail", "/tesla/map/api/config",
                 "/tesla/trips/api/sessions", "/tesla/trips/api/1/track",
                 "/tesla/live/api/status",
                 "/tesla/changelog/api/entries",
                 "/api/me", "/api/account/name", "/accounts/api/users"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json() == {"detail": "未登录"}


def test_public_paths_accessible_without_login(client):
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200    # 注册页公开
    for asset in ("/tesla/static/echarts.min.js", "/tesla/static/gcj02.js",
                  "/tesla/static/trackutil.js", "/tesla/static/favicon.svg",
                  "/static/login.js", "/static/register.js",
                  "/static/favicon.svg"):               # 账号层静态放行
        assert client.get(asset).status_code == 200, asset
    # Safari 不支持 SVG favicon, 需要 PNG 版 + iOS 主屏 apple-touch-icon
    for icon in ("/tesla/static/favicon-32.png",
                 "/tesla/static/apple-touch-icon.png",
                 "/static/favicon-32.png", "/static/apple-touch-icon.png"):
        assert client.get(icon).status_code == 200, icon


def test_apple_touch_icon_opaque_with_padding():
    """iOS 主屏图标: 不透明纯白底 (透明底被 iOS 合成纯黑) + Tesla 红 T 居中留边。
    旧版 T 铺满整个画布还带 Alpha → 添加到主屏幕后 logo 过大且黑底。"""
    path = Path(m.__file__).parent / "tesla" / "static" / "apple-touch-icon.png"
    with path.open("rb") as fh:
        d = fh.read()
    w, h = struct.unpack(">II", d[16:24])
    ctype = d[25]
    assert (w, h) == (180, 180)
    assert ctype in (2, 6), f"应是 RGB/RGBA, 实际类型 {ctype}"

    # 纯 Python 解码 (无 Pillow 依赖): 拼出 IDAT 后逆滤镜
    ch = {2: 3, 6: 4}[ctype]
    pos, idat = 8, b""
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos+8])
        if typ == b"IDAT":
            idat += d[pos+8:pos+8+ln]
        pos += 12 + ln
    rows = _unfilter_png(zlib.decompress(idat), w, ch)

    def px(x, y):
        return tuple(rows[y][x*ch:x*ch+3])

    if ch == 4:   # 带 Alpha 则必须全不透明 (透明像素在主屏上变黑)
        assert all(rows[y][x*4+3] == 255
                   for y in range(h) for x in range(0, w, 9))
    # 满出血白底, 四角纯白 (iOS 自己切圆角, 不能预切)
    for x, y in [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1)]:
        assert px(x, y) == (255, 255, 255)
    # T 标居中, 是 Tesla 红
    assert px(w//2, h//2) == (232, 33, 39)
    # 上下左右各留 ≥18px (10%) 白边: logo 不再铺满画布
    assert px(18, h//2) == (255, 255, 255)
    assert px(w-1-18, h//2) == (255, 255, 255)
    assert px(w//2, 18) == (255, 255, 255)
    assert px(w//2, h-1-18) == (255, 255, 255)


def test_moved_account_paths_redirect(client):
    """账号体系在根路径 (账号层), 旧地址 302/307 兼容 —— 已经发出去的
    邀请链接和手机上的老书签不能断: 页面 302, 接口 307 (保方法与请求体),
    查询串 (invite=) 原样带上。"""
    for old, new in (("/tesla/register?invite=tok", "/register?invite=tok"),
                     ("/tesla/accounts", "/accounts")):
        r = client.get(old, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (302, new), old
    for verb, old, new in (
            ("post", "/tesla/api/login", "/api/login"),
            ("post", "/tesla/api/logout", "/api/logout"),
            ("post", "/tesla/api/register", "/api/register"),
            ("get", "/tesla/api/invite-status?invite=tok",
             "/api/invite-status?invite=tok"),
            ("get", "/tesla/api/me", "/api/me"),
            ("post", "/tesla/api/account/name", "/api/account/name"),
            ("post", "/tesla/api/account/password", "/api/account/password"),
            ("get", "/tesla/accounts/api/users", "/accounts/api/users"),
            ("delete", "/tesla/accounts/api/invitations/tok",
             "/accounts/api/invitations/tok")):
        r = getattr(client, verb)(old, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (307, new), old
    # 老书签真的能用: 307 转过去登录成功
    r = client.post("/tesla/api/login", json={"user": config.AUTH_USER,
                                              "password": config.AUTH_PASS})
    assert r.status_code == 200
    # Tesla 业务接口没有平移到根路径 (不与账号接口混住)
    assert client.get("/api/summary").status_code == 404
    assert client.get("/api/charging").status_code == 404


# ---------------------------------------------------------------- 页面路由
def test_root_redirect_chain(auth):
    """登录后根路径 302 收口到充电页 (独立应用, 单一入口); /tesla 同样收口。"""
    r = auth.get("/", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (302, "/tesla/charging")
    r = auth.get("/tesla", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (302, "/tesla/charging")


def test_pages_served_after_login(auth):
    for path, marker in (("/tesla/charging", "My Tesla"),
                         ("/tesla/stats", "My Tesla"),
                         ("/tesla/chargemap", "My Tesla"),
                         ("/tesla/map", "My Tesla"),
                         ("/tesla/trips", "My Tesla"),
                         ("/register", "My Tesla"),
                         ("/tesla/changelog", "My Tesla"),
                         ("/tesla/groups", "My Tesla"),
                         ("/tesla/live", "My Tesla"),
                         ("/tesla/settings", "My Tesla"),
                         ("/accounts", "My Tesla")):          # 账号管理
        r = auth.get(path)
        assert r.status_code == 200, path
        assert marker in r.text, path


def test_static_js_must_revalidate(client):
    """JS 工具文件必须 no-cache 重新校验, 否则浏览器启发式缓存用旧版 (动画曾因此冻住)。"""
    r = client.get("/tesla/static/trackutil.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"


def test_cache_control_headers(auth):
    """API 响应禁止缓存 (配置更新要即时生效), 页面允许缓存但必须重新校验。"""
    assert auth.get("/tesla/map/api/config?_=1").headers["cache-control"] == "no-store"
    # 未登录的 401 API 响应同样禁缓存
    anon = TestClient(m.app)
    assert anon.get("/tesla/map/api/config").headers["cache-control"] == "no-store"
    for path in ("/tesla/charging", "/tesla/map", "/tesla/trips",
                 "/register", "/accounts"):
        assert auth.get(path).headers["cache-control"] == "no-cache", path
    assert auth.get("/static/login.js").headers["cache-control"] == "no-cache"


def test_all_pages_declare_png_and_touch_icons(auth):
    """每个页面都要有 PNG favicon + apple-touch-icon (Safari/iOS 看不见 SVG)。"""
    for path in ALL_PAGES:
        body = auth.get(path).text
        assert "favicon-32.png" in body, f"{path} 缺 PNG favicon"
        assert "apple-touch-icon.png" in body, f"{path} 缺 apple-touch-icon"


def test_brand_menu_pages_show_current_user():
    """每个带品牌下拉的页面都引 menu-user.js: 菜单顶部显示当前登录的账号。"""
    root = Path(__file__).parent.parent / "app"
    pages = [page for base in ("tesla/static", "static")
             for page in (root / base).glob("*.html")
             if "brand-menu" in page.read_text(encoding="utf-8")]
    assert len(pages) == 10             # 9 个应用页 + 账号管理页, 加页面也得跟上
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert "/static/menu-user.js" in html, f"{page.name} 缺 menu-user.js"
    # 小件本身: 问 /api/me, 样式自带, 找不到菜单静默不装 (名字走 DOM 不进 innerHTML)
    widget = (root / "static" / "menu-user.js").read_text(encoding="utf-8")
    for frag in ('"/api/me"', ".brand-menu .menu", "menu.prepend",
                 "is_admin", ".textContent = name"):
        assert frag in widget, f"menu-user.js 缺少 {frag}"


def test_all_pages_have_brand_menu(auth):
    """品牌即入口: My Tesla 是下拉按钮, 展开是应用页面 + 退出登录, 当前页高亮。"""
    for path, cur, slug in (("/tesla/charging", "充电记录", "charging"),
                            ("/tesla/map", "足迹地图", "map"),
                            ("/tesla/trips", "行程列表", "trips"),
                            ("/tesla/live", "当前驾驶", "live")):
        html = auth.get(path).text
        assert 'class="nav-menu brand-menu" id="brand-menu"' in html, path
        assert '<nav class="tabs">' not in html, path       # 平铺页签已删
        assert "<h1>My Tesla</h1>" not in html, path        # 旧标题位换成品牌下拉
        assert 'id="nav-menu"' not in html, path            # 旧页签菜单已删
        for href in ("/tesla/charging", "/tesla/map", "/tesla/trips",
                     "/tesla/live"):
            assert f'href="{href}"' in html, (path, href)
        assert f'<a class="on" href="/tesla/{slug}">{cur}</a>' in html, (path, cur)
        # 退出收进品牌菜单 (不再是顶栏独立按钮)
        assert 'class="logout-row" id="logout"' in html and "logout-btn" not in html, path
        assert "退出登录" in html, path
        # 记账/音乐已不随迁: 菜单里不再有它们的链接
        assert 'href="/bookkeeping"' not in html, path
        assert 'href="/music"' not in html, path


def test_login_page_redirects_authed_visitor(auth, client):
    """已登录的人开 /login: 服务端 302 直接进应用 (不再显示表单 ——
    旧版靠页面 JS 探测切换, 现在登录态判断在中间件)。"""
    r = auth.get("/login", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (302, "/tesla/charging")
    # 未登录看到的才是登录表单 (My Tesla 的门, 全站唯一)
    # (client 与 auth 是同一个对象且已登录, 匿名视角要新建)
    html = TestClient(m.app).get("/login").text
    assert "<title>登录 · My Tesla</title>" in html
    assert 'id="form"' in html
    assert 'id="eye"' in html          # 查看密码按钮 (图标并排显示 bug 修过)


def test_accounts_page_is_home_layer(auth):
    """账号管理页属账号层: 品牌菜单是 My Tesla (应用/账号管理, 当前项高亮),
    退出收在菜单里; 门厅与记账/音乐的入口已不随迁。"""
    html = auth.get("/accounts").text
    assert 'class="nav-menu brand-menu" id="brand-menu"' in html
    assert "<summary>My Tesla" in html
    assert '<a href="/tesla/charging">My Tesla</a>' in html
    assert '<a class="on" href="/accounts">账号管理</a>' in html
    assert 'class="logout-row" id="logout"' in html
    assert "门厅" not in html            # 门厅不随迁
    assert "My Money" not in html        # 记账应用不随迁


def test_tesla_pages_have_no_accounts_entry(auth):
    """My Tesla 的页面没有账号管理入口 (账号管理是独立的 /accounts 页,
    不属于任何一个业务页); 旧门厅的 home.js / me.js 也不随迁。"""
    for path in ("/tesla/charging", "/tesla/map", "/tesla/trips",
                 "/tesla/settings", "/tesla/live"):
        html = auth.get(path).text
        assert "账号管理" not in html, path
        assert "home.js" not in html, path
        assert "me.js" not in html, path
