"""充电统计视图测试: /dimensions 维度聚合接口 + 壳内视图骨架 + 充电视图瘦身守卫。

统计图表 (月度趋势/常去充电点) 与统计卡从充电视图整体搬到本视图,
充电视图只留记录列表 —— 两个视图的边界由 test_charging_view_records_only 看住。
城市口径 (只到市/区县下钻) 的测试住 test_charging_districts (2026-09-27 拆)。
"""
from datetime import datetime

from tests.charging_page_scripts import CHARGING_ASSETS, _page_scripts
from tests.seed_factories import seed_addresses, seed_charge, seed_charging
from tests.tesla_static_files import served_page


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
    """四笔种子 → 开始时段 12 档 / 起充 SOC 十档 / 峰值功率十档 / 单价十档 /
    时长十档 / 城市聚合 (2026-09-27 用户点名改十档; 快慢充计数随环形图退役,
    顶部统计卡的快充占比走汇总接口)。"""
    _seed_dimensions(db)
    d = auth.get("/tesla/charging/api/dimensions").json()
    assert sum(d["by_hour"]) == 4                        # 每笔各进一个时段档
    assert d["by_hour"][11] == 1 and d["by_hour"][9] == 1   # 23 点→11 组, 18 点→9 组
    assert d["by_hour"][5] == 2                           # 10 点/11 点同进 5 组 (2 小时一组)
    assert d["by_soc"] == [0, 0, 1, 0, 0, 1, 0, 0, 1, 0]  # 20%→2 档 50%→5 档 85%→8 档, 未知不计
    assert d["by_power"] == [0, 0, 0, 0, 1, 0, 0, 0, 0, 1]  # 90kW→80-100 档 250kW→≥180 档
    # 单价: A 25.5/48≈0.53→0.5-0.75 档, D 2.0/5=0.4→0.25-0.5 档; B/C 没记费用不计
    assert d["by_price"] == [0, 1, 1, 0, 0, 0, 0, 0, 0, 0]
    # 时长: A 432 分→6-8时, B/D 120 分→2-3时, C 40 分→30-60分
    assert d["by_duration"] == [0, 1, 0, 0, 2, 0, 0, 0, 1, 0]
    assert d["by_city"] == [                             # 次数降序; 无地址的 D 不进城市维度
        {"city": "深圳市", "sessions": 2, "energy": 59.0, "cost": 25.5},
        {"city": "东莞市", "sessions": 1, "energy": 30.0, "cost": 0.0},
    ]


def test_dimensions_respects_date_range(auth, db):
    """from=09-08 排除 09-07 的 A (统计与列表同日期口径)。"""
    _seed_dimensions(db)
    d = auth.get("/tesla/charging/api/dimensions",
                 params={"from": "2026-09-08"}).json()
    assert sum(d["by_hour"]) == 3
    assert d["by_price"] == [0, 1, 0, 0, 0, 0, 0, 0, 0, 0]   # 只剩 D (2.0/5=0.4→0.25-0.5 档)
    assert {c["city"] for c in d["by_city"]} == {"深圳市", "东莞市"}


def test_dimensions_rejects_bad_date(auth, db):
    r = auth.get("/tesla/charging/api/dimensions", params={"from": "2026-13-99"})
    assert r.status_code == 400
    assert "日期格式错误" in r.json()["detail"]


def test_dimensions_empty_db(auth, db):
    """无充电记录: 各档全 0 / 空列表, 页面图表落"暂无数据"。"""
    d = auth.get("/tesla/charging/api/dimensions").json()
    assert d["by_hour"] == [0] * 12
    assert d["by_soc"] == [0] * 10
    assert d["by_power"] == [0] * 10
    assert d["by_price"] == [0] * 10
    assert d["by_duration"] == [0] * 10
    assert d["by_city"] == []


# ---------------------------------------------------------------- 视图
def test_stats_view_skeleton(auth):
    """统计视图: 一级标题 + 统计卡行 + 八张图表卡 (纯图表 —— 2026-09-27 用户
    点名「都不需要表格视图」, mini-seg 切换退役; 快慢充环形图同日退役, 顶部
    统计卡已有快充占比一档); 月度趋势 = 充电量/充电费用两幅柱状 + 共享 12
    个月时间窗滑块 (任意历史窗口随手看); 开始时段 2 小时一组 (12 档, 同日
    用户点名), 单价/充电时长两图同批新增。
    统计卡是纵向网格 —— 整页只有上下滑 (2026-09-26「不要有左右滑」)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        '<div class="sec-head"><h2>充电统计</h2></div>',   # 一级标题 (与其他页同款)
        'class="stats-grid" id="stats-row"',              # 统计卡纵向网格
        'id="view-stats"', 'data-view="stats"',
        'id="stats-row"', 'id="charts-grid"',
        'id="chart-monthly-kwh"', 'id="chart-monthly-cost"',   # 月度两幅柱状
        '<span class="mc-name">充电量</span>', 'id="mkwh-total"',        # 上幅: 充电量 + 窗口合计
        '<span class="mc-name">充电费用</span>', 'id="mcost-total"',    # 下幅: 充电费用 + 窗口合计
        'id="monthly-slider-row"', 'id="monthly-window"',  # 共享时间窗滑块 (range)
        'id="win-first"', 'id="win-last"',                 # 轨道两端月份刻度
        'id="chart-hour"', 'id="chart-loc"',
        'id="chart-socdist"', 'id="chart-powerdist"',
        'id="chart-price"', 'id="chart-dur"', 'id="chart-city"',
        # 2026-09-28 名字类条形图改竖排 (用户点名「柱状图竖着放, 文字竖着排列」)
        'class="chart-box chart-vlabel" id="chart-loc"',    # 常去充电点
        'class="chart-box chart-vlabel" id="chart-city"',   # 城市层 + 下钻区县层
        '<div class="cc-title">充电开始时段</div>',
        '<div class="cc-title">起充电量分布</div>',
        '<div class="cc-title">峰值功率分布</div>',
        '<div class="cc-title">单价分布</div>',
        '<div class="cc-title">充电时长分布</div>',
        '<div class="cc-title">城市分布</div>',
        '"/tesla/charging/api/dimensions?"',                 # 新维度接口
        '"/tesla/charging/api/summary?"', '"/tesla/charging/api/monthly?"',
        "renderHour", "renderSoc", "renderPower",
        "renderPrice", "renderDuration", "renderCity",
        "pad(peak * 2)",           # 开始时段 2 小时一组: 峰值档副题报起止小时
        "dimsData.by_price", "dimsData.by_duration",         # 单价/时长两图的数据接线
        "MONTH_WINDOW", "drawMonthlyWindow",                # 12 个月窗口 + 滑块重绘
        'v.endsWith("-01")',        # 月份轴防重叠: 年头/首格带年份, 其余只标月份数
        'setProperty("--win"',      # 滑块块身宽度 = 12/N 轨道宽 (窗口本体)
        "valueFromCenter",          # 拖拽自管指针: 窗口内抓住带着走, 窗外点下先跳
                                    # (move/up 挂 window 级 —— iOS 指针 capture 会 cancel)
        'echarts.connect([mkChart("monthlyKw"), mkChart("monthlyCost")])',
        "SOC_LB", "POWER_LB", "PRICE_LB", "DUR_LB",         # 十档区间文案 (副题/气泡)
        "SOC_AX", "POWER_AX", "PRICE_AX", "DUR_AX",         # 十档轴标 = 档位起点
        '"/tesla/charging/api/districts?city="',             # 城市下钻接口 (双击展开二级)
        "cityDrill", "lastCityTap", "双击柱看区县",         # 下钻态 + 双击判定 + 副题提示
        "grid-template-columns: 1fr 1fr",                    # 宽屏两列网格
    ]:
        assert frag in html, f"统计视图缺少 {frag}"
    # 横滑整链退役 (禁词钉具体文件 —— 拼串口径下别的视图合法用横向滚动)
    stats_css = auth.get("/tesla/static/css/tesla-stats.css").text
    for gone in ("snap-row", "scroll-snap", "overflow-x"):
        assert gone not in stats_css, f"统计样式横向滑动残留: {gone}"
    # 竖排名字要占高度 (每字一行 × 7 字 ≈ 84px): 名字图挂加高类
    assert ".chart-box.chart-vlabel { height: 264px; }" in stats_css
    # 名字竖排铺柱底: 充电点截断后每字一行; 城市名短不截断, 下钻区县层同款
    assert "rows.map(d => stackLabel(truncateName(d.location, 7)))" in \
        auth.get("/tesla/static/js/view/stats-chart-trend.js").text
    dims_js = auth.get("/tesla/static/js/view/stats-chart-dimensions.js").text
    assert "rows.map(c => stackLabel(c.city))" in dims_js
    assert "rows.map(d => stackLabel(d.district))" in dims_js


def test_stats_view_tables_retired(auth):
    """表格视图退役守卫 (2026-09-27 用户点名「都不需要表格视图」) + 快慢充
    环形图退役守卫 (同日, 顶部统计卡已有快充占比): 视图段与三个统计脚本、
    统计样式里 mini-seg/表格渲染/切换绑定/快慢充图一根毛都不许剩
    (钉具体文件 —— 拼串口径下别的视图可能有同名物)。"""
    page = auth.get("/tesla").text
    stats = page[page.index('id="view-stats"'):page.index('id="view-chargemap"')]
    for gone in ("mini-seg", "chart-table", 'id="table-', "chart-fastslow",
                 'cc-title">充电时段</div>'):   # 旧名「充电时段」(改「充电开始时段」)
        assert gone not in stats, f"统计视图段退役残留: {gone}"
    for ref in ("js/view/stats-page.js", "js/view/stats-chart-trend.js",
                "js/view/stats-chart-dimensions.js", "css/tesla-stats.css"):
        body = auth.get(f"/tesla/static/{ref}").text
        for gone in ("bindViewToggle", "forceTableMode", "mini-seg",
                     "chart-table", '$("#table-', "renderFastSlow"):
            assert gone not in body, f"{ref} 退役残留: {gone}"


def test_charging_view_records_only(auth):
    """充电视图只留记录列表: 统计卡/图表卡在统计视图, 充电视图段没有;
    详情弹层的曲线图表保留。3.0 单壳后全页断言分不开视图, 这里按
    app.html 的视图段切开看边界。"""
    page = auth.get("/tesla").text
    charging = page[page.index('id="view-charging"'):page.index('id="view-stats"')]
    assert 'id="chg-masonry"' in charging                  # 记录列表 (壳内 chg- 前缀)
    for gone in ('id="stats-row"', 'id="charts-grid"'):
        assert gone not in charging, f"充电视图段不应再有 {gone} (统计在统计视图)"
    js = _page_scripts(auth, *CHARGING_ASSETS)
    for frag in ('id="chart-pw"',                      # 详情弹层图表仍在 (电量+曲线合并成一张)
                 "renderPwChart"):
        assert frag in js, f"充电视图缺少 {frag}"
    for gone in ("loadSummary", "loadCharts",
                 "renderMonthly", "renderLocations", "bindViewToggle"):
        assert gone not in js, f"充电视图脚本不应再有 {gone} (统计已挪统计视图)"
