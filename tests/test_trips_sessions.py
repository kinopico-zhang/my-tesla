"""行程列表接口测试: 分页 / 字段容错 / 单条详情 / 司机标记。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime
from app.tesla import repository
from app.tesla.models import Address, Driver, TripDriver
from tests.seed_factories import seed_addresses, seed_drive


# ---------------------------------------------------------------- 列表
def test_trips_sessions_paginates(auth, db):
    seed_addresses(db)
    for i in range(3):
        seed_drive(db, id=i + 1, distance=42.5, duration_min=72, speed_max=118,
                   start_date=datetime(2026, 9, 10 - i, 0, 32),
                   end_date=datetime(2026, 9, 10 - i, 1, 44))
    r = auth.get("/tesla/trips/api/sessions?offset=0&limit=2")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 3
    assert len(d["items"]) == 2
    it = d["items"][0]
    assert it["id"] == 1
    assert it["date"] == "2026-09-10"          # UTC 00:32 → 北京 08:32
    assert it["start"] == "2026-09-10 08:32"
    assert it["end"] == "2026-09-10 09:44"
    assert it["km"] == 42.5
    assert it["min"] == 72
    assert it["speed_max"] == 118
    assert it["from"] == "广东省深圳市龙岗区坂田街道"   # 地址用 display_name
    assert it["to"] == "广东省东莞市长安镇"


def test_trips_sessions_address_cleanup(auth, db):
    """反向地理编码带来的尾部悬挂逗号/空白要清掉, 空地址兜底 未知位置。"""
    db.add(Address(id=1, name="a", city="c", display_name="广东省深圳市南山区, "))
    db.add(Address(id=2, name="b", city="c", display_name=None))
    db.commit()
    seed_drive(db, id=1)
    it = auth.get("/tesla/trips/api/sessions").json()["items"][0]
    assert it["from"] == "广东省深圳市南山区"    # 尾部 ", " 已清
    assert it["to"] == "未知位置"


def test_trips_sessions_tolerates_missing_fields(auth, db):
    """distance/duration/speed 为空时不炸, 前端显示 —。"""
    seed_drive(db, id=1, distance=None, duration_min=None, speed_max=None,
               start_address_id=None, end_address_id=None)
    it = auth.get("/tesla/trips/api/sessions").json()["items"][0]
    assert it["end"] is not None
    assert it["min"] is None and it["km"] is None and it["speed_max"] is None
    assert it["from"] == "未知位置" and it["to"] == "未知位置"


def test_trips_sessions_rejects_bad_pagination(auth, monkeypatch):
    def boom(*_args):
        raise AssertionError("参数非法不应查库")

    monkeypatch.setattr(repository, "list_trips", boom)
    base = "/tesla/trips/api/sessions"
    assert auth.get(base, params={"offset": -1}).status_code == 400
    assert auth.get(base, params={"limit": 0}).status_code == 400
    assert auth.get(base, params={"limit": 101}).status_code == 400


def test_trips_sessions_excludes_unfinished(auth, db):
    """未关闭行程 (TeslaMate 记录中断留下的 end_date 空行) 不进列表/单条,
    口径与 Grafana 行程面板 / 地图页全量轨迹一致。"""
    seed_addresses(db)
    seed_drive(db, id=1)
    seed_drive(db, id=1838, start_date=datetime(2026, 8, 21, 9, 7),
               end_date=None, distance=None, duration_min=None,
               speed_max=None, start_address_id=None, end_address_id=None)
    d = auth.get("/tesla/trips/api/sessions").json()
    assert d["total"] == 1
    assert [i["id"] for i in d["items"]] == [1]
    assert auth.get("/tesla/trips/api/sessions/1838").status_code == 404


def test_trip_session_one(auth, db):
    """单条行程接口: 分享链接 /tesla/trips?id=X 直开弹层时前端拉取。"""
    seed_addresses(db)
    seed_drive(db, id=1838)
    r = auth.get("/tesla/trips/api/sessions/1838")
    assert r.status_code == 200
    assert r.json() == {
        "id": 1838, "date": "2026-09-10",
        "start": "2026-09-10 08:32", "end": "2026-09-10 09:44",
        "km": 42.5, "min": 72, "speed_max": 118,
        "from": "广东省深圳市龙岗区坂田街道", "to": "广东省东莞市长安镇",
        "driver": None, "driver_id": None,     # 没配驾驶员 → 不显示
        "toll": None, "toll_km": None,         # 高速费还没算过
        "kwh": None, "wh_per_km": None,        # 没有充电记录 → 换算系数缺失
    }


def test_trip_session_one_404(auth):
    """不存在 / 未完成的行程 → 404 (前端抹掉地址栏参数)。"""
    assert auth.get("/tesla/trips/api/sessions/9999").status_code == 404


def test_trip_driver_mark(auth, db, owndb):
    """标/清行程驾驶员: 展示名显式标注 > 默认驾驶员兜底; 删驾驶员联动清标注。"""
    seed_addresses(db)
    seed_drive(db, id=1838)
    owndb.add(Driver(id=1, name="大导子", is_default=True))
    owndb.add(Driver(id=2, name="小导子"))
    owndb.commit()
    base = "/tesla/trips/api/sessions/1838"

    it = auth.get(base).json()
    assert it["driver"] == "大导子"            # 未标注 → 默认驾驶员
    assert it["driver_id"] is None             # 但显式标注为空

    it = auth.post("/tesla/trips/api/1838/driver",
                   json={"driver_id": 2}).json()
    assert it["driver"] == "小导子" and it["driver_id"] == 2
    lst = auth.get("/tesla/trips/api/sessions").json()["items"]
    assert lst[0]["driver"] == "小导子"        # 列表同样带标注

    it = auth.post("/tesla/trips/api/1838/driver",
                   json={"driver_id": None}).json()
    assert it["driver"] == "大导子" and it["driver_id"] is None   # 清除回默认

    auth.post("/tesla/trips/api/1838/driver", json={"driver_id": 2})
    auth.delete("/tesla/api/drivers/2")       # 删驾驶员 → 标注联动清掉
    it = auth.get(base).json()
    assert it["driver"] == "大导子" and it["driver_id"] is None


def test_trip_list_filters_by_driver(auth, db, owndb):
    """行程列表按驾驶员筛选, 与卡片展示同口径: 显式标注的 + 默认驾驶员时
    未标注的 (未标注在卡片上就显示默认驾驶员名)。"""
    seed_addresses(db)
    for did in (11, 12, 13):
        seed_drive(db, id=did)
    owndb.add(Driver(id=1, name="大导子", is_default=True))
    owndb.add(Driver(id=2, name="小导子"))
    owndb.add(TripDriver(drive_id=11, driver_id=2))
    owndb.commit()

    lst = auth.get("/tesla/trips/api/sessions?driver_id=2").json()
    assert [x["id"] for x in lst["items"]] == [11]
    assert lst["total"] == 1

    lst = auth.get("/tesla/trips/api/sessions?driver_id=1").json()   # 默认 → 含未标注
    assert sorted(x["id"] for x in lst["items"]) == [12, 13]
    assert lst["total"] == 2

    lst = auth.get("/tesla/trips/api/sessions?driver_id=99").json()  # 驾驶员不存在 → 空
    assert lst["items"] == [] and lst["total"] == 0
