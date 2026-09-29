"""行程轨迹测试: 单条全精度与降采样, 服务端断档检出 (原始密度 + 端点保留
下采样)。拆自 test_trips.py (结构化重构); 多选合并 (拼接/停驶剔除/去重/
校验) 2026-09-26 拆去 test_trips_tracks_merged.py (这边满 200 行硬上限)。"""
import math
from datetime import datetime, timedelta
from tests.seed_factories import seed_addresses, seed_drive, seed_position, seed_positions


# ---------------------------------------------------------------- 轨迹
def test_trip_track_full_resolution_with_speed(auth, db):
    seed_addresses(db)
    seed_drive(db, id=7)
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_position(db, 7, id=None, date=t0, longitude=114.05, latitude=22.55,
                  speed=30.0, power=45000.0)
    seed_position(db, 7, id=None,
                  date=t0 + timedelta(minutes=72, seconds=1),
                  longitude=114.06, latitude=22.56, speed=None, power=None)
    r = auth.get("/tesla/trips/api/7/track")
    assert r.status_code == 200
    # 每点 [lng, lat, speed, power_W, elevation_m]; 速度缺失按 0 (停车),
    # power/海拔可为 null (车不报/补路点); ts 是相对起点的秒偏移
    # (播放动画里算"已行驶时长"和平均功耗)
    assert r.json() == {"id": 7,
                        "pts": [[114.05, 22.55, 30.0, 45000.0, None],
                                [114.06, 22.56, 0, None, None]],
                        "ts": [0, 4321],
                        "gaps": []}   # 两点行程检不出断档 (阈值随中位段长走)


def _seed_track_with_hole(db, drive_id=7, n_before=30, n_after=29):
    """一条带真洞的轨迹: 前后两段 ~11m 步长, 中间瞬移 ~800m (隧道/信号丢失)。
    返回洞两侧的下标 (原始空间, 点数低于下采样上限时即载荷下标)。"""
    seed_addresses(db)
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_drive(db, id=drive_id, start_date=t0,
               end_date=t0 + timedelta(minutes=5))
    rows = [{"date": t0 + timedelta(seconds=i),
             "longitude": 114.0 + i * 1e-4, "latitude": 22.5, "speed": 30.0}
            for i in range(n_before)]
    rows += [{"date": t0 + timedelta(seconds=n_before + j),
              "longitude": 114.01 + j * 1e-4, "latitude": 22.5, "speed": 30.0}
             for j in range(n_after)]
    seed_positions(db, drive_id, rows)
    return n_before - 1, n_before


def test_trip_track_reports_server_side_gaps(auth, db):
    """断档改在服务端原始密度上检出, 端点对 [a, b, drive_id] 随载荷下发:
    前端 splitGaps 的自适应阈值在抽稀后的合并流里测不出真洞 (长途段抽稀
    后中位段长 100~263m, 阈值跟涨到 1~2.6km, 200m~3.7km 的真洞被当普通
    线段直连 —— 2026-09-22 用户实报分组补出来的轨迹全是直线)。"""
    a_raw, b_raw = _seed_track_with_hole(db)
    d = auth.get("/tesla/trips/api/7/track").json()
    assert d["gaps"] == [[a_raw, b_raw, 7]]
    a, b, _did = d["gaps"][0]
    assert b == a + 1      # 断档在载荷下标空间里相邻 (前端切段/补路的契约)


def test_trip_track_keeps_gap_endpoints_through_downsample(auth, db):
    """断档端点强制保留过下采样: 抽掉一个岸点, 前端就再也对不上这个洞
    (直连飞线回潮)。一万点 (stride=2) 里洞两侧一奇一偶, 都得活着。"""
    seed_addresses(db)
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_drive(db, id=7, start_date=t0, end_date=t0 + timedelta(hours=3))
    hole_at = 5000
    rows = [{"date": t0 + timedelta(seconds=i),
             "longitude": 114.0 + i * 1e-4, "latitude": 22.5, "speed": 30.0}
            for i in range(hole_at)]
    # 洞: 上段末 114.4999 (5000 步 × 1e-4°) → 下段头 114.55, ~4.8km;
    # 步长 ~10.7m, 阈值 160m, 段内不误报。raw 岸点 4999 奇 / 5000 偶,
    # stride=2 只留偶数 —— 4999 全靠强制保留活下来
    rows += [{"date": t0 + timedelta(seconds=hole_at + j),
              "longitude": 114.55 + j * 1e-4, "latitude": 22.5, "speed": 30.0}
             for j in range(10001 - hole_at)]
    seed_positions(db, 7, rows)
    d = auth.get("/tesla/trips/api/7/track").json()
    assert 5000 <= len(d["pts"]) <= 5002      # 下采样照常 (等间隔抽取)
    assert len(d["gaps"]) == 1
    a, b, did = d["gaps"][0]
    assert (did, b) == (7, a + 1)
    # 岸点就在载荷里: 这一步跨的是真洞本身 (~4.8km), 不是抽稀间距
    km = math.hypot((d["pts"][b][0] - d["pts"][a][0]) * 96.5,   # 经度按 cos(22.5°) 折算
                    (d["pts"][b][1] - d["pts"][a][1]) * 111)
    assert 4 < km < 6


def test_trip_track_carries_elevation(auth, db):
    """海拔列原样穿到载荷 (回放实时海拔格吃 pts[i][4]; 车报才有,
    近 60 天 98% 的点都有 —— 2026-09-21 用户点名加实时海拔)。"""
    seed_addresses(db)
    seed_drive(db, id=7)
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_position(db, 7, id=None, date=t0, longitude=114.05, latitude=22.55,
                  speed=30.0, power=45000.0, elevation=82.5)
    seed_position(db, 7, id=None, date=t0 + timedelta(minutes=72, seconds=1),
                  longitude=114.06, latitude=22.56, speed=None, power=None,
                  elevation=None)
    d = auth.get("/tesla/trips/api/7/track").json()
    assert d["pts"] == [[114.05, 22.55, 30.0, 45000.0, 82.5],
                        [114.06, 22.56, 0, None, None]]


def test_trip_track_downsamples_beyond_5000(auth, db):
    """5000 点上限: 超长轨迹等间隔抽取 (首末点必留)。"""
    seed_addresses(db)
    seed_drive(db, id=7, start_date=datetime(2026, 9, 10, 0, 32),
               end_date=datetime(2026, 9, 10, 3, 0))
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_positions(db, 7, [{"date": t0 + timedelta(seconds=i),
                            "longitude": 114.0 + i * 1e-5, "latitude": 22.5}
                           for i in range(10001)])
    d = auth.get("/tesla/trips/api/7/track").json()
    assert 5000 <= len(d["pts"]) <= 5002     # stride=2 → ~5001 点
    assert d["pts"][0][0] == 114.0
    assert d["pts"][-1][0] == round(114.0 + 10000 * 1e-5, 5)
    assert d["ts"][0] == 0 and d["ts"][-1] == 10000


def test_trip_track_404_when_no_points(auth, db):
    seed_addresses(db)
    seed_drive(db, id=999)                       # 0 点
    r = auth.get("/tesla/trips/api/999/track")
    assert r.status_code == 404
    seed_position(db, 999, id=None)              # 只剩 1 个点画不了线, 也算没有
    r = auth.get("/tesla/trips/api/999/track")
    assert r.status_code == 404
    assert "没有轨迹数据" in r.json()["detail"]
