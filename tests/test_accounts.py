"""账号系统测试: 邀请注册 / 多用户 / 自助改名改密 / 管理员边界。

uuid 由后端生成且全程不出接口 (用户不可见也不变); 普通账号有全部业务
功能但没有账号管理权限。
"""
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app import account_store, config
import app.main as m


def _register(usersdb, name="二号账号", password="password123"):
    """凭邀请注册一个普通账号, 返回 (该账号登录态的 client, 邀请令牌)。"""
    invitation = account_store.create_invitation(usersdb, 7)
    client = TestClient(m.app)
    r = client.post("/api/register",
                    json={"invite": invitation.token, "name": name,
                          "password": password})
    assert r.status_code == 200, r.text
    return client, invitation.token


def _admin(client):
    """管理员登录态的 client (env 账密 = 种入的管理员)。"""
    r = client.post("/api/login",
                    json={"user": config.AUTH_USER, "password": config.AUTH_PASS})
    assert r.status_code == 200
    return client


# ---------------------------------------------------------------- 管理员种子
def test_ensure_admin_seeds_once(usersdb):
    """isolate 已种过管理员: 再调 ensure_admin 不重复种 (只种一次)。"""
    account_store.ensure_admin(usersdb, "管理员", "password123")
    users = account_store.list_users(usersdb)
    assert len(users) == 1                    # 没有第二个
    assert users[0].is_admin is True
    assert users[0].name == config.AUTH_USER  # 保持 env 种入的名字
    assert len(users[0].uuid) == 32           # uuid4().hex


# ---------------------------------------------------------------- 注册流程
def test_register_full_lifecycle(client, usersdb):
    invitation = account_store.create_invitation(usersdb, 1)
    # 进页先查状态: 可用
    r = client.get("/api/invite-status",
                   params={"invite": invitation.token})
    assert r.status_code == 200
    # 注册成功 = 自动登录 (新 cookie 落在 path=/)
    r = client.post("/api/register",
                    json={"invite": invitation.token, "name": "家里那位",
                          "password": "password123"})
    assert r.status_code == 200
    me = client.get("/api/me").json()
    assert me == {"name": "家里那位", "is_admin": False}   # 不含 uuid
    # 邀请一次一用: 状态与再注册都不行
    assert client.get("/api/invite-status",
                      params={"invite": invitation.token}).status_code == 400
    r = client.post("/api/register",
                    json={"invite": invitation.token, "name": "第三位",
                          "password": "password123"})
    assert r.status_code == 400
    assert "已被使用" in r.json()["detail"]


def test_register_validates_name_password_invite(client, usersdb):
    invitation = account_store.create_invitation(usersdb, 7)
    for name, password in (("", "password123"),       # 名字太短
                           ("a", "password123"),      # 名字 1 字符
                           ("带 空格", "password123"),  # 内部空白
                           ("名字", "12345")):        # 密码太短
        r = client.post("/api/register",
                        json={"invite": invitation.token, "name": name,
                              "password": password})
        assert r.status_code == 400, name
    # 名字重名 (管理员已种)
    r = client.post("/api/register",
                    json={"invite": invitation.token, "name": config.AUTH_USER,
                          "password": "password123"})
    assert r.status_code == 400
    assert "已被占用" in r.json()["detail"]
    # 环令牌
    r = client.post("/api/register",
                    json={"invite": "no-such-token", "name": "家里那位",
                          "password": "password123"})
    assert r.status_code == 400
    assert "无效" in r.json()["detail"]


def test_invitation_states(usersdb, client):
    _admin(client)
    # 签发档位: 只有 1/7/30
    assert client.post("/accounts/api/invitations",
                       json={"days": 5}).status_code == 400
    made = client.post("/accounts/api/invitations",
                       json={"days": 30}).json()
    assert made["token"] and made["expires_at"]
    # 撤销后不可用
    assert client.delete(f"/accounts/api/invitations/{made['token']}"
                         ).status_code == 200
    r = client.get("/api/invite-status", params={"invite": made["token"]})
    assert r.status_code == 400
    assert "撤销" in r.json()["detail"]
    # 已撤销的不能再撤销
    assert client.delete(f"/accounts/api/invitations/{made['token']}"
                         ).status_code == 400
    # 过期不可用 (直接把库里的截止时间改到过去)
    invitation = account_store.create_invitation(usersdb, 1)
    invitation.expires_at = datetime.utcnow() - timedelta(seconds=1)
    usersdb.commit()
    r = client.get("/api/invite-status", params={"invite": invitation.token})
    assert r.status_code == 400
    assert "过期" in r.json()["detail"]
    # 列表带全部状态字段 (前端现算有效/已注册/过期/已撤销)
    items = client.get("/accounts/api/invitations").json()
    assert {i["token"] for i in items} >= {made["token"], invitation.token}
    fields = {"token", "created_at", "expires_at", "used_at", "revoked"}
    assert fields <= set(items[0])


# ---------------------------------------------------------------- 管理员边界
def test_accounts_admin_only(usersdb):
    other, _ = _register(usersdb)
    # 普通账号: 列表/签发/撤销全部 403
    assert other.get("/accounts/api/users").status_code == 403
    assert other.post("/accounts/api/invitations",
                      json={"days": 7}).status_code == 403
    assert other.get("/accounts/api/invitations").status_code == 403
    assert other.delete("/accounts/api/invitations/x").status_code == 403
    # 未登录: 401
    anon = TestClient(m.app)
    assert anon.get("/accounts/api/users").status_code == 401


def test_accounts_user_list_no_uuid_leak(usersdb, client):
    _admin(client)
    _register(usersdb, "家里那位")
    users = client.get("/accounts/api/users").json()
    assert len(users) == 2
    assert users[0]["is_admin"] is True                    # 管理员在前
    assert users[1] == {"name": "家里那位", "is_admin": False,
                        "created_at": users[1]["created_at"]}
    assert "uuid" not in users[1] and "uuid" not in users[0]


# ---------------------------------------------------------------- 自助账号
def test_rename_keeps_session_and_uuid(usersdb):
    other, _ = _register(usersdb)
    before = other.get("/api/me").json()
    assert before["name"] == "二号账号"
    r = other.post("/api/account/name", json={"name": "新名字"})
    assert r.status_code == 200
    assert r.json() == {"name": "新名字", "is_admin": False}
    # 会话不掉线 (uuid 没变)
    assert other.get("/api/me").json()["name"] == "新名字"
    assert other.get("/tesla/charging").status_code == 200
    # 改成管理员的名字 → 占用
    r = other.post("/api/account/name", json={"name": config.AUTH_USER})
    assert r.status_code == 400
    # 改回自己的名字 → 允许 (no-op)
    assert other.post("/api/account/name",
                      json={"name": "新名字"}).status_code == 200


def test_password_change(usersdb):
    other, _ = _register(usersdb, "家里那位", "password123")
    # 旧密码错 → 400
    r = other.post("/api/account/password",
                   json={"old_password": "wrong-old", "new_password": "newpass456"})
    assert r.status_code == 400
    assert "旧密码" in r.json()["detail"]
    # 改成功: 会话不掉线, 新密码能登录, 旧密码不行
    r = other.post("/api/account/password",
                   json={"old_password": "password123",
                         "new_password": "newpass456"})
    assert r.status_code == 200
    assert other.get("/api/me").status_code == 200
    fresh = TestClient(m.app)
    assert fresh.post("/api/login",
                      json={"user": "家里那位", "password": "newpass456"}
                      ).status_code == 200
    assert fresh.post("/api/login",
                      json={"user": "家里那位", "password": "password123"}
                      ).status_code == 401


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401


# ---------------------------------------------------------------- 邀请链接分发
def test_invite_copy_ios_safari_fallbacks():
    """iOS Safari 在 HTTP 站点没有异步剪贴板 API (isSecureContext=false),
    execCommand 退化路必须先 focus 再选中再同步拷贝 (2026-09-13 用户实测
    复制落空: 旧版对 textarea 用 Range 选 —— 它没有 DOM 子节点选不中,
    还没 focus、元素移出视口); 拷贝整条路被拒时拉系统分享面板兜底,
    链接一定送得出去。"""
    js = (Path(m.__file__).parent / "static" / "accounts.js").read_text(encoding="utf-8")
    assert "navigator.clipboard && window.isSecureContext" in js
    assert "ta.focus({ preventScroll: true })" in js   # iOS: 聚焦后选区才建立
    assert "ta.setSelectionRange(0, text.length)" in js
    assert "ta.readOnly = true" in js                  # 只读聚焦不弹键盘
    assert "navigator.share" in js                     # 兜底: 分享面板 (含「拷贝」)
    # 不许再犯: textarea 没有 DOM 子节点, Range 选不中它
    assert "selectNodeContents(ta)" not in js


def test_admin_badge_outside_name_cell():
    """管理员徽章是 .usr-row 的 flex 子元素, 不能在 .usr-name 里 —— 那格有
    overflow:hidden (长名省略号), inline 徽章的下半 (含下边框) 会伸出行盒
    被裁掉 (2026-09-13 用户抓到「椭圆框只有上半」)。"""
    base = Path(m.__file__).parent / "static"
    js = (base / "accounts.js").read_text(encoding="utf-8")
    assert '<div class="usr-name">${esc(u.name)}</div>' in js   # 名字格先闭合
    assert 'usr-badge">管理员</span>` : "")' in js              # 徽章是行级片段
    assert "${esc(u.name)}<span" not in js                      # 不许塞回名字格
    html = (base / "accounts.html").read_text(encoding="utf-8")
    assert "flex: none; font-size: 10.5px; line-height: 1" in html  # 自立行高
