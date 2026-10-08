"""设置页 API: TeslaMate 连接/高德 Key 存自有库 + 驾驶员管理 + 两把 Key
的「测试」钮端点 (Web 服务 Key 打一次逆地理回真伪)。

引擎重建在测试里 monkeypatch 成记录器 (真重建会把注入的测试引擎换掉);
验证查询走当前工厂 —— 注入引擎是 SQLite, SELECT 1 必通。
"""
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.tesla import roads_amap
from tests.tesla_static_files import served_page


@pytest.fixture()
def rebuild_recorder(monkeypatch):
    """记录 rebuild_engine 调用但不真换引擎 (保住测试注入的 SQLite)。"""
    calls: list[str] = []
    monkeypatch.setattr(database, "rebuild_engine", calls.append)
    return calls


def test_settings_get_defaults_from_env(auth, monkeypatch):
    """未保存过: TeslaMate 现值回落 env; 高德 Key 只认设置页 (没配就是空)。"""
    monkeypatch.setenv("TMDB_HOST", "10.0.0.8")
    monkeypatch.setenv("TMDB_USER", "tmuser")
    d = auth.get("/tesla/api/settings").json()
    assert d["tmdb"] == {"host": "10.0.0.8", "port": "5432", "user": "tmuser",
                         "name": "teslamate", "password_set": False}
    # 高德 Key 只认设置页存库 (2026-10-08 收敛, 不再走 env): 没配就是空串;
    # 安全码也是头尾掩码回显 (2026-10-06, 未设空串, 不再是「在用」布尔)
    assert d["amap"]["key_masked"] == ""
    assert d["amap"]["security_code_masked"] == ""


def test_settings_save_amap_and_map_config_reflects(auth):
    """高德 Key 存自有库, map config 端点即时反映 (改完即生效, 无需重启)。"""
    r = auth.post("/tesla/api/settings",
                  json={"amap_key": "abcd1234efgh5678", "amap_security_code": "9182ac3b"})
    assert r.status_code == 200
    assert r.json()["amap"]["key_masked"] == "abcd****5678"
    assert r.json()["amap"]["security_code_masked"] == "****"   # 8 位不过头尾窗, 全掩
    assert auth.get("/tesla/map/api/config").json() == {
        "amap_key": "abcd1234efgh5678", "security_code": "9182ac3b"}
    # 留空 = 保持现值
    auth.post("/tesla/api/settings", json={"amap_key": "", "amap_security_code": ""})
    assert auth.get("/tesla/map/api/config").json()["amap_key"] == "abcd1234efgh5678"


def test_settings_map_provider_field_retired(auth, monkeypatch):
    """地图服务商/样式字段退役 (2026-09-25「只保留高德」/ 2026-10-05「样式
    选择去掉, 不允许用户选择」): 状态与配置端点都不再有 provider/style
    (样式固定幻影黑住前端适配层); 旧客户端再 POST map_provider / amap_style
    是无效字段, 不炸不落库 (pydantic 忽略), Key 保存照常。"""
    monkeypatch.setenv("MAP_PROVIDER", "osm")   # env 也不再看 (有也不生效)
    monkeypatch.setenv("AMAP_STYLE", "amap://styles/light")
    state = auth.get("/tesla/api/settings").json()["amap"]
    assert set(state) == {"key_masked", "security_code_masked",
                          "web_key_masked"}   # 3.3.3 起加轨迹拟合 Web 服务 Key;
                                              # 安全码 2026-10-06 起打码回显 (原「在用」布尔)
    cfg = auth.get("/tesla/map/api/config").json()
    assert set(cfg) == {"amap_key", "security_code"}
    r = auth.post("/tesla/api/settings",
                  json={"map_provider": "osm", "amap_style": "amap://styles/grey"})
    assert r.status_code == 200
    assert "provider" not in r.json()["amap"] and "style" not in r.json()["amap"]


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


def test_web_key_test_verdicts(auth, monkeypatch):
    """「测试」钮端点 (2026-10-06 用户点名「添加两个测试按钮」+ 同日追点
    「测试正常只显示正常就行了, 只有测试正常才能保存」): 测 POST 来的候选
    Web 服务 Key (空 = 测现值) —— 打一次逆地理回真伪, 通过 detail 就是
    toast 文案「正常」; 无效 Key (10001) / 网络不通算不过; 配额限流
    (10003 只发生在有效 Key 上) 报「有效但限流」。候选原样到高德 (mock
    客户端收到的就是它, strip 过)。"""
    seen: list[str] = []

    def fake_client(payload):
        def make(key, timeout=8.0):
            seen.append(key)
            return roads_amap.AmapClient(
                key, transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=payload)))
        return make

    monkeypatch.delenv("AMAP_WEB_KEY", raising=False)   # env 已不是通道, 双保险
    assert auth.post("/tesla/map/api/web-key-test").json() == \
        {"ok": False, "detail": "还没填 Web 服务 Key"}

    # 现值只认设置页存库 (2026-10-08 收敛): 保存后「测试」测它
    auth.post("/tesla/api/settings", json={"amap_web_key": "webkey-123"})
    monkeypatch.setattr("app.tesla.routers.map.AmapClient",
                        fake_client({"status": "1", "info": "OK",
                                     "infocode": "10000",
                                     "regeocode": {"pois": [], "roads": [],
                                                   "addressComponent":
                                                   {"district": "福田区"}}}))
    assert auth.post("/tesla/map/api/web-key-test").json() == \
        {"ok": True, "detail": "正常"}
    # 候选优先: 框里给了就测框里的 (原样到高德); 空 key / 空白 = 测现值
    auth.post("/tesla/map/api/web-key-test", json={"key": " candidate-xyz "})
    assert seen == ["webkey-123", "candidate-xyz"]
    auth.post("/tesla/map/api/web-key-test", json={"key": "  "})
    assert seen[-1] == "webkey-123"

    monkeypatch.setattr("app.tesla.routers.map.AmapClient",
                        fake_client({"status": "0", "info": "INVALID_USER_KEY",
                                     "infocode": "10001"}))
    r = auth.post("/tesla/map/api/web-key-test").json()
    assert r["ok"] is False and "10001" in r["detail"]

    monkeypatch.setattr("app.tesla.routers.map.AmapClient",
                        fake_client({"status": "0", "info": "DAILY_QUERY_OVER_LIMIT",
                                     "infocode": "10003"}))
    r = auth.post("/tesla/map/api/web-key-test").json()
    assert r["ok"] is True and "限流" in r["detail"]

    def boom(request):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr("app.tesla.routers.map.AmapClient",
                        lambda key, timeout=8.0: roads_amap.AmapClient(
                            key, transport=httpx.MockTransport(boom)))
    r = auth.post("/tesla/map/api/web-key-test").json()
    assert r["ok"] is False and "网络" in r["detail"]


def test_settings_views_and_entries(auth):
    """设置拆视图挂全 (账号设置/数据来源/地图设置/驾驶员, 表单原样搬壳;
    账号 2026-09-27 从数据来源页拆出独立页, 用户点名排设置组前两页);
    3.0 的入口是抽屉设置组 (test_shell_wiring 钉住); 账号 2026-10-05 二改:
    账号名行内编辑 + 修改密码 + 登出分三张卡 (弹层退役, test_shell_views 钉住)。"""
    html = served_page(auth, "/tesla")
    for frag in ['id="view-settings-account"', '<h2>账号设置</h2>',
                 'id="view-settings-db"', 'id="view-settings-map"',
                 'id="view-settings-drivers"',
                 'id="tm-host"', 'id="tm-save"', "保存并连接", 'id="amap-key"',
                 'id="drv-list"', "/tesla/api/settings", "/tesla/api/drivers",
                 'id="toast"', "设为默认",
                 # 高德两把 Key 各配一个「获取方式」折叠块 (2026-10-06 用户
                 # 点名「默认折叠, 展开后 markdown 条目渲染, 超链接可以点开」)
                 # + 已填的在框里显掩码 (掩码住 placeholder 不入提交值)
                 '<details class="howto">', "<summary>Key 的获取方式</summary>",
                 'id="amap-howto"', 'id="amap-web-howto"',
                 # 驾驶员页 10-04 左滑三钮 (v5): 常显钮退役, 改名是行内编辑
                 'class="swipe-edit set-def">设为默认', 'class="swipe-edit ren">改名',
                 'class="drv-input"', "window.confirm(`删除驾驶员",
                 'bindSwipeDelete($("#drv-list")']:
        assert frag in html, f"设置视图缺少片段 {frag}"
    # TeslaMate 卡布局 (2026-10-07 用户点名「端口和ip放在一行, 数据库名,
    # 账号密码分别占一行」): 主机+端口同住唯一一行 .row2, 数据库名/用户/
    # 密码三框各整行 (不在 row2 里)
    db_card = html[html.index('id="view-settings-db"'):html.index('id="tm-save"')]
    assert db_card.count('class="row2"') == 1
    r0 = db_card.index('<div class="row2">')
    row2 = db_card[r0:db_card.index("</div>", r0)]   # 从 row2 开标签起找它的闭合
    assert 'id="tm-host"' in row2 and 'id="tm-port"' in row2, "主机和端口该在同一行"
    for alone in ('id="tm-name"', 'id="tm-user"', 'id="tm-pass"'):
        assert alone not in row2, f"{alone} 该自己占一行"
    # 测试钮 (2026-10-06 用户点名「添加两个测试按钮」+ 同日追点「测试正常
    # 只显示正常就行了, 只有测试正常才能保存」): 两张 Key 卡各一枚, 与保存
    # 主钮 .btn-row 并排 (次钮 .plain 描边蓝字)
    for frag in ('id="amap-test"', 'id="amap-web-test"',
                 'class="plain" id="amap-test">测试</button>',
                 'class="plain" id="amap-web-test">测试</button>'):
        assert frag in html, f"地图设置缺测试钮 {frag}"
    sm = auth.get("/tesla/static/js/view/settings-map.js").text
    for frag in ('$("#amap-test").addEventListener',
                 "mapLib.probeKey(",              # Web端候选: 走适配层探针
                                                     # (独立 iframe 建小图, 探针本体钉在 test_map_adapter)
                 '$("#amap-web-test").addEventListener',
                 'sendJSON("/tesla/map/api/web-key-test"',   # Web服务候选 POST 给服务端
                 'JSON.stringify({ key:',
                 "toast(verdict)",               # 通过转述探针回话
                                                     # (正常 / Key 有效但限流), 不再写死「正常」
                 '$("#amap-save").disabled',      # 保存闸: 测试通过才解锁
                 '$("#amap-web-save").disabled',
                 'addEventListener("input"'):     # 输入一变作废重测
        assert frag in sm, f"地图设置脚本缺 {frag}"
    # 折叠块内容 (markdown 条目) 与渲染器: 条目在 JS 里记, [字](网址) 转成
    # 新标签页链接; 安全码掩码回显住 placeholder (2026-10-06 用户点名
    # 「默认折叠/markdown 条目/链接可点开」「安全码也是显示头尾」)
    for frag in ("HOWTO_JS", "HOWTO_WEB", "function mdItems(",
                 'target="_blank"', "https://console.amap.com",
                 "服务平台选「Web端 (JS API)」", "服务平台选「Web服务」",
                 "两种类型, 不能混用",
                 'security_code_masked || "未设置"',
                 'web_key_masked || "未设置"', "setMapGate("):
        assert frag in sm, f"获取方式折叠块/掩码回显缺 {frag}"
    # 通行一次性 (2026-10-06 用户点名「修改后, 保存按钮灰色, 要测试通过
    # 才能保存」): 存完回灰再存要重测; 「留空保持」文案同日退役
    assert "保存消费掉通行" in sm
    assert "留空保持" not in sm
    # v12 的「测已保存值/未保存先拦」旧路退役 (与保存闸死循环, 不许回潮)
    assert "先保存再测" not in sm
    css = auth.get("/tesla/static/css/tesla-settings.css").text
    for frag in (".btn-row {", ".plain {", ".howto summary {", ".howto .md a {"):
        assert frag in css, f"设置样式缺 {frag}"
    # 服务商切换/地图样式选择/长说明已退役 (2026-09-25/10-05, 用户点名):
    # 下拉/收组逻辑/样式保存不许回潮; 样式固定幻影黑住适配层
    for gone in ('id="map-provider"', "map_provider:", "syncProviderRows",
                 'id="amap-rows"', '<option value="osm">',
                 'id="amap-style"', "amap_style:", "styles/darkblue",
                 'id="amap-style-custom"', 'id="amap-now"', 'id="amap-web-now"',
                 "首次打开过一两秒才出现", "留空 = 保持现值",
                 "留空保持现值"):   # 「留空保持」文案 2026-10-06 用户点名退役
        assert gone not in html, f"退役的片段回潮: {gone}"
    assert "无地名" not in html   # 深色样式有地名, 旧说法不许回潮
