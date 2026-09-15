"""当前驾驶 (live) 测试: "在开"判据 = 未结束行程 + 位置点足够新。

TeslaMate 记录中断会留下大量未关闭行程 (库里躺着十几条 2026-08-21 的),
未关闭 ≠ 在开 —— 必须看最新位置点的新鲜度 (repository.LIVE_STALE_AFTER_S)。
"""
from datetime import datetime, timedelta, timezone

from tests.conftest import seed_charging, seed_drive, seed_position

_EPOCH = datetime(1970, 1, 1)


def _utcnow() -> datetime:
    """与库内 date 同口径的 UTC 裸时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _epoch(dt: datetime) -> int:
    """UTC 裸时间 → epoch 秒 (与 repository._utc_seconds 同算法)。"""
    return int((dt - _EPOCH).total_seconds())


# ---------------------------------------------------------------- 在开: 字段口径

def test_live_status_fields(auth, db):
    """开着的行程: 速度/SOC/位置取最新采样点, 里程 = odometer 差,
    电耗 = 续航差 (首个/最新非空轮询值) × 充电定标 (与行程页同口径)。"""
    now = _utcnow()
    seed_charging(db)   # 默认种子: 45 kWh / 210 km 续航增量 → 定标 3/14
    seed_drive(db, id=500, start_date=now - timedelta(minutes=40),
               end_date=None, distance=None, duration_min=None)
    seed_position(db, drive_id=500, date=now - timedelta(minutes=40),
                  longitude=114.05, latitude=22.55, speed=12,
                  odometer=100.0, battery_level=97, rated_battery_range_km=402.0)
    seed_position(db, drive_id=500, date=now - timedelta(minutes=20),
                  longitude=114.10, latitude=22.57, speed=40,
                  odometer=112.4, battery_level=93, rated_battery_range_km=None)
    seed_position(db, drive_id=500, date=now - timedelta(seconds=70),
                  longitude=114.20, latitude=22.59, speed=55,
                  odometer=120.0, battery_level=91, rated_battery_range_km=377.2)
    seed_position(db, drive_id=500, date=now - timedelta(seconds=30),
                  longitude=114.26, latitude=22.61, speed=62,
                  odometer=124.8, battery_level=90, rated_battery_range_km=None)

    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is True
    assert j["drive_id"] == 500
    assert j["speed"] == 62 and j["speed_max"] == 62   # 最新点 / 全程最高
    assert j["soc"] == 90
    assert j["rated_range_km"] == 377.2                # 最新非空轮询值
    assert j["km"] == 24.8                             # odometer 差
    assert j["kwh"] == 5.3                             # (402-377.2) × 3/14
    assert j["wh_per_km"] == 214
    assert j["lng"] == 114.26 and j["lat"] == 22.61
    assert j["pos_utc"] == _epoch(now - timedelta(seconds=30))
    assert j["started_utc"] == _epoch(now - timedelta(minutes=40))
    # 服务器时钟锚: 手机时钟不准时前端靠它校偏差, 否则已行驶被钳成 0:00
    assert abs(j["now_utc"] - _epoch(now)) < 5
    assert isinstance(j["start"], str) and j["start"]


# ---------------------------------------------------------------- 在开判据

def test_live_status_stale_open_drive_is_not_driving(auth, db):
    """未关闭但位置点在几个月前 (TeslaMate 中断残留) → 不算在开。"""
    old = datetime(2026, 8, 21, 9, 8)
    seed_drive(db, id=1838, start_date=old, end_date=None, distance=None)
    seed_position(db, drive_id=1838, date=old, longitude=114.0, latitude=22.5,
                  speed=20, odometer=100.0, battery_level=90,
                  rated_battery_range_km=300.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is False and j["drive_id"] is None


def test_live_status_picks_freshest_open_drive(auth, db):
    """多条未关闭行程里取位置点最新的那条 (与出发时间无关)。"""
    old = datetime(2026, 8, 21, 9, 8)
    now = _utcnow()
    seed_drive(db, id=1838, start_date=old, end_date=None, distance=None)
    seed_position(db, drive_id=1838, date=old, longitude=114.0, latitude=22.5,
                  speed=20)
    seed_drive(db, id=2208, start_date=now - timedelta(minutes=5),
               end_date=None, distance=None)
    seed_position(db, drive_id=2208, date=now - timedelta(seconds=10),
                  longitude=114.1, latitude=22.6, speed=33,
                  odometer=10.0, battery_level=80)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is True and j["drive_id"] == 2208 and j["speed"] == 33


def test_live_status_ignores_just_closed_drive(auth, db):
    """位置点再新, 行程已闭合 (end_date 非空) 就不是当前驾驶。"""
    now = _utcnow()
    seed_drive(db, id=1, start_date=now - timedelta(minutes=10),
               end_date=now - timedelta(seconds=60), distance=5.0)
    seed_position(db, drive_id=1, date=now - timedelta(seconds=61),
                  longitude=114.0, latitude=22.5, speed=10, odometer=100.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is False and j["drive_id"] is None


# ---------------------------------------------------------------- 电耗口径边界

def test_live_status_without_calibration_hides_kwh(auth, db):
    """没有充电定标 (无可用充电记录) 时电耗格显示占位, 其余照常。"""
    now = _utcnow()
    seed_drive(db, id=9, start_date=now - timedelta(minutes=3),
               end_date=None, distance=None)
    seed_position(db, drive_id=9, date=now - timedelta(minutes=3),
                  longitude=114.0, latitude=22.5, speed=5,
                  odometer=100.0, battery_level=90, rated_battery_range_km=400.0)
    seed_position(db, drive_id=9, date=now - timedelta(seconds=20),
                  longitude=114.01, latitude=22.51, speed=30,
                  odometer=101.5, battery_level=89, rated_battery_range_km=398.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is True
    assert j["km"] == 1.5
    assert j["kwh"] is None and j["wh_per_km"] is None


def test_live_status_short_drive_and_regen_clamp(auth, db):
    """里程不足 1km 平均电耗无意义 → None; 续航回弹 (校准/回收) 夹到 0。"""
    now = _utcnow()
    seed_charging(db)
    seed_drive(db, id=7, start_date=now - timedelta(minutes=1),
               end_date=None, distance=None)
    seed_position(db, drive_id=7, date=now - timedelta(minutes=1),
                  longitude=114.0, latitude=22.5, speed=3,
                  odometer=100.0, battery_level=90, rated_battery_range_km=400.0)
    seed_position(db, drive_id=7, date=now - timedelta(seconds=10),
                  longitude=114.001, latitude=22.501, speed=8,
                  odometer=100.4, battery_level=90, rated_battery_range_km=402.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["km"] == 0.4
    assert j["kwh"] == 0.0
    assert j["wh_per_km"] is None


# ---------------------------------------------------------------- 鉴权 / 页面

def test_live_api_requires_login(client):
    r = client.get("/tesla/live/api/status")
    assert r.status_code == 401
    assert r.json() == {"detail": "未登录"}


def test_live_page_skeleton(auth):
    """页面骨架: 车速/时长/电量格, 状态轮询 + 轨迹刷新 (复用行程接口),
    空态 / 结束态深链 / 信号中断提示 / 高德失败降级。"""
    html = auth.get("/tesla/live").text
    html += auth.get("/tesla/static/live.js?v=1").text
    assert "当前驾驶 · My Tesla" in html
    for sel in ("lv-speed", "lv-elapsed", "lv-soc", "lv-range", "lv-km",
                "lv-kwh", "lv-avg", "lv-vmax"):
        assert f'id="{sel}"' in html, sel
    assert '"/tesla/live/api/status"' in html
    assert "POLL_MS = 5000" in html
    assert '"/tesla/trips/api/" + driveId + "/track"' in html
    assert "当前没有进行中的驾驶" in html
    assert "本次驾驶已结束" in html
    assert '"/tesla/trips?id=" + doneId' in html
    assert "信号可能中断" in html
    assert "地图暂不可用" in html
    assert "car-dot" in html
    # 实时数字定宽盒: 位数变化 (9→105 / 59:59→1:00:00) 不推动布局
    assert "min-width: 3ch" in html and "min-width: 7ch" in html
    assert '<span class="n">' in html
    assert "cur && cur.driving" in html   # 地图异步就位后补画车点/轨迹
    # 地图样式走 config (设置页可换), 不再写死幻影黑
    assert 'mapStyle: cfg.style || "amap://styles/dark"' in html
    # "©…auto navi" 版权文字按需求去掉
    assert '#map .amap-copyright { display: none !important; }' in html
    # 地名首帧竞态: 样式数据异步加载, complete 后延时补重渲染才有地名
    assert 'map.setFeatures(map.getFeatures())' in html
    assert "s.soc > 50" in html and "#32d74b" in html


def test_live_page_layout_bombproof(auth):
    """真机排版修复 (2026-09-13 用户报告): 速度+单位 flex 不换行 / 右列可收缩 /
    数据格 2×2 防溢出; 历史轨迹速度着色 + 末端连线接车点。"""
    html = auth.get("/tesla/live").text
    js = auth.get("/tesla/static/live.js?v=1").text
    # 速度大数字与单位: flex 行内永不换行 (窄屏/页缩放挤压时单位曾掉到第二行)
    assert "display: flex; align-items: baseline; white-space: nowrap;" in html
    # 右列可收缩, 出发行超宽省略号, 不再死宽抢速度区
    assert "flex-shrink: 1; min-width: 0; text-align: right; display: grid;" in html
    assert "text-overflow: ellipsis" in html
    # 数据格 2×2: 四格一行窄屏放不下会溢出圆角框
    assert "flex-wrap: wrap" in html and "flex: 1 1 calc(50% - 5px);" in html
    # 已行驶按服务器时钟走 (now_utc 校偏差), 手机时钟不准不再是 0:00
    assert "let serverSkew = 0;" in js
    assert "if (s.now_utc != null) serverSkew = s.now_utc - Date.now() / 1000;" in js
    assert "Date.now() / 1000 + serverSkew - s.started_utc" in js
    # 历史轨迹: 速度着色 (行程回放同套色阶) + 末端连线接到车当前位置
    assert '<script src="/tesla/static/trackutil.js?v=8"></script>' in html
    assert "TrackUtil.speedLines(t.pts)" in js
    assert "TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(" in js
    assert "tailLine.setPath([trackEnd, p])" in js
    assert 'strokeColor: "#3987e5"' not in js   # 纯蓝轨迹不许回来
