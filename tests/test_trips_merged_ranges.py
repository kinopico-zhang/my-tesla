"""行程头尾区间与流式下载测试: 连续行程只记首尾 id 的展开校验,
NDJSON 边下边播。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""
import json
from datetime import datetime, timedelta
from app.tesla.models import Position
from tests.seed_factories import seed_addresses, seed_drive, seed_position


# ---------------------------------------------------------------- 头尾区间 (连续行程只记首尾 id)
def _seed_pair(db):
    """两段各 2 点的行程 (11 在前 12 在后), 供合并/流式用例复用。"""
    seed_addresses(db)
    t = datetime(2026, 9, 10, 0, 32)
    for drive_id in (11, 12):
        seed_drive(db, id=drive_id, start_date=t + timedelta(hours=drive_id),
                   end_date=t + timedelta(hours=drive_id, minutes=10))
        seed_position(db, drive_id, id=None,
                      date=t + timedelta(hours=drive_id),
                      longitude=114.0 + drive_id * 0.01, latitude=22.5,
                      speed=10.0, power=None)
        seed_position(db, drive_id, id=None,
                      date=t + timedelta(hours=drive_id, minutes=10),
                      longitude=114.1 + drive_id * 0.01, latitude=22.5,
                      speed=10.0, power=None)


def test_merged_range_form_expands_closed_drives(auth, db):
    """ids=首-尾: 展开成区间内全部已结束行程 (未结束的自动跳过), 与逗号形式等价。"""
    _seed_pair(db)
    seed_drive(db, id=13, start_date=datetime(2026, 9, 10, 13, 0),
               end_date=datetime(2026, 9, 10, 13, 10))
    seed_position(db, 13, id=None, date=datetime(2026, 9, 10, 13, 0),
                  longitude=114.3, latitude=22.5, speed=10.0, power=None)
    seed_position(db, 13, id=None, date=datetime(2026, 9, 10, 13, 10),
                  longitude=114.4, latitude=22.5, speed=10.0, power=None)
    seed_drive(db, id=14, start_date=datetime(2026, 9, 10, 13, 0),
               end_date=None)                      # 未结束: 区间内但不该出现
    by_range = auth.get("/tesla/trips/api/merged?ids=11-14").json()
    assert by_range["ids"] == [11, 12, 13]
    by_list = auth.get("/tesla/trips/api/merged?ids=11,12,13").json()
    assert by_range["pts"] == by_list["pts"]
    assert by_range["ts"] == by_list["ts"]
    # 坏区间 (头大于尾 / 非数字) → 400
    assert auth.get("/tesla/trips/api/merged?ids=14-11").status_code == 400
    assert auth.get("/tesla/trips/api/merged?ids=a-b").status_code == 400


def test_merged_range_form_requires_enough_drives(auth, db):
    """区间展开后不足 2 段或超 100 段 → 400 (与逗号形式同口径)。"""
    _seed_pair(db)
    assert auth.get("/tesla/trips/api/merged?ids=11-11").status_code == 400
    assert auth.get("/tesla/trips/api/merged?ids=99-100").status_code == 400
    # 展开后 101 段 → 400 (上限与逗号形式一致, 区间跨度本身不设限)
    t = datetime(2026, 9, 10, 0, 32)
    for drive_id in range(13, 112):       # 已有 11,12 → 共 101 段
        seed_drive(db, id=drive_id, start_date=t + timedelta(hours=drive_id),
                   end_date=t + timedelta(hours=drive_id, minutes=5))
    assert auth.get("/tesla/trips/api/merged?ids=11-111").status_code == 400
    # 恰 100 段 (空轨迹段只进 ids 不进 pts) → 放行, 边界不差一
    r = auth.get("/tesla/trips/api/merged?ids=11-110")
    assert r.status_code == 200
    assert r.json()["n"] == 100


# ---------------------------------------------------------------- 流式下载 (边下边播)
def test_merged_stream_ndjson_summary_then_segments(auth, db):
    """NDJSON 流: 首行汇总 (含 segs=有数据的段数), 之后每行一段; 拼起来与整包一致。"""
    _seed_pair(db)
    r = auth.get("/tesla/trips/api/merged_stream?ids=11-12")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert lines[0]["summary"]["ids"] == [11, 12]
    assert lines[0]["summary"]["n"] == 2
    assert lines[0]["segs"] == 2
    segs = lines[1:]
    assert len(segs) == 2
    assert all(len(s["pts"]) == 2 for s in segs)
    # 流式拼接 == 整包接口 (前端两种消费方式数据同源)
    full = auth.get("/tesla/trips/api/merged?ids=11-12").json()
    assert [p for s in segs for p in s["pts"]] == full["pts"]
    assert [t for s in segs for t in s["ts"]] == full["ts"]


def test_merged_stream_404_before_first_line(auth, db):
    """行程不存在/未结束 → 流开始前就 404 (JSON, 不是断在半路的流)。
    区间形式会跳过不存在的 id, 这里用逗号形式触发 404。"""
    _seed_pair(db)
    r = auth.get("/tesla/trips/api/merged_stream?ids=11,99")
    assert r.status_code == 404
    assert "不存在或未完成" in r.json()["detail"]


def test_merged_budget_proportional_to_segment_size(auth, db):
    """预算按各段原始点数占比分配: 长段多分 (真实下采样), 短段 200 保底全留。"""
    seed_addresses(db)
    t = datetime(2026, 9, 10, 0, 32)
    raw = {11: 30000, 12: 3000, 13: 50}
    for drive_id, cnt in raw.items():
        seed_drive(db, id=drive_id, start_date=t + timedelta(hours=drive_id * 5),
                   end_date=t + timedelta(hours=drive_id * 5, minutes=30))
        db.add_all(Position(drive_id=drive_id,
                            date=t + timedelta(hours=drive_id * 5, seconds=i),
                            longitude=114.0 + i * 1e-6, latitude=22.5,
                            speed=50.0, power=None)
                   for i in range(cnt))
    db.commit()
    r = auth.get("/tesla/trips/api/merged_stream?ids=11-13")
    assert r.status_code == 200
    seg_sizes = [len(json.loads(x)["pts"])
                 for x in r.text.splitlines()[1:] if x.strip()]
    # 长段 30000 原始点 → 预算 10909 → stride 2 → ~15001 (不再是平均主义的 200)
    assert 10900 < seg_sizes[0] <= 15002
    # 中段 3000 → 预算 1091 → stride 2 → ~1501
    assert 1090 < seg_sizes[1] <= 1502
    # 短段 50 → 200 保底 → 全留
    assert seg_sizes[2] == 50
