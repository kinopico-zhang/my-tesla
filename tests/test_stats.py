"""充电统计页测试: /dimensions 维度聚合接口 + 页面骨架 + 充电页瘦身守卫。

统计图表 (月度趋势/常去充电点) 与统计卡从充电记录页整体搬到本页,
充电页只留记录列表 —— 两页的边界由 test_charging_page_records_only 看住。
"""
from datetime import datetime

from tests.conftest import seed_addresses, seed_charge, seed_charging


# 充电记录/统计页共用格式化拆去了 format.js: 页面片段断言把先加载的
# format.js 一并拼进来查子串
def _page_scripts(auth, *names):
    return "".join(auth.get(f"/tesla/static/{name}").text for name in names)

PAGES = ["/tesla/charging", "/tesla/stats", "/tesla/chargemap", "/tesla/map",
         "/tesla/trips", "/tesla/groups", "/tesla/live", "/tesla/settings"]


def _seed_dimensions(db):
    """四笔覆盖各维度的充电: 快/慢充、不同开始时段 / 起充 SOC / 峰值功率 / 城市。

    A 深圳快充: 本地 09-07 23:50 开始 (UTC 15:50), 起充 20%, 峰值 90kW
    B 深圳慢充: 本地 09-08 18:00 开始 (UTC 10:00), 起充 50%, 无采样 (功率未知)
    C 东莞快充: 本地 09-09 10:00 开始 (UTC 02:00), 起充 85%, 峰值 250kW, 无费用
    D 无地址:   本地 09-09 11:30 开始 (UTC 03:30), 起充 SOC 未知 (不进 SOC 档)
    """
    seed_addresses(db)                      # 1=深圳市 2=东莞市
    seed_charging(db)                       # A
    seed_charge(db, 1)
    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 10, 0),
                  end_date=datetime(2026, 9, 8, 12, 0),
                  charge_energy_added=10.0, charge_energy_used=11.0,
                  duration_min=120, cost=None, start_battery_level=50,
                  end_battery_level=70)
    seed_charging(db, id=3, start_date=datetime(2026, 9, 9, 2, 0),
                  end_date=datetime(2026, 9, 9, 2, 40), address_id=2,
                  charge_energy_added=30.0, charge_energy_used=30.0,
                  duration_min=40, cost=None, start_battery_level=85,
                  end_battery_level=95)
    seed_charge(db, 3, charger_power=250.0)
    seed_charging(db, id=4, start_date=datetime(2026, 9, 9, 3, 30),
                  end_date=datetime(2026, 9, 9, 5, 30), address_id=None,
                  charge_energy_used=5.0, duration_min=120, cost=2.0,
                  start_battery_level=None, end_battery_level=30)


# ---------------------------------------------------------------- 维度接口
def test_dimensions_endpoint(auth, db):
    """四笔种子 → 快慢充 / 24 时段 / 起充 SOC 五档 / 峰值功率五档 / 城市聚合。"""
    _seed_dimensions(db)
    d = auth.get("/tesla/charging/api/dimensions").json()
    assert d["fast_sessions"] == 2 and d["slow_sessions"] == 2
    assert sum(d["by_hour"]) == 4                        # 每笔各进一个时段档
    assert d["by_hour"][23] == 1 and d["by_hour"][18] == 1
    assert d["by_hour"][10] == 1 and d["by_hour"][11] == 1
    assert d["by_soc"] == [0, 1, 1, 0, 1]                # 20%→1 档 50%→2 档 85%→4 档, 未知不计
    assert d["by_power"] == [0, 1, 0, 0, 1]              # 90kW→60-100 档 250kW→≥200 档, 无采样不计
    assert d["by_city"] == [                             # 次数降序; 无地址的 D 不进城市维度
        {"city": "深圳市", "sessions": 2, "energy": 59.0, "cost": 25.5},
        {"city": "东莞市", "sessions": 1, "energy": 30.0, "cost": 0.0},
    ]


def test_dimensions_respects_date_range(auth, db):
    """from=09-08 排除 09-07 的 A (统计与列表同日期口径)。"""
    _seed_dimensions(db)
    d = auth.get("/tesla/charging/api/dimensions",
                 params={"from": "2026-09-08"}).json()
    assert d["fast_sessions"] == 1 and d["slow_sessions"] == 2
    assert sum(d["by_hour"]) == 3
    assert {c["city"] for c in d["by_city"]} == {"深圳市", "东莞市"}


def test_dimensions_rejects_bad_date(auth, db):
    r = auth.get("/tesla/charging/api/dimensions", params={"from": "2026-13-99"})
    assert r.status_code == 400
    assert "日期格式错误" in r.json()["detail"]


def test_dimensions_empty_db(auth, db):
    """无充电记录: 各档全 0 / 空列表, 页面图表落"暂无数据"。"""
    d = auth.get("/tesla/charging/api/dimensions").json()
    assert d["fast_sessions"] == 0 and d["slow_sessions"] == 0
    assert d["by_hour"] == [0] * 24
    assert d["by_soc"] == [0] * 5
    assert d["by_power"] == [0] * 5
    assert d["by_city"] == []


# ---------------------------------------------------------------- 页面
def test_stats_page_skeleton(auth):
    """统计页: 统计卡行 + 七张图表卡 (每张图表/表格切换), 菜单高亮充电统计。"""
    html = auth.get("/tesla/stats").text
    html += _page_scripts(auth, "format.js", "stats.js")
    for frag in [
        "<title>充电统计 · My Tesla</title>",
        '<a class="on" href="/tesla/stats">充电统计</a>',
        'id="stats-row"', 'id="charts-grid"',
        'id="chart-monthly-kwh"', 'id="chart-monthly-cost"',   # 月度趋势 (上下两幅)
        'id="chart-fastslow"', 'id="chart-hour"', 'id="chart-loc"',
        'id="chart-socdist"', 'id="chart-powerdist"', 'id="chart-city"',
        '<div class="cc-title">快慢充占比</div>',
        '<div class="cc-title">充电时段</div>',
        '<div class="cc-title">起充电量分布</div>',
        '<div class="cc-title">峰值功率分布</div>',
        '<div class="cc-title">城市分布</div>',
        'id="monthly-view"', 'id="fastslow-view"', 'id="hour-view"',
        'id="loc-view"', 'id="soc-view"', 'id="power-view"', 'id="city-view"',
        'id="time-menu"', 'id="tm-cal"',                     # 时间筛选 + 自定义日历
        # 时间菜单在顶栏 nav-row (与全站一致), 本页没有筛选行
        '</details>\n    <details class="nav-menu time-menu" id="time-menu">',
        '"/tesla/charging/api/dimensions?"',                 # 新维度接口
        '"/tesla/charging/api/summary?"', '"/tesla/charging/api/monthly?"',
        "renderFastSlow", "renderHour", "renderSoc", "renderPower", "renderCity",
        "bindViewToggle",
        'echarts.connect([mkChart("monthlyKw"), mkChart("monthlyCost")])',
        "SOC_LB", "POWER_LB",                                # 五档标签常量
        'type: "pie"',                                       # 快慢充环形
        "grid-template-columns: 1fr 1fr",                    # 宽屏两列网格
    ]:
        assert frag in html, f"统计页缺少 {frag}"
    assert 'class="filters"' not in html   # 时间筛选上顶栏后, 本页没有筛选行


def test_charging_page_records_only(auth):
    """充电页只留记录列表: 统计卡/图表卡搬去统计页, 详情弹层的曲线图表保留。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, "format.js", "index.js")
    for frag in ['id="masonry"',                             # 记录列表
                 'id="chart-soc"', 'id="chart-pw"',          # 详情弹层图表仍在
                 ".mini-seg {", "renderPwChart"]:
        assert frag in html, f"充电页缺少 {frag}"
    for gone in ['id="stats-row"', 'id="charts-grid"', "loadSummary", "loadCharts",
                 "renderMonthly", "renderLocations", "bindViewToggle"]:
        assert gone not in html, f"充电页不应再有 {gone} (统计已挪充电统计页)"


def test_stats_link_in_all_nav_menus(auth):
    """每个业务页的页签菜单都有充电统计入口; 上次停留页/登录回跳白名单收录。"""
    for path in PAGES:
        html = auth.get(path).text
        assert 'href="/tesla/stats">充电统计</a>' in html, path   # 含 on 态 (统计页自身)
    lastpage = auth.get("/tesla/static/lastpage.js?v=1").text
    assert '"/tesla/stats", "/tesla/chargemap"' in lastpage
    login_js = auth.get("/static/login.js?v=1").text
    assert "stats|chargemap|map" in login_js
