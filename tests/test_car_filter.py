"""多车 car_id 穿参测试 (充电域): 双车种子下, 缺省 = 全部 (并集),
?car_id=N = 子集。列表/汇总/月度/地点/维度/地图点位/地区树; 未知
car_id 一律空结果 (宽容口径, 不 4xx)。行程/地图/驾驶见
test_car_filter_trips.py。
"""
from app.tesla.models import Address
from tests.car_seed_helpers import _seed_two_cars
from tests.seed_factories import seed_car


# ---------------------------------------------------------------- 车辆清单

def test_car_endpoint_lists_both_cars(auth, db):
    seed_car(db)
    seed_car(db, id=2, name="小黑", model="3", trim_badging="P", vin="5YJ3")
    cars = auth.get("/tesla/charging/api/car").json()
    assert [(c["id"], c["name"]) for c in cars] == [(1, "臭哈子"), (2, "小黑")]


# ---------------------------------------------------------------- 充电域

def test_charging_sessions_filter_by_car(auth, db):
    _seed_two_cars(db)
    d = auth.get("/tesla/charging/api/sessions").json()
    assert d["total"] == 2
    assert {i["id"] for i in d["items"]} == {1, 2}
    d1 = auth.get("/tesla/charging/api/sessions?car_id=1").json()
    assert d1["total"] == 1 and [i["id"] for i in d1["items"]] == [1]
    d2 = auth.get("/tesla/charging/api/sessions?car_id=2").json()
    assert d2["total"] == 1 and [i["id"] for i in d2["items"]] == [2]
    # 未知车辆 → 空结果 (宽容口径, 不 4xx)
    d9 = auth.get("/tesla/charging/api/sessions?car_id=99").json()
    assert d9["total"] == 0 and d9["items"] == []


def test_charging_summary_monthly_locations_filter_by_car(auth, db):
    _seed_two_cars(db)
    s = auth.get("/tesla/charging/api/summary").json()
    assert s["sessions"] == 2 and s["energy_added"] == 105.0
    s1 = auth.get("/tesla/charging/api/summary?car_id=1").json()
    assert s1["sessions"] == 1 and s1["energy_added"] == 45.0
    s2 = auth.get("/tesla/charging/api/summary?car_id=2").json()
    assert s2["sessions"] == 1 and s2["energy_added"] == 60.0

    # 两台车都充在 2026-09: 默认一个月条目 2 次, 车 1 只剩 1 次
    mm = auth.get("/tesla/charging/api/monthly").json()
    assert len(mm) == 1 and mm[0]["month"] == "2026-09"
    assert mm[0]["sessions"] == 2
    mm1 = auth.get("/tesla/charging/api/monthly?car_id=1").json()
    assert mm1[0]["sessions"] == 1

    # 地点统计: 默认两个地址各 1 次, 车 1 只剩华为立体车库
    locs = auth.get("/tesla/charging/api/locations").json()
    assert sorted(l["location"] for l in locs) == ["华为立体车库", "长安镇"]
    locs1 = auth.get("/tesla/charging/api/locations?car_id=1").json()
    assert [l["location"] for l in locs1] == ["华为立体车库"]
    assert locs1[0]["sessions"] == 1


def test_charging_dimensions_map_locations_regions_filter_by_car(auth, db):
    _seed_two_cars(db)
    # 维度: 车 1 快充 (90kW), 车 2 慢充 (11kW), 合起来 1 快 1 慢
    dim = auth.get("/tesla/charging/api/dimensions").json()
    assert dim["fast_sessions"] == 1 and dim["slow_sessions"] == 1
    dim1 = auth.get("/tesla/charging/api/dimensions?car_id=1").json()
    assert dim1["fast_sessions"] == 1 and dim1["slow_sessions"] == 0
    dim2 = auth.get("/tesla/charging/api/dimensions?car_id=2").json()
    assert dim2["fast_sessions"] == 0 and dim2["slow_sessions"] == 1

    # 充电地图点位: 地址补坐标后, 默认 2 个点, 车 1 只剩深圳那个
    for aid, lat, lng in ((1, 22.55, 114.05), (2, 22.80, 113.75)):
        addr = db.get(Address, aid)
        addr.latitude = lat
        addr.longitude = lng
    db.commit()
    pts = auth.get("/tesla/charging/api/map-locations").json()
    assert len(pts) == 2
    pts1 = auth.get("/tesla/charging/api/map-locations?car_id=1").json()
    assert len(pts1) == 1 and pts1[0]["id"] == 1
    assert pts1[0]["sessions"] == 1 and pts1[0]["fast_sessions"] == 1

    # 地区树: 默认广东省 2 次, 车 1 只剩深圳市 1 次
    tree = auth.get("/tesla/charging/api/regions").json()
    assert tree[0]["name"] == "广东省" and tree[0]["count"] == 2
    tree1 = auth.get("/tesla/charging/api/regions?car_id=1").json()
    assert tree1[0]["name"] == "广东省" and tree1[0]["count"] == 1
    assert [c["name"] for c in tree1[0]["children"]] == ["深圳市"]
