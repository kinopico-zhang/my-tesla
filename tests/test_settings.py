"""设置页 API: TeslaMate 连接/高德 Key 存自有库 + 驾驶员管理。

引擎重建在测试里 monkeypatch 成记录器 (真重建会把注入的测试引擎换掉);
验证查询走当前工厂 —— 注入引擎是 SQLite, SELECT 1 必通。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database


@pytest.fixture()
def rebuild_recorder(monkeypatch):
    """记录 rebuild_engine 调用但不真换引擎 (保住测试注入的 SQLite)。"""
    calls: list[str] = []
    monkeypatch.setattr(database, "rebuild_engine", calls.append)
    return calls


def test_settings_get_defaults_from_env(auth, monkeypatch):
    """未保存过: 现值回落 env; 秘密不回显 (Key 打码, 密码只报在用)。"""
    monkeypatch.setenv("TMDB_HOST", "10.0.0.8")
    monkeypatch.setenv("TMDB_USER", "tmuser")
    monkeypatch.setenv("AMAP_KEY", "test-amap-key-123456")
    d = auth.get("/tesla/api/settings").json()
    assert d["tmdb"] == {"host": "10.0.0.8", "port": "5432", "user": "tmuser",
                         "name": "teslamate", "password_set": False}
    assert d["amap"]["key_masked"] == "test****3456"
    assert d["amap"]["security_code_set"] is False


def test_settings_save_amap_and_map_config_reflects(auth, monkeypatch):
    """高德 Key 存自有库, map config 端点即时反映 (改完即生效, 无需重启)。"""
    monkeypatch.delenv("AMAP_KEY", raising=False)
    monkeypatch.delenv("AMAP_SECURITY_CODE", raising=False)
    r = auth.post("/tesla/api/settings",
                  json={"amap_key": "abcd1234efgh5678", "amap_security_code": "9182ac3b"})
    assert r.status_code == 200
    assert r.json()["amap"]["key_masked"] == "abcd****5678"
    assert auth.get("/tesla/map/api/config").json() == {
        "amap_key": "abcd1234efgh5678", "security_code": "9182ac3b",
        "style": "amap://styles/dark"}
    # 留空 = 保持现值
    auth.post("/tesla/api/settings", json={"amap_key": "", "amap_security_code": ""})
    assert auth.get("/tesla/map/api/config").json()["amap_key"] == "abcd1234efgh5678"


def test_settings_save_map_style_and_validation(auth, monkeypatch):
    """地图样式: 预设/自定义 ID 存得下, map config 即时反映; 留空保持; 坏格式 400 不落库。

    默认幻影黑 (dark): 底色纯黑配深色 App。深色样式也有地名 —— 标注依赖
    样式数据异步加载, 首次打开过一两秒才出现 (页面自动补重渲染)。"""
    monkeypatch.delenv("AMAP_STYLE", raising=False)
    assert auth.get("/tesla/api/settings").json()["amap"]["style"] \
        == "amap://styles/dark"
    r = auth.post("/tesla/api/settings", json={"amap_style": "amap://styles/light"})
    assert r.json()["amap"]["style"] == "amap://styles/light"
    assert auth.get("/tesla/map/api/config").json()["style"] == "amap://styles/light"
    # 自定义样式 ID (个性化地图编辑器产出)
    custom = "amap://styles/d2b1f2e34c5a6789"
    r = auth.post("/tesla/api/settings", json={"amap_style": custom})
    assert r.json()["amap"]["style"] == custom
    assert auth.get("/tesla/map/api/config").json()["style"] == custom
    # 留空 = 保持现值
    r = auth.post("/tesla/api/settings", json={"amap_style": ""})
    assert r.json()["amap"]["style"] == custom
    # 坏格式 400 且不落库
    for bad in ("dark", "amap://styles/", "amap://styles/带空格",
                "amap://styles/a/b", "http://evil/x"):
        assert auth.post("/tesla/api/settings",
                         json={"amap_style": bad}).status_code == 400, bad
    assert auth.get("/tesla/api/settings").json()["amap"]["style"] == custom
    # env 回落: 设置行有值时 env 不生效 (清不掉, 但能被覆盖) —— 换回预设即可
    monkeypatch.setenv("AMAP_STYLE", "amap://styles/grey")
    r = auth.post("/tesla/api/settings", json={"amap_style": "amap://styles/normal"})
    assert r.json()["amap"]["style"] == "amap://styles/normal"


def test_settings_tmdb_rollback_also_reverts_style(auth, monkeypatch):
    """引擎验证失败整体回滚: 同请求里改的地图样式也要一起退回去。"""
    monkeypatch.setenv("TMDB_HOST", "10.0.0.1")
    auth.post("/tesla/api/settings",
              json={"tmdb_host": "10.0.0.1", "tmdb_user": "u", "tmdb_password": "p"})
    bad = sessionmaker(create_engine("sqlite:////nonexistent-dir/x.db"))
    monkeypatch.setattr(database, "session_factory", lambda: bad)
    r = auth.post("/tesla/api/settings",
                  json={"tmdb_host": "10.0.0.2", "amap_style": "amap://styles/grey"})
    assert r.status_code == 400
    assert auth.get("/tesla/api/settings").json()["amap"]["style"] \
        == "amap://styles/dark"   # 样式没被半路写入


def test_settings_save_tmdb_rebuilds_only_on_change(  # pylint: disable=redefined-outer-name
        auth, rebuild_recorder, monkeypatch):
    """TeslaMate 连接: 保存落库; URL 变了才换引擎, 原值重存不换 (幂等)。"""
    monkeypatch.setenv("TMDB_HOST", "10.0.0.1")   # 固定 host, 别走 docker 定位
    body = {"tmdb_host": "10.0.0.1", "tmdb_user": "u", "tmdb_password": "p",
            "tmdb_port": "5433", "tmdb_name": "n"}
    d = auth.post("/tesla/api/settings", json=body).json()["tmdb"]
    assert (d["host"], d["port"], d["user"], d["name"], d["password_set"]) == \
        ("10.0.0.1", "5433", "u", "n", True)
    assert rebuild_recorder == ["postgresql+psycopg://u:p@10.0.0.1:5433/n"]
    # 原值再存: URL 没变, 不换引擎
    auth.post("/tesla/api/settings", json=body)
    assert len(rebuild_recorder) == 1


def test_settings_tmdb_rollback_when_verify_fails(  # pylint: disable=redefined-outer-name
        auth, rebuild_recorder, monkeypatch):
    """新连接实测失败: 设置行回滚 + 引擎换回旧 URL + 400 (服务不断)。"""
    monkeypatch.setenv("TMDB_HOST", "10.0.0.1")
    auth.post("/tesla/api/settings",
              json={"tmdb_host": "10.0.0.1", "tmdb_user": "u", "tmdb_password": "p"})
    rebuild_recorder.clear()
    # 验证查询指向连不上的库 (目录不存在, SQLite 直接 OperationalError)
    bad = sessionmaker(create_engine("sqlite:////nonexistent-dir/x.db"))
    monkeypatch.setattr(database, "session_factory", lambda: bad)

    r = auth.post("/tesla/api/settings", json={"tmdb_host": "10.0.0.2"})
    assert r.status_code == 400 and "连不上" in r.json()["detail"]
    assert rebuild_recorder == [
        "postgresql+psycopg://u:p@10.0.0.2:5432/teslamate",   # 先换新
        "postgresql+psycopg://u:p@10.0.0.1:5432/teslamate"]    # 失败换回
    d = auth.get("/tesla/api/settings").json()["tmdb"]
    assert d["host"] == "10.0.0.1"   # 设置行已回滚


def test_drivers_crud_and_single_default(auth):
    """驾驶员: 添加/列表/改名/删除; 设默认互斥 (全库至多一个)。"""
    d1 = auth.post("/tesla/api/drivers", json={"name": "爸爸"}).json()
    d2 = auth.post("/tesla/api/drivers", json={"name": " 妈妈 "}).json()
    assert d2["name"] == "妈妈"                       # 名字 strip
    assert [x["name"] for x in auth.get("/tesla/api/drivers").json()] == ["爸爸", "妈妈"]

    assert auth.patch(f"/tesla/api/drivers/{d2['id']}",
                      json={"is_default": True}).json()["is_default"] is True
    flags = [x["is_default"] for x in auth.get("/tesla/api/drivers").json()]
    assert flags == [False, True]                     # 设新的清掉旧的

    assert auth.patch(f"/tesla/api/drivers/{d1['id']}",
                      json={"name": "老王"}).json()["name"] == "老王"
    assert auth.patch("/tesla/api/drivers/99",
                      json={"name": "x"}).status_code == 404

    assert auth.delete(f"/tesla/api/drivers/{d2['id']}").json() == {"ok": True}
    assert auth.get("/tesla/api/drivers").json() == [
        {"id": d1["id"], "name": "老王", "is_default": False}]
    assert auth.delete(f"/tesla/api/drivers/{d2['id']}").status_code == 404

    assert auth.post("/tesla/api/drivers", json={"name": "  "}).status_code == 400
    assert auth.post("/tesla/api/drivers", json={"name": "x" * 31}).status_code == 422


def test_settings_page_and_nav_entries(auth):
    """设置页挂全 (表单/驾驶员/轻提示); 三个页面品牌菜单都有设置入口。"""
    html = auth.get("/tesla/settings").text
    html += auth.get("/tesla/static/settings.js?v=1").text
    for frag in ['id="tm-host"', 'id="tm-save"', "保存并连接", 'id="amap-key"',
                 'id="drv-list"', "/tesla/api/settings", "/tesla/api/drivers",
                 'id="toast"', "设为默认", "留空 = 保持现值",
                 # 地图样式选择 (深色默认幻影黑配 App; 提示讲清地名是异步到的)
                 'id="amap-style"', 'value="amap://styles/dark"',
                 'value="amap://styles/darkblue"', '极夜蓝',
                 '幻影黑 (纯黑)</option>', '首次打开过一两秒才出现',
                 'id="amap-style-custom"', "amap_style:"]:
        assert frag in html, f"设置页缺少片段 {frag}"
    assert "无地名" not in html   # 深色样式有地名, 旧说法不许回潮
    # 顶栏与全站一致: 手机端下拉锚到全宽 header (header 非定位要补 relative)
    for frag in ["@media (max-width: 479px)", "header { position: relative; }",
                 ".nav-menu { position: static; }", ".nav-menu .menu { left: 12px; right: 12px; }"]:
        assert frag in html, f"设置页顶栏缺少片段 {frag}"
    for page in ("/tesla/charging", "/tesla/map", "/tesla/trips"):
        assert '<a href="/tesla/settings">软件设置</a>' in auth.get(page).text, page
