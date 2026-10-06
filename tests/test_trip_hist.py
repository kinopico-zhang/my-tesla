"""速度档直方图测试 (统计页三卡, 2026-09-24 对账官方口径, 同日二次对账
修公式、三次对账修档沿后按用户点名改自然档): 原始 positions 上 SQL 聚合
—— 档沿自然十进整除 0-9/10-19/… (面板原式 speed×单位CASE/10 是 numeric
真除四舍五入, 档值 80 = 75-84; 上午两版逐字对齐面板后用户点名要自然档,
有意差半档) / 地形分流 (相邻海拔差 ±1m) / 官方 Grafana「不同速度下的能
耗」面板公式 (平地 Σ(power·speed)/Σ(speed)×10 与 AVG(power), 只收 ≥1km
行程, 0 档照画 —— 用户 2026-09-24 点名, 面板 min_speed_segment 默认 10
砍掉) / 每段原料的自有库缓存 v4 (v2 同款自然档原料兼容读回; v3 四舍五入
档 / v1 旧原料作废重算; 已结束行程 positions 不可变, 合并分组聚合原始
点位要 ~10s 不缓存挡不起)。
旧客户端 speedHist 分桶 (下采样载荷 + floor 档沿 + 模型定标) 已随首版
对账退役; 首版"÷平地均速×1000"公式 2026-09-24 用户拿面板对账点名退役
(120 档比面板低 ~20%, 低速档高数倍)。"""
import json
from datetime import datetime, timedelta

from app.tesla.models import DriveHistCache, Position
from app.tesla.repository.trips import track_hist
from tests.seed_factories import seed_drive

# 五个采样: 平地两根 (82km/h 15kW 首采 lag 空 / 84km/h 25kW) → 自然档 80,
# 官方公式速度加权: Σpw·s/Σs = (15·82+25·84)/166 ≠ 均值功率 —— 平地档
# 电耗pk=200.6 / 平均功率pw=20; 一根下坡 (78km/h 10kW, 海拔 -1) 自然档
# 归档 70 (整除舍尾), 不进平地电耗但时间/里程照入档; 一根上坡 (44km/h
# 5kW, 海拔 +4) → 档 40; 一根 4km/h 平地 → 档 0, 时间/里程入档, 电耗
# 也报 (用户 2026-09-24 点名 0 档照画: 该档 pk = 2·4/4×10 = 20, pw = 2)。
_T0 = datetime(2026, 9, 10, 0, 32)
_SAMPLES = [
    {"date": _T0, "speed": 82.0, "power": 15.0, "elevation": 100.0,
     "odometer": 100.00},
    {"date": _T0 + timedelta(seconds=10), "speed": 84.0, "power": 25.0,
     "elevation": 100.0, "odometer": 100.05},
    {"date": _T0 + timedelta(seconds=20), "speed": 78.0, "power": 10.0,
     "elevation": 99.0, "odometer": 100.26},
    {"date": _T0 + timedelta(seconds=30), "speed": 44.0, "power": 5.0,
     "elevation": 103.0, "odometer": 100.37},
    {"date": _T0 + timedelta(seconds=40), "speed": 4.0, "power": 2.0,
     "elevation": 103.0, "odometer": 100.38},
]


def _seed_hist_drive(db, drive_id, distance=1.2):
    seed_drive(db, id=drive_id, start_date=_T0,
               end_date=_T0 + timedelta(minutes=1), distance=distance)
    db.add_all(Position(drive_id=drive_id, car_id=1, longitude=114.05,
                        latitude=22.55, **s) for s in _SAMPLES)
    db.commit()


def test_track_hist_official_formula_and_terrain(db, owndb):
    """官方公式: 档 80 平地两根采样 —— pk = Σpw·sp/Σsp ×10
    = (15·82+25·84)/166×10 = 200.6 (速度加权: 非加权均值功率×10 是 200,
    首版 ÷均速×1000 会算 242), pw = AVG(power) = 20; 下坡 78 那根自然档
    (整除) 归档 70, 不进平地电耗但时间/里程照入档; 档 40 只有上坡采样
    → 平地电耗 None; 档 0 有平地采样, 电耗照报 (用户点名 0 档照画:
    pk = 2·4/4×10 = 20); 首采样 lag 空项不计
    时长/里程差但速度/功率照进官方公式原料。"""
    _seed_hist_drive(db, 51)
    h = track_hist(db, owndb, [51])
    assert h is not None
    assert h.step == 10
    assert len(h.t) == 9                      # 档 0..80 (最快 84 → 档 80)
    assert h.t[8] == 0.17                     # 档 80 两根 (82/84) 只有第二根
    assert h.km[8] == 0.05                    # 带时长/里程差 (首根 lag 空)
    assert h.pk[8] == 200.6 and h.pw[8] == 20.0   # 官方公式/采样均值
    assert h.t[7] == 0.17 and h.km[7] == 0.21    # 78 整除归档 70, 带自己的差
    assert h.pk[7] is None and h.pw[7] is None   # 下坡: 不进平地电耗
    assert h.t[4] == 0.17 and h.km[4] == 0.11    # 上坡档: 时间里程照入
    assert h.pk[4] is None and h.pw[4] is None
    assert h.t[0] == 0.17 and h.km[0] == 0.01    # 4km/h 平地 → 档 0
    assert h.pk[0] == 20.0 and h.pw[0] == 2.0    # 0 档照画 (2kW·4km/h)
    # 没沾过的档全零占位 (轴上留空档), 电耗 None
    assert h.t[1] == 0 and h.km[2] == 0 and h.pk[6] is None


def test_track_hist_cache_reuse(db, owndb):
    """首算落自有库缓存 (v4); 已结束行程 positions 不可变 → 之后 TeslaMate
    库里的点位删光也照回同数 (合并分组 68 万点聚合 ~10s, 全靠这层缓存)。"""
    _seed_hist_drive(db, 52)
    first = track_hist(db, owndb, [52])
    assert owndb.query(DriveHistCache).filter_by(drive_id=52).count() == 1
    assert json.loads(owndb.query(DriveHistCache).filter_by(
        drive_id=52).one().payload)["v"] == 4
    db.query(Position).delete(synchronize_session=False)   # 点位删光
    db.commit()
    assert track_hist(db, owndb, [52]) == first


def test_track_hist_stale_cache_recompute(db, owndb):
    """v1 (旧公式原料, 裸 list) / v3 (四舍五入档, 2026-09-24 上午半天版)
    缓存读不回 → 作废重算重写; v2 (同款自然档原料) 兼容读回不重算
    (上午赶在改档沿前算过的段不再白算一遍)。"""
    _seed_hist_drive(db, 60)
    _seed_hist_drive(db, 61)
    _seed_hist_drive(db, 62)
    owndb.add(DriveHistCache(drive_id=60, payload=json.dumps(
        [[80, 0, 2, 2460.0, 164.0, 10.0, 150.0, 0.05]])))   # v1 布局
    # v2 有效载荷: 只给档 70 平地一根 (10kW·78km/h, ps=78) —— 真算这趟的
    # 78 采样是下坡 (pk 该是 None), 缓存拿来就报 pk=10 恰证明走了缓存
    owndb.add(DriveHistCache(drive_id=61, payload=json.dumps(
        {"v": 2, "rows": [[70, 0, 1, 10.0, 78.0, 78.0, 10.0, 0.21]]})))
    owndb.add(DriveHistCache(drive_id=62, payload=json.dumps(
        {"v": 3, "rows": [[80, 0, 3, 50.0, 3330.0, 240.0, 30.0, 0.26]]})))
    owndb.commit()
    h1 = track_hist(db, owndb, [60])          # v1 旧布局: 作废重算
    h2 = track_hist(db, owndb, [61])          # v2 同款自然档: 直接用
    h3 = track_hist(db, owndb, [62])          # v3 四舍五入档: 作废重算
    assert h1 is not None and h2 is not None and h3 is not None
    assert h1.pk[8] == 200.6               # 重算, 不是 v1 的数
    assert h2.t[7] == 0.17 and h2.km[7] == 0.21
    assert h2.pk[7] == 10.0 and h2.pw[7] == 10.0     # 78/78×10: 缓存口径
    assert len(h2.t) == 8                  # 只有档 70: 不再重算出 9 档
    assert h3.t[8] == 0.17 and h3.t[7] == 0.17      # 自然档: 78 归档 70
    for did, v in ((60, 4), (62, 4)):
        assert json.loads(owndb.query(DriveHistCache).filter_by(
            drive_id=did).one().payload)["v"] == v         # 覆写成 v4
    assert json.loads(owndb.query(DriveHistCache).filter_by(
        drive_id=61).one().payload)["v"] == 2              # v2 原样留着


def test_track_hist_merged_additive(db, owndb):
    """合并 = 各段原料相加: 两段同款行程, 时间/里程翻倍; 官方公式对同构
    翻倍不变 (比值不变)。"""
    _seed_hist_drive(db, 53)
    _seed_hist_drive(db, 54)
    h = track_hist(db, owndb, [54, 53])          # 乱序进, 升序算
    assert h is not None
    assert h.t[8] == 0.33 and h.km[8] == 0.1
    assert h.pk[8] == 200.6 and h.pw[8] == 20.0   # 同构翻倍: 公式不变
    assert h.t[7] == 0.33 and h.pk[4] is None


def test_track_hist_short_drive_no_consumption(db, owndb):
    """<1km 行程不进电耗 (面板 min_distance=1): pk/pw 全 None, 时间/里程
    卡照有 (那两张是自家口径, 不过滤行程)。"""
    _seed_hist_drive(db, 59, distance=0.4)
    h = track_hist(db, owndb, [59])
    assert h is not None
    assert h.t[8] == 0.17 and h.km[8] == 0.05
    assert all(v is None for v in h.pk)
    assert all(v is None for v in h.pw)


def test_track_hist_power_null_leaves_time_km(db, owndb):
    """老行程没功耗数据: 电耗/功率全 None, 时间/里程照有 (三卡前两张活)。"""
    seed_drive(db, id=55, start_date=_T0, end_date=_T0 + timedelta(minutes=1),
               distance=1.2)
    db.add_all(Position(drive_id=55, car_id=1, longitude=114.05, latitude=22.55,
                        date=s["date"], speed=s["speed"], power=None,
                        elevation=s["elevation"], odometer=s["odometer"])
               for s in _SAMPLES)
    db.commit()
    h = track_hist(db, owndb, [55])
    assert h is not None
    assert h.t[8] == 0.17 and h.km[8] == 0.05
    assert all(v is None for v in h.pk)
    assert all(v is None for v in h.pw)


def test_track_hist_open_drive_and_endpoint(auth, db, owndb):
    """未结束行程不进直方图 (端点口径与列表一致); 接口 ids 三种写法
    (单 id / 逗号 / 首尾区间) 同途, 没轨迹 404。"""
    _seed_hist_drive(db, 56)
    _seed_hist_drive(db, 57)
    seed_drive(db, id=58, start_date=_T0, end_date=None)   # 未结束: 没点位
    assert track_hist(db, owndb, [58]) is None
    r = auth.get("/tesla/trips/api/hist?ids=56")
    assert r.status_code == 200
    assert r.json()["pk"][8] == 200.6
    assert auth.get("/tesla/trips/api/hist?ids=56,57").json()["t"][8] == 0.33
    assert auth.get("/tesla/trips/api/hist?ids=56-57").json()["km"][8] == 0.1
    assert auth.get("/tesla/trips/api/hist?ids=58").status_code == 404
    assert auth.get("/tesla/trips/api/hist?ids=abc").status_code == 400
