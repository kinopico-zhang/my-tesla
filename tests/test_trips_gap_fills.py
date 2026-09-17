"""断档补路测试 (自有库): 锚点校验, 覆盖重传, 时间戳单调,
降采样存活, 并入合并流。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""
import json
from datetime import datetime, timedelta
from app.tesla.models import Position, TrackFill
from tests.seed_factories import seed_addresses, seed_drive, seed_position


# ---------------------------------------------------------------- 断档补路 (自有库)
def _seed_gap_drive(db, drive_id=7):
    """一段有 ~2km 断档的行程: 前后各 2 个密集采样点, 中间跳变。"""
    seed_addresses(db)
    seed_drive(db, id=drive_id)
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_position(db, drive_id, id=None, date=t0,
                  longitude=114.000, latitude=22.50, speed=30.0, power=45000.0)
    seed_position(db, drive_id, id=None, date=t0 + timedelta(seconds=10),
                  longitude=114.001, latitude=22.50, speed=30.0, power=45000.0)
    # 2km 断档 (隧道): 10s → 80s
    seed_position(db, drive_id, id=None, date=t0 + timedelta(seconds=80),
                  longitude=114.021, latitude=22.50, speed=60.0, power=45000.0)
    seed_position(db, drive_id, id=None, date=t0 + timedelta(seconds=90),
                  longitude=114.022, latitude=22.50, speed=60.0, power=45000.0)
    return t0


FILL_BODY = {
    "drive_id": 7,
    "a": [114.001, 22.50], "b": [114.021, 22.50],
    "path": [[114.001, 22.50], [114.011, 22.50], [114.021, 22.50]],
}


def test_gap_fill_post_then_track_spliced(auth, db, owndb):
    """回传补路 → 存自有库 (TeslaMate 库零写入) → 轨迹接口服务端拼好。"""
    _seed_gap_drive(db)
    r = auth.post("/tesla/trips/api/gap_fill", json=FILL_BODY)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and 2.0 < d["km"] < 2.1    # 服务端实算里程 (加密不改长度)
    # 自有库一行; 原库 positions 还是 4 个 (只读不动)
    fills = owndb.query(TrackFill).all()
    assert len(fills) == 1
    assert fills[0].drive_id == 7 and fills[0].source == "amap"
    assert db.query(Position).count() == 4
    # 存库路径已按 80m 加密: 2km 断档 3 顶点 → 每条边 12 个插值点 = 27 点
    assert len(json.loads(fills[0].path)) == 27
    # 轨迹接口: 断档被插值点铺满 (时间按弧长, 速度两端插值, power 不造假)
    track = auth.get("/tesla/trips/api/7/track").json()
    assert track["pts"][0][:2] == [114.0, 22.5]
    assert track["pts"][-1][:2] == [114.022, 22.5]
    assert track["ts"] == sorted(track["ts"])        # 时间单调
    assert track["ts"][0] == 0 and track["ts"][-1] == 90
    assert [114.011, 22.5, 45.0, None] in track["pts"]   # 弧长中点: 速度 30→60 插值
    # 相邻点距恒 < 160m (断档识别最低阈值) —— 不再被前端二次识别成断档
    gaps = [abs(b[0] - a[0]) * 102.87 for a, b in zip(track["pts"], track["pts"][1:])]
    assert max(gaps) < 0.16


def test_gap_fill_rejects_far_or_misordered_anchors(auth, db):
    """端点离轨迹超 150m / 顺序颠倒 / 不存在的行程 → 4xx, 不落库。"""
    _seed_gap_drive(db)
    far = dict(FILL_BODY, a=[116.0, 24.0])
    assert auth.post("/tesla/trips/api/gap_fill", json=far).status_code == 400
    reversed_ = dict(FILL_BODY, a=FILL_BODY["b"], b=FILL_BODY["a"])
    assert auth.post("/tesla/trips/api/gap_fill", json=reversed_).status_code == 400
    assert auth.post("/tesla/trips/api/gap_fill",
                     json=dict(FILL_BODY, drive_id=99)).status_code == 404
    short = dict(FILL_BODY, path=[[114.001, 22.5]])
    assert auth.post("/tesla/trips/api/gap_fill", json=short).status_code == 400


def test_gap_fill_overwrites_same_gap(auth, db, owndb):
    """同一断档重复回传 = 覆盖 (按锚点唯一), 轨迹用最新路径。"""
    _seed_gap_drive(db)
    auth.post("/tesla/trips/api/gap_fill", json=FILL_BODY)
    better = dict(FILL_BODY, path=[[114.001, 22.50], [114.006, 22.50],
                                   [114.016, 22.50], [114.021, 22.50]])
    r = auth.post("/tesla/trips/api/gap_fill", json=better)
    assert r.status_code == 200
    assert len(owndb.query(TrackFill).all()) == 1     # 覆盖不是追加
    track = auth.get("/tesla/trips/api/7/track").json()
    # 4 原始 + 新路径的插值点 (4 顶点 / 3 边, 各边 80m 加密共 24 点, 去掉
    # 与锚点重合的首尾 = 26): 新顶点 114.006 在弧长 1/4 处, 速度 30→60 插值 37.5
    assert [114.006, 22.5, 37.5, None] in track["pts"]
    assert len(track["pts"]) == 30


def test_gap_fill_anchors_with_inbetween_points_keep_ts_monotonic(auth, db):
    """锚点区间内夹着原始点 (客户端按下采样视图挑锚点) → 按日期归并, ts 单调。

    实锤场景: 合并轨迹按段下采样, 客户端在它收到的序列里看到断档, 回传的
    锚点在原始流里中间还夹着未被抽掉的点 —— 旧实现把补路点整块插到锚点后,
    中间的原始点日期回退, 合并轨迹 ts 出现 12 秒乱序 (播放节拍错乱)。"""
    seed_addresses(db)
    seed_drive(db, id=8)
    t0 = datetime(2026, 9, 10, 0, 32)
    rows = [(0, 114.000, 22.50, 30.0),
            (10, 114.001, 22.50, 30.0),    # ← 锚点 a
            (11, 114.0015, 22.50, 30.0),   # 区间内原始点 (客户端视图抽掉的)
            (79, 114.0205, 22.50, 60.0),   # 区间内原始点
            (80, 114.021, 22.50, 60.0),    # ← 锚点 b
            (90, 114.022, 22.50, 60.0)]
    for sec, lng, lat, spd in rows:
        seed_position(db, 8, id=None, date=t0 + timedelta(seconds=sec),
                      longitude=lng, latitude=lat, speed=spd, power=45000.0)
    r = auth.post("/tesla/trips/api/gap_fill", json=dict(FILL_BODY, drive_id=8))
    assert r.status_code == 200 and r.json()["ok"] is True
    track = auth.get("/tesla/trips/api/8/track").json()
    assert track["ts"] == sorted(track["ts"])    # 修复前: 补路点块后 ts 回退
    assert track["ts"][0] == 0 and track["ts"][-1] == 90
    assert track["pts"][0][:2] == [114.0, 22.5]
    assert track["pts"][-1][:2] == [114.022, 22.5]
    assert len(track["pts"]) == 6 + 25           # 原始 6 + 补路 25 (27 加密点
    # 去掉与锚点重合的首尾), 区间内两个原始点一个不丢 —— 归并后按日期穿插
    assert [114.0015, 22.5, 30.0, 45000.0] in track["pts"]
    assert [114.0205, 22.5, 60.0, 45000.0] in track["pts"]


def test_gap_fill_points_survive_downsampling(auth, db):
    """大行程 (原始点 3 倍于预算, stride=3) 的补路点全保留不被抽掉。

    补路点相距 ~78m, 若被 stride 抽掉 2/3, 间距飙到 ~235m —— 超过断档
    识别阈值 160m, 会被前端再次当断档无限重规划 (1385 号行程的实发问题)。"""
    seed_addresses(db)
    seed_drive(db, id=9)
    t0 = datetime(2026, 9, 10, 0, 32)
    rows = [Position(drive_id=9, date=t0 + timedelta(seconds=i),
                     longitude=round(114.0 + i * 0.000002
                                     + (0.033 if i >= 5000 else 0), 6),
                     latitude=22.5, speed=30.0, power=45000.0)
            for i in range(15001)]
    db.add_all(rows)
    db.commit()                                       # i=4999 → 114.009998, i=5000 → 114.043
    r = auth.post("/tesla/trips/api/gap_fill", json={
        "drive_id": 9,
        "a": [114.009998, 22.5], "b": [114.043, 22.5],
        "path": [[114.009998, 22.5], [114.0265, 22.5], [114.043, 22.5]]})
    assert r.status_code == 200 and 3.3 < r.json()["km"] < 3.4
    track = auth.get("/tesla/trips/api/9/track").json()
    # 断档区 (114.01~114.043 之间没有原始点) 的补路点一个不少:
    # 2 边各 21 个插值点 + 中间顶点, 去掉与锚点重合的首尾 = 43
    gap_pts = [p for p in track["pts"] if 114.01 < p[0] < 114.043]
    assert len(gap_pts) == 43
    gaps = [abs(b[0] - a[0]) * 102.87 for a, b in zip(track["pts"], track["pts"][1:])]
    assert max(gaps) < 0.16                           # 全程无一处超断档阈值


def test_gap_fill_spliced_into_merged_stream_too(auth, db):
    """合并/流式接口同样吃到补路点 (所有轨迹消费方一个口径)。"""
    _seed_gap_drive(db, 7)
    t = datetime(2026, 9, 10, 3, 0)
    seed_drive(db, id=8, start_date=t, end_date=t + timedelta(minutes=10))
    seed_position(db, 8, id=None, date=t, longitude=115.0, latitude=23.0,
                  speed=20.0, power=None)
    seed_position(db, 8, id=None, date=t + timedelta(minutes=10),
                  longitude=115.1, latitude=23.0, speed=20.0, power=None)
    auth.post("/tesla/trips/api/gap_fill", json=FILL_BODY)
    r = auth.get("/tesla/trips/api/merged_stream?ids=7-8")
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    segs = lines[1:]
    assert len(segs[0]["pts"]) == 29                  # 4 原始 + 25 加密插值
    assert segs[0]["ts"][0] == 0 and segs[0]["ts"][-1] == 90
    assert [114.011, 22.5, 45.0, None] in segs[0]["pts"]
    assert len(segs[1]["pts"]) == 2
