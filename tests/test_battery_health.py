"""电池健康 (2026-09-27 新增, 充电组新页面): 口径照 TeslaMate Battery
Health 仪表盘移植 —— 满电续航 = 额定续航 ÷ 可用电量 × 100 (充电采样,
车端口径), 按充电日聚合; 只采充电结尾 100% 的过程 (2026-09-27 用户点名
「满电续航你只能采集充电结尾是100%的样来估算」—— SOC 顶部不线性,
部分充电外推有偏; 大 Session 能量过滤同日退役); 当前值 = 最近 100 个
满充采样均值; 健康度 = 当前 ÷ 峰值; 容量 = 满电续航 × 充电定标系数
(桩端, 与行程电耗同源)。接口数学 + 页面骨架两头钉。"""
from datetime import datetime

from app.tesla import repository
from tests.seed_factories import seed_charge, seed_charging
from tests.tesla_static_files import served_page


def _seed_day2(db, process_id: int, energy: float) -> None:
    """第二充电日 (2026-09-20): 满充过程 (结尾 100%), 续航增量 90,
    可用电量 40 / 额定 180 → 450。"""
    seed_charging(db, id=process_id,
                  start_date=datetime(2026, 9, 20, 3, 0),
                  end_date=datetime(2026, 9, 20, 5, 0),
                  end_battery_level=100,
                  charge_energy_added=energy,
                  start_rated_range_km=150.0, end_rated_range_km=240.0)
    seed_charge(db, process_id, date=datetime(2026, 9, 20, 4, 0),
                usable_battery_level=40, rated_battery_range_km=180)


# ---------------------------------------------------------------- 接口数学
def test_battery_health_math(db):
    """两个满充日 (500km → 450km): 日序列各归各日, 峰值 500, 当前 = 两采样
    均值 475, 健康度 95%; 定标系数 ΣkWh/Σ续航增量 = 75/300 = 0.25, 容量
    当前 118.8 / 峰值 125.0 kWh。"""
    # 日 1: 2026-09-07 (UTC 15:50 → 本地 23:50), 45kWh 充入, 续航增量 210
    seed_charging(db, id=1, end_battery_level=100, charge_energy_added=45.0)
    seed_charge(db, 1, usable_battery_level=40, rated_battery_range_km=200)
    # 日 2: 30kWh 充入, 同样充到满 —— 两采样都进当前值
    _seed_day2(db, 2, 30.0)
    h = repository.battery_health(db)
    assert [(p.day, p.range_km) for p in h.series] == \
        [("2026-09-07", 500.0), ("2026-09-20", 450.0)]   # 200/40, 180/40 ×100
    assert h.sample_days == 2
    assert h.max_range_km == 500.0
    assert h.current_range_km == 475.0                   # (500 + 450) / 2
    assert h.health_pct == 95.0                          # 475 / 500
    assert h.efficiency_kwh_per_km == 0.25               # 75 / 300
    assert h.current_capacity_kwh == 118.8               # 475 × 0.25
    assert h.max_capacity_kwh == 125.0                   # 500 × 0.25


def test_battery_health_usable_falls_back_to_level(db):
    """可用电量缺位时退回电池电量 (coalesce 口径, TeslaMate 同款):
    battery_level=50 + 额定 200 → 满电续航 400。"""
    seed_charging(db, id=1, end_battery_level=100)
    seed_charge(db, 1, battery_level=50, rated_battery_range_km=200)
    h = repository.battery_health(db)
    assert [(p.day, p.range_km) for p in h.series] == [("2026-09-07", 400.0)]
    assert h.current_range_km == 400.0 and h.max_range_km == 400.0
    assert h.health_pct == 100.0


def test_battery_health_without_efficiency(db):
    """没定标 (过程两端额定续航缺位, 定标系数算不出): 续航曲线照出, 容量
    两格如实 None —— 车端口径不依赖桩端定标。"""
    seed_charging(db, id=1, end_battery_level=100,
                  start_rated_range_km=None, end_rated_range_km=None)
    seed_charge(db, 1, usable_battery_level=50, rated_battery_range_km=200)
    h = repository.battery_health(db)
    assert h.efficiency_kwh_per_km is None
    assert h.current_capacity_kwh is None and h.max_capacity_kwh is None
    assert [(p.day, p.range_km) for p in h.series] == [("2026-09-07", 400.0)]
    assert h.current_range_km == 400.0 and h.health_pct == 100.0


def test_battery_health_partial_charge_excluded(db):
    """只采充到 100% 的过程 (2026-09-27 用户点名): 结尾 80% 的整段不进
    —— 序列/当前值都没有它 (SOC 顶部不线性, 部分充电外推满电有偏)。"""
    seed_charging(db, id=1, end_battery_level=100, charge_energy_added=45.0)
    seed_charge(db, 1, usable_battery_level=40, rated_battery_range_km=200)
    # 日 2: 电量不小 (30kWh) 但结尾只到 80% —— 整段不算数
    seed_charging(db, id=2, start_date=datetime(2026, 9, 20, 3, 0),
                  end_date=datetime(2026, 9, 20, 5, 0), end_battery_level=80,
                  charge_energy_added=30.0,
                  start_rated_range_km=150.0, end_rated_range_km=240.0)
    seed_charge(db, 2, date=datetime(2026, 9, 20, 4, 0),
                usable_battery_level=40, rated_battery_range_km=180)
    h = repository.battery_health(db)
    assert [(p.day, p.range_km) for p in h.series] == [("2026-09-07", 500.0)]
    assert h.sample_days == 1
    assert h.current_range_km == 500.0 and h.max_range_km == 500.0


def test_battery_health_small_full_session_counts(db):
    """大 Session 能量过滤退役 (2026-09-27 与满充规则换岗): 充入只有
    10kWh 但结尾 100% —— 照样进序列与当前值, 能量大小不再是门槛。"""
    seed_charging(db, id=1, end_battery_level=100, charge_energy_added=45.0)
    seed_charge(db, 1, usable_battery_level=40, rated_battery_range_km=200)
    _seed_day2(db, 2, 10.0)                       # 10kWh, 充到满
    h = repository.battery_health(db)
    assert h.sample_days == 2                      # 两日都在曲线上
    assert h.current_range_km == 475.0             # 两采样均值, 不滤
    assert h.efficiency_kwh_per_km == 0.1833       # 55 / 300 → 四舍五入


def test_battery_health_empty(db):
    """空库: 曲线空, 全部指标 None (前端照 — 显示)。"""
    h = repository.battery_health(db)
    assert h.series == [] and h.sample_days == 0
    for none_field in (h.health_pct, h.current_range_km, h.max_range_km,
                       h.current_capacity_kwh, h.max_capacity_kwh,
                       h.efficiency_kwh_per_km):
        assert none_field is None


def test_battery_health_endpoint(auth, db):
    """接口: car_id 穿参 (多车各算各的), 没数据的车空曲线。"""
    seed_charging(db, id=1, end_battery_level=100)
    seed_charge(db, 1, usable_battery_level=40, rated_battery_range_km=200)
    seed_charging(db, id=2, car_id=2, start_date=datetime(2026, 9, 20, 3, 0),
                  end_date=datetime(2026, 9, 20, 5, 0), end_battery_level=100,
                  charge_energy_added=30.0,
                  start_rated_range_km=150.0, end_rated_range_km=240.0)
    seed_charge(db, 2, date=datetime(2026, 9, 20, 4, 0),
                usable_battery_level=60, rated_battery_range_km=300)
    assert auth.get("/tesla/charging/api/battery").json()["sample_days"] == 2
    assert auth.get("/tesla/charging/api/battery?car_id=2"
                    ).json()["series"] == [{"day": "2026-09-20", "range_km": 500.0}]
    assert auth.get("/tesla/charging/api/battery?car_id=9").json()["series"] == []


# ---------------------------------------------------------------- 页面骨架
def test_battery_page_skeleton(auth):
    """电池健康页 (2026-09-27 从「电池健康度」改口, 两张峰值卡退役):
    充电组新视图 (抽屉树导航), 统计卡行 (四卡: 健康/满电续航/容量/定标)
    + 满电续航曲线 (bh- 前缀自家数据位), 图表底座与充电/行程统计共用
    (CHART_ELS 登记键 bhCurve), 口径脚注钉在图下。"""
    page = served_page(auth, "/tesla")
    for token in ('id="view-battery"', 'data-view="battery"',
                  '<h2>电池健康</h2>', 'id="bh-scroll"', 'id="bh-row"',
                  'id="bh-grid"', 'id="chart-bh-curve"', 'id="bh-curve-sub"',
                  'id="bh-loader"', 'id="bh-errbox"', 'id="bh-retry"',
                  'class="bh-note"', 'battery-page.js'):
        assert token in page, f"电池健康页缺 {token}"
    assert "电池健康度" not in auth.get("/tesla").text, "旧页名「电池健康度」回潮了"
    js = auth.get("/tesla/static/js/view/battery-page.js").text
    for frag in ('registerView("battery"', 'title: "电池健康"',
                 '"/tesla/charging/api/battery?"',
                 "bhRenderCards", "bhRenderCurve", "mkChart(\"bhCurve\")",
                 "markLine", "峰值", "loadEcharts"):
        assert frag in js, f"电池健康页 js 缺 {frag}"
    assert "满电续航 × 定标系数" in js and "电池容量" in js   # 四卡在
    trend = auth.get("/tesla/static/js/view/stats-chart-trend.js").text
    assert 'bhCurve: "#chart-bh-curve"' in trend       # 图位登记进共用底座
    drawer = auth.get("/tesla/static/js/tesla-drawer.js").text
    assert '{ key: "battery", lb: "电池健康" }' in drawer   # 充电组第三页
    assert "battery:" in drawer                          # DRW_ICONS 图标在表
