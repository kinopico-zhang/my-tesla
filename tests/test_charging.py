"""充电记录 API 测试 (SQLite 种子数据跑真实 SQL, 不依赖真实 TeslaMate 库)。"""
from datetime import datetime

from app.tesla import repository
from app.tesla.models import Address, ChargingProcess, Geofence
from tests.conftest import (seed_addresses, seed_car, seed_charge,
                            seed_charging)


# 充电记录/统计页共用格式化拆去了 format.js: 页面片段断言把先加载的
# format.js 一并拼进来查子串
def _page_scripts(auth, *names):
    return "".join(auth.get(f"/tesla/static/{name}").text for name in names)


# ---------------------------------------------------------------- 转换语义 (repository)
def test_session_fields_and_price(db):
    seed_addresses(db)
    seed_charge(db, 1)
    seed_charging(db)          # 默认: 45/48kWh, 25.5 元, 无 geofence
    row = repository.list_charging_sessions(db, repository.SessionFilter(
        None, "all", None, "date_desc", 0, 50))[1][0]
    assert row.id == 1
    assert row.start == "2026-09-07 23:50"      # UTC 15:50 → 北京时间
    assert row.date == "2026-09-07"
    assert row.location == "华为立体车库"         # 无 geofence 时退回 address
    assert row.price_per_kwh == round(25.5 / 48.0, 3)
    assert row.is_fast is True                   # charges 有 90kW 采样
    assert row.outside_temp == 28.5
    assert row.city == "深圳市"


def test_session_geofence_preferred(db):
    db.add(Geofence(id=7, name="公司"))
    db.commit()
    seed_addresses(db)
    seed_charging(db, geofence_id=7)
    seed_charge(db, 1)
    item = repository.list_charging_sessions(db, repository.SessionFilter(
        None, "all", None, "date_desc", 0, 50))[1][0]
    assert item.location == "公司"


def test_session_without_cost(db):
    seed_addresses(db)
    seed_charging(db, cost=None)
    item = repository.list_charging_sessions(db, repository.SessionFilter(
        None, "all", None, "date_desc", 0, 50))[1][0]
    assert item.cost is None
    assert item.price_per_kwh is None


def test_parse_date_range_boundaries():
    rng = repository.parse_date_range("2026-01-01", "2026-01-31")
    assert rng is not None
    # 北京时间 1/1 00:00 = UTC 前一天 16:00; to 的边界是次日零点 (左闭右开)
    assert rng.start == datetime(2025, 12, 31, 16, 0)
    assert rng.end == datetime(2026, 1, 31, 16, 0)
    assert repository.parse_date_range(None, None) is None
    try:
        repository.parse_date_range("2026-13-99", None)
        raise AssertionError("非法日期应抛 ValueError")
    except ValueError as exc:
        assert "日期格式错误" in str(exc)


# ---------------------------------------------------------------- 接口
def test_car_endpoint(auth, db):
    seed_car(db)
    r = auth.get("/tesla/charging/api/car")
    assert r.status_code == 200
    assert r.json() == [{"id": 1, "name": "臭哈子", "model": "Y",
                         "trim_badging": "50", "vin": "LRW1"}]


def test_summary_endpoint(auth, db):
    seed_addresses(db)
    # 快充 45/48kWh 25.5 元 + 慢充 (无 charges 采样, is_fast=False)
    seed_charging(db)
    seed_charge(db, 1)
    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 10, 0),
                  end_date=datetime(2026, 9, 8, 12, 0),
                  charge_energy_added=10.0, charge_energy_used=11.0,
                  duration_min=120, cost=None, start_battery_level=50,
                  end_battery_level=70, start_rated_range_km=200.0,
                  end_rated_range_km=280.0)
    d = auth.get("/tesla/charging/api/summary").json()
    assert d["sessions"] == 2
    assert d["fast_sessions"] == 1
    assert d["energy_added"] == 55.0
    assert d["energy_used"] == 59.0
    assert d["cost"] == 25.5
    assert d["price_per_kwh"] == round(25.5 / 59.0, 3)
    assert d["duration_min"] == 552
    assert d["soc_gain"] == 80
    assert d["range_gain"] == round((330 - 120) + (280 - 200), 1)
    assert d["first_date"] == "2026-09-07"
    assert d["last_date"] == "2026-09-08"


def test_summary_respects_date_range(auth, db):
    seed_addresses(db)
    seed_charging(db)          # 09-07
    seed_charging(db, id=2, start_date=datetime(2026, 8, 1, 1, 0),
                  end_date=datetime(2026, 8, 1, 3, 0))
    d = auth.get("/tesla/charging/api/summary",
                 params={"from": "2026-09-01"}).json()
    assert d["sessions"] == 1
    assert d["first_date"] == "2026-09-07"


def test_sessions_list(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332)
    d = auth.get("/tesla/charging/api/sessions?limit=1").json()
    assert d["total"] == 1
    assert len(d["items"]) == 1
    assert d["items"][0]["id"] == 332


def test_sessions_rejects_unknown_sort(auth):
    r = auth.get("/tesla/charging/api/sessions?sort=hack")
    assert r.status_code == 400
    assert "不支持的排序" in r.json()["detail"]


def test_sessions_sort_orders_with_nulls_last(auth, db):
    """排序键齐全 + None 值排最后 (等价 Postgres NULLS LAST)。"""
    seed_addresses(db)
    # 1: 09-08 (最新) 30 元 55kWh 120 分; 2: 09-07 10 元 28kWh 150 分;
    # 3: 09-06 各字段全空
    seed_charging(db, id=1, cost=30.0, charge_energy_used=55.0,
                  duration_min=120, start_date=datetime(2026, 9, 8, 15, 50),
                  end_date=datetime(2026, 9, 8, 20, 0))
    seed_charging(db, id=2, cost=10.0, charge_energy_used=28.0, duration_min=150)
    seed_charging(db, id=3, cost=None, charge_energy_used=None,
                  duration_min=None, start_date=datetime(2026, 9, 6, 15, 50))
    base = "/tesla/charging/api/sessions?limit=50"

    def ids(qs):
        return [i["id"] for i in auth.get(f"{base}{qs}").json()["items"]]

    assert ids("&sort=date_desc") == [1, 2, 3]
    assert ids("&sort=date_asc") == [3, 2, 1]
    assert ids("&sort=cost_desc") == [1, 2, 3]     # None 排最后
    assert ids("&sort=cost_asc") == [2, 1, 3]
    assert ids("&sort=energy_desc") == [1, 2, 3]
    assert ids("&sort=energy_asc") == [2, 1, 3]
    assert ids("&sort=duration_desc") == [2, 1, 3]


def test_sessions_type_filter(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1)                      # 快充 (90kW 采样)
    seed_charge(db, 1, charger_power=90.0, fast_charger_present=True)
    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 10, 0))
    seed_charge(db, 2, charger_power=8.0, fast_charger_present=False,
                date=datetime(2026, 9, 8, 10, 5))
    assert auth.get("/tesla/charging/api/sessions?type=fast"
                    ).json()["total"] == 1
    assert auth.get("/tesla/charging/api/sessions?type=slow"
                    ).json()["total"] == 1
    assert auth.get("/tesla/charging/api/sessions"
                    ).json()["total"] == 2


def test_sessions_cost_filter(auth, db):
    """费用筛选: 已记录 / 未记录 (费用记 0 也算已记录); 非法值 400。"""
    seed_addresses(db)
    seed_charging(db, id=1, cost=25.5)                       # 记了费用
    seed_charging(db, id=2, cost=0.0,                        # 记了 0 元也算已记录
                  start_date=datetime(2026, 9, 8, 10, 0))
    seed_charging(db, id=3, cost=None,                       # 没记
                  start_date=datetime(2026, 9, 9, 10, 0))
    base = "/tesla/charging/api/sessions"
    assert auth.get(base, params={"cost": "recorded"}).json()["total"] == 2
    assert auth.get(base, params={"cost": "missing"}).json()["total"] == 1
    assert auth.get(base).json()["total"] == 3               # 不带 = 全部
    # 前端默认就发 cost=all (首屏), 必须当"全部"收下 —— 曾因不认 all 首屏 400
    assert auth.get(base, params={"cost": "all"}).json()["total"] == 3
    r = auth.get(base, params={"cost": "hack"})
    assert r.status_code == 400 and r.json()["detail"] == "不支持的费用筛选"


def test_sessions_search_by_address(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1)
    seed_charging(db, id=2, address_id=2,            # 东莞
                  start_date=datetime(2026, 9, 8, 10, 0))
    base = "/tesla/charging/api/sessions"
    assert auth.get(base, params={"q": "龙岗"}).json()["total"] == 1
    assert auth.get(base, params={"q": "东莞"}).json()["total"] == 1
    assert auth.get(base, params={"q": "不存在的地方"}).json()["total"] == 0


def test_sessions_pagination(auth, db):
    seed_addresses(db)
    for i in range(5):
        seed_charging(db, id=i + 1,
                      start_date=datetime(2026, 9, 7 + i, 15, 50))
    base = "/tesla/charging/api/sessions?sort=date_asc"
    d1 = auth.get(f"{base}&offset=0&limit=2").json()
    assert d1["total"] == 5 and [i["id"] for i in d1["items"]] == [1, 2]
    d2 = auth.get(f"{base}&offset=2&limit=2").json()
    assert [i["id"] for i in d2["items"]] == [3, 4]
    assert auth.get(f"{base}&offset=4&limit=2").json()["items"][0]["id"] == 5
    assert auth.get(f"{base}&offset=99&limit=2").json()["items"] == []


def test_session_detail(auth, db):
    seed_addresses(db)
    seed_charging(db)
    seed_charge(db, 1, date=datetime(2026, 9, 7, 16, 0),
                fast_charger_brand="<invalid>", fast_charger_type="Tesla")
    seed_charge(db, 1, id=None, date=datetime(2026, 9, 7, 16, 10),
                battery_level=30, charger_power=80.0,
                charger_actual_current=200.0, charge_energy_added=10.0,
                conn_charge_cable=None, fast_charger_brand=None,
                fast_charger_type=None)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["curve"]["minutes"] == [10.0, 20.0]    # 距 start (15:50) 的分钟数
    assert d["curve"]["soc"] == [20, 30]
    assert d["curve"]["kw"] == [90.0, 80.0]
    assert d["cable"] == "CCS"
    assert d["charger_brand"] is None               # <invalid> 已过滤
    assert d["charger_type"] == "Tesla"
    assert d["start_rated_range"] == 120.0
    assert d["end_rated_range"] == 330.0


def test_session_detail_nav_coords(auth, db):
    """详情带充电站坐标 (WGS-84) —— 前端导航换算的原料; 没坐标的地址给 None。"""
    db.add(Address(id=1, name="华为立体车库", city="深圳市",
                   display_name="深圳市华为立体车库",
                   latitude=22.55, longitude=114.05))
    db.commit()
    seed_charging(db)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["lat"] == 22.55 and d["lng"] == 114.05


def test_session_detail_no_coords(auth, db):
    """没反向地理编码过的地址: 坐标字段是 None (前端不渲染导航按钮)。"""
    seed_addresses(db)                     # 默认地址没有坐标
    seed_charging(db)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["lat"] is None and d["lng"] is None


def test_charging_detail_nav_button(auth):
    """详情「导航到充电站」: 先弹选单让用户挑地图 App, 点一个只拉一个。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    for frag in [
        'id="nav-go"', "🧭 导航到充电站",
        'id="nav-bd"', 'id="nav-apps"', 'id="nav-cancel"',     # 选单
        'data-app="amap"', 'data-app="baidu"',
        'data-app="tencent"', 'data-app="apple"',
        "openNavChooser",                     # 点按钮先弹选单
        # 没装的地图长按隐藏 (localStorage 记住), ＋ 胶囊恢复 —— 网页枚举不了装了哪些 App
        "navHiddenApps", "function renderNavApps()", "data-restore",
        "长按可隐藏没装的地图", "长按隐藏后的 click 吞掉",
        "function navAppUrl(",                # 一个 App 一个 URL
        "GCJ02.wgs84ToGcj02",                 # WGS-84 → GCJ-02, 不转偏几百米
        "iosamap://navi", "androidamap://navi",    # 高德 (iOS / 安卓 scheme)
        "baidumap", "://map/direction", "coord_type=gcj02",   # 百度 (iOS/安卓 scheme 前缀不同)
        "qqmap://map/routeplan", "fromcoord=CurrentLocation",   # 腾讯
        "maps.apple.com/?daddr",                   # 苹果地图
    ]:
        assert frag in html, f"充电详情导航缺少 {frag}"
    # 不自动探测连环拉起: iOS 拉 scheme 前先弹「在 xx 中打开」确认框,
    # 确认前页面不切后台, 探测窗口一过就把装了的 App 连环拉起 (用户实测)
    js = _page_scripts(auth, "format.js", "index.js")
    for gone in ["NAV_PROBE_MS", "visibilitychange", "uri.amap.com/navigation"]:
        assert gone not in js, f"自动探测链残留: {gone}"
    # 坐标换算库要先于页面脚本加载
    page = auth.get("/tesla/charging").text
    assert page.index("gcj02.js") < page.index("index.js")


def test_session_detail_hides_national_standard_tags(auth, db):
    """国标取值 (线缆 GB_DC / 类型 Gb, 国内满屏都是) 不进详情 —— 用户点名撤掉。

    品牌 Tesla 不受影响; 非国标取值 (CCS / v3) 照常展示。
    """
    seed_addresses(db)
    seed_charging(db)
    seed_charge(db, 1, conn_charge_cable="GB_DC",
                fast_charger_brand="Tesla", fast_charger_type="Gb")
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["cable"] is None and d["charger_type"] is None
    assert d["charger_brand"] == "Tesla"       # 国标过滤不殃及品牌


def test_session_detail_404(auth):
    assert auth.get("/tesla/charging/api/sessions/99999").status_code == 404


def test_monthly_endpoint(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1, cost=150.0, charge_energy_used=300.0,
                  duration_min=60)
    seed_charging(db, id=2, start_date=datetime(2026, 8, 1, 2, 0),
                  end_date=datetime(2026, 8, 1, 4, 0), cost=None,
                  charge_energy_used=None)
    d = auth.get("/tesla/charging/api/monthly").json()
    assert d == [
        {"month": "2026-08", "sessions": 1, "energy_used": None,
         "cost": None, "fast_sessions": 0},
        {"month": "2026-09", "sessions": 1, "energy_used": 300.0,
         "cost": 150.0, "fast_sessions": 0},
    ]


def test_locations_endpoint(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1, address_id=2)          # 东莞 1 次
    seed_charging(db, id=2, address_id=1,          # 深圳 2 次
                  start_date=datetime(2026, 9, 8, 10, 0))
    seed_charging(db, id=3, address_id=1,
                  start_date=datetime(2026, 9, 9, 10, 0))
    d = auth.get("/tesla/charging/api/locations").json()
    assert d[0]["location"] == "华为立体车库"        # 次数多的排前面
    assert d[0]["sessions"] == 2
    assert d[0]["city"] == "深圳市"
    assert d[1]["location"] == "长安镇"
    assert d[1]["city"] == "东莞市"


# ---------------------------------------------------------------- 费用编辑
def test_cost_patch_rejects_out_of_range(auth):
    for bad in (-1, 100001):
        r = auth.patch("/tesla/charging/api/sessions/1/cost", json={"cost": bad})
        assert r.status_code == 400, bad
        assert "金额" in r.json()["detail"]


def test_cost_patch_unknown_session(auth):
    r = auth.patch("/tesla/charging/api/sessions/99999/cost", json={"cost": 10})
    assert r.status_code == 404


def test_cost_patch_updates_db(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332)      # used 48 kWh
    r = auth.patch("/tesla/charging/api/sessions/332/cost", json={"cost": 30})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["cost"] == 30.0
    assert d["price_per_kwh"] == round(30.0 / 48.0, 3)
    # 真实写库: 换个会话能看到 (金额四舍五入到 2 位)
    assert db.get(ChargingProcess, 332).cost == 30.0


def test_cost_patch_clear_with_null(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332, cost=30.0)
    r = auth.patch("/tesla/charging/api/sessions/332/cost", json={"cost": None})
    assert r.status_code == 200
    assert r.json()["cost"] is None
    assert db.get(ChargingProcess, 332).cost is None


def test_cost_patch_rounds_to_two_decimals(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332)
    r = auth.patch("/tesla/charging/api/sessions/332/cost",
                   json={"cost": 30.456})
    assert r.status_code == 200
    assert db.get(ChargingProcess, 332).cost == 30.46


def test_charging_page_single_column_and_lazy_chain(auth):
    """充电列表单列 (手机优先, 对齐行程页) + Chrome 懒加载修复 (装载后链式续载)。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    for frag in ['id="masonry"', "flex-direction: column", "PRELOAD_PX = 800",
                 'rootMargin: PRELOAD_PX + "px"',
                 "getBoundingClientRect().top < window.innerHeight + PRELOAD_PX",
                 "max-width: 760px"]:
        assert frag in html, f"充电页缺少 {frag}"
    # 多列瀑布流的列容器/列数逻辑已删
    assert "m-col" not in html and "colCount" not in html


def test_charging_page_unrecorded_cost_red(auth):
    """没记费用的充电记录红标醒目: 卡片红色"添加费用"胶囊 + 详情费用格红字。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    for frag in [
        '<button class="cs-cost none" data-cost>＋ 添加费用</button>',
        ".cs-cost.none {", "background: #e5484d",   # 红色实心胶囊
        '未记费用',                                   # 详情格文案
        ".st-cost .val.red { color: #e5484d; }",     # 详情红字
        'cv.classList.toggle("red", cost == null)',  # 记完费用就地摘红
    ]:
        assert frag in html, f"充电页缺少 {frag}"


def test_charging_page_soc_axis_fixed_and_dense(auth):
    """SOC 轴固定 0-100% 量程: 标签按真实百分比定位 (贴边的 space-between 读起来像自适应);
    电量与费用并入一行, 收紧卡片纵向留白。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    assert "soc-lbl" not in html                 # 贴边标签行已删
    assert 'class="sa-lb"' in html               # 轴标签钉在真实位置
    assert "Math.min(it.start_soc, 93)" in html  # 左标签左缘 = 充电起点
    assert "right:${100 - it.end_soc}%" in html  # 右标签右缘 = 终点
    assert 'class="cs-main"' in html             # 电量 + 费用同行


def test_charging_page_soc_labels_merge_on_short_charges(auth):
    """短充电 (起止差 < 15%) 两端标签钉真实百分比会叠字: 并成一个 "起 → 终"
    标签居中钉在轨迹中点, 中点钳 15~85% (标签再宽也不出卡)。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    assert "it.end_soc - it.start_soc >= 15" in html   # 阈值: 起止差 ≥15% 仍钉两端
    assert "Math.min(Math.max((it.start_soc + it.end_soc) / 2, 15), 85)" in html
    assert "transform:translateX(-50%)" in html        # 合并标签按中心定位
    assert "${it.start_soc} → ${it.end_soc}%" in html


# ---------------------------------------------------------------- 地点筛选
def test_charging_regions_endpoint(auth, db):
    """充电地点省市区三级树 (每级按次数降序); 解析不出省的地址不进树。

    覆盖两种 display_name: 连写 "广东省深圳市龙岗区坂田街道" 与 OSM 逗号链。
    """
    db.add(Address(id=3, name="无名地", city=None, display_name="某处"))
    db.add(Address(id=4, name="翠湖边", city=None,
                   display_name="翠湖西路, 华山街道, 五华区, 昆明市, 云南省, 650031, 中国"))
    db.commit()
    seed_addresses(db)                       # 1=深圳市龙岗区 2=东莞市长安镇
    seed_charging(db, id=1, address_id=1)
    seed_charging(db, id=2, address_id=1)
    seed_charging(db, id=3, address_id=2)
    seed_charging(db, id=4, address_id=4)    # 云南 (OSM 逗号链, 带邮编带中国)
    seed_charging(db, id=5, address_id=3)    # 解析不出省 → 不进树
    assert auth.get("/tesla/charging/api/regions").json() == [
        {"name": "广东省", "count": 3, "children": [
            {"name": "深圳市", "count": 2, "children": [
                {"name": "龙岗区", "count": 2, "children": []}]},
            {"name": "东莞市", "count": 1, "children": [
                {"name": "长安镇", "count": 1, "children": []}]}]},
        {"name": "云南省", "count": 1, "children": [
            {"name": "昆明市", "count": 1, "children": [
                {"name": "五华区", "count": 1, "children": []}]}]}]


def test_charging_sessions_filters_by_region(auth, db):
    """地点筛选: 省/市/区县逐级精确 ("/" 路径 1~3 段), 可与快慢充叠加。"""
    db.add(Address(id=3, name="无名地", city=None, display_name="某处"))
    db.commit()
    seed_addresses(db)
    seed_charging(db, id=1, address_id=1)    # 深圳 慢充 (无采样 → 非快充)
    seed_charging(db, id=2, address_id=1,
                  start_date=datetime(2026, 9, 8, 15, 50),
                  end_date=datetime(2026, 9, 8, 23, 2))
    seed_charge(db, 2, date=datetime(2026, 9, 8, 16, 0))   # 深圳 快充
    seed_charging(db, id=3, address_id=2,    # 东莞 慢充 (日期再早一档, 排序确定)
                  start_date=datetime(2026, 9, 6, 15, 50),
                  end_date=datetime(2026, 9, 6, 23, 2))
    seed_charging(db, id=4, address_id=3)    # 解析不出省 → 只在全列表出现

    def ids(**params):
        return [i["id"] for i in auth.get(
            "/tesla/charging/api/sessions", params=params).json()["items"]]

    assert ids(region="广东省") == [2, 1, 3]             # 省: 全省
    assert ids(region="广东省/深圳市") == [2, 1]         # 市
    assert ids(region="广东省/深圳市/龙岗区") == [2, 1]  # 区县
    assert ids(region="广东省/东莞市") == [3]
    assert ids(region="云南省") == []
    assert ids(region="广东省/深圳市", type="fast") == [2]
    assert auth.get("/tesla/charging/api/sessions",
                    params={"region": "省/市/区/街道"}).status_code == 400  # 最多 3 段


def test_charging_page_time_menu_calendar_and_region_filter(auth):
    """顶栏时间下拉 (快捷档 + 自定义日历) + 筛选行省市区级联, 筛选写进 URL。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    for frag in ['id="time-menu"', 'data-v="24h"', 'data-v="7d"', 'data-v="30d"',
                 'data-v="180d"', 'data-v="1y"', 'data-v="all"',
                 'data-v="custom"', 'id="tm-cal"', 'id="tm-prev"', 'id="tm-next"',
                 'id="tm-ym"', 'id="tm-sel"', 'id="tm-apply"', 'function calRender()',
                 '再点结束日期',
                 # 时间菜单在顶栏 nav-row (全站统一位置; 本页品牌旁还有车名胶囊)
                 '<span class="car-pill" id="car-pill">Tesla</span>\n'
                 '    <details class="nav-menu time-menu" id="time-menu">',
                 'id="loc-menu"', 'id="loc-opts"', "/tesla/charging/api/regions",
                 # 地点省市区级联 (行程页同款): 钻取行/返回行/面包屑/限高滚动
                 'class="menu loc-menu"', 'class="loc-back"', 'class="loc-crumb"',
                 '<button class="loc-row', "const locParam = () =>", "钻下一级",
                 # 快充/慢充筛选改下拉 (与地点筛选同款, 分段钮太占地方)
                 'id="type-menu"', 'id="type-opts"', 'id="type-lb"',
                 'data-v="fast"', "⚡ 快充", "🔌 慢充", "TYPE_LABELS",
                 '$("#type-opts").addEventListener',
                 "function syncURL()", 'u.searchParams.set("region", state.region)',
                 # 手机: 下拉面板锚全宽 header (日历行 ~300px, 挂胶囊右缘必出屏)
                 '@media (max-width: 479px)', '.nav-menu { position: static; }']:
        assert frag in html, f"充电页缺少 {frag}"
    assert "chips-range" not in html and 'id="tm-from"' not in html
    assert 'id="seg-type"' not in html and ".seg {" not in html   # 分段钮样式不许回来
    for i in ('time-menu', 'time-lb', 'time-opts', 'tm-dates', 'tm-cal', 'tm-prev',
              'tm-next', 'tm-ym', 'tm-sel', 'brand-menu', 'logout', 'loc-opts',
              'type-opts'):
        assert html.count(f'id="{i}"') == 1, f"页面 {i} 重复"
    # 筛选行太宽时手机端自己横滑, 不把整个页面带着滑 (下拉锚在 header 不受裁)
    assert ".filters { overflow-x: auto; scrollbar-width: none; }" in html
    assert ".filters::-webkit-scrollbar { display: none; }" in html


def test_charging_sheet_grab_drag_close(auth):
    """充电详情弹层手柄: 点一下关, 拖 >90px 松手也关 (跟手 + 回弹)。

    iOS Safari 对 touch 指针 setPointerCapture 会当场 pointercancel
    (用户实测拉不动), move/up 挂 window 级不捕获 —— 手指出界照样收,
    各端行为一致 (2026-09-13 修)。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    for frag in ['id="grab-zone"', "touch-action: none",
                 'window.addEventListener("pointermove", move)',
                 'window.addEventListener("pointerup", release)',
                 'window.removeEventListener("pointermove", move)',
                 "translateY(${dy}px)", "if (dy > 90) closeSheet()",
                 # 点一下也关; 拖过 8px 抑制随后的 click (trips 手柄同款)
                 'if (dy > 8) { dy = 0; return; }']:
        assert frag in html, f"充电页缺少 {frag}"
    assert "setPointerCapture(e.pointerId)" not in html   # iOS capture 即 cancel, 别回潮
    assert "touchstart" not in html          # 旧 touch 三件套已废 (鼠标拖不动)


def test_charging_page_cost_filter_menu(auth):
    """费用筛选下拉 (全部/已记录/未记录): 与类型筛选同款收起式, 写进 URL。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    for frag in ['id="cost-menu"', 'id="cost-opts"', 'id="cost-lb"',
                 'data-v="recorded"', 'data-v="missing"', "已记录费用", "未记录费用",
                 "COST_LABELS", '$("#cost-opts").addEventListener',
                 'u.searchParams.set("cost", state.cost)',
                 'cost: state.cost',                       # 列表请求带费用筛选
                 'qs0.get("cost")']:                       # URL 深链带入
        assert frag in html, f"充电页缺少 {frag}"
