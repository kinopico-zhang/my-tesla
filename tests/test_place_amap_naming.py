"""常去地点高德命名 API 级测试 (2026-10-02 #171): locations 接口的高德名优先 /
无缓存回退 TeslaMate 名 (旧行为) / 改名接口对高德名照常生效。单元级口径
(策略/regeo/worker) 在 test_place_names; 别名并组的细账在 test_place_alias。"""
from datetime import datetime

from app.tesla.models import Address
from app.tesla.repository.place_names import place_name_row, save_place_name
from tests.seed_factories import seed_drive

API = "/tesla/trips/api/stats/locations"
POST = "/tesla/trips/api/stats/place-alias"


def _seed(db, owndb):
    """地址 1=华为立体车库 (高德叫 万象天地), 2=同地库旧名 (无缓存行 → 回退
    TeslaMate 名), 3=街道兜底地址 (高德叫 坂田地铁站), 4=境外地址 (高德落
    skip → 也回退)。行程 1/2 起点地址 1, 行程 3 起点 2, 行程 4 起点 3,
    行程 5 起点 4 (行程按出发升序, 最近坐标后写覆盖)。"""
    db.add(Address(id=1, name="华为立体车库", display_name="广东省深圳市龙岗区",
                   latitude=22.61, longitude=114.06))
    db.add(Address(id=2, name="华为旧车库", display_name="广东省深圳市龙岗区",
                   latitude=22.62, longitude=114.07))
    db.add(Address(id=3, name=None,
                   display_name="广东省深圳市龙岗区坂田街道",
                   latitude=22.63, longitude=114.08))
    db.add(Address(id=4, name="东京塔停车场", display_name="日本东京都",
                   latitude=35.68, longitude=139.73))
    seed_drive(db, id=1, start_address_id=1, end_address_id=None)
    seed_drive(db, id=2, start_address_id=1, end_address_id=None,
               start_date=datetime(2026, 9, 11, 2, 0),
               end_date=datetime(2026, 9, 11, 3, 0))
    seed_drive(db, id=3, start_address_id=2, end_address_id=None,
               start_date=datetime(2026, 9, 12, 2, 0),
               end_date=datetime(2026, 9, 12, 3, 0))
    seed_drive(db, id=4, start_address_id=3, end_address_id=None,
               start_date=datetime(2026, 9, 13, 2, 0),
               end_date=datetime(2026, 9, 13, 3, 0))
    seed_drive(db, id=5, start_address_id=4, end_address_id=None,
               start_date=datetime(2026, 9, 14, 2, 0),
               end_date=datetime(2026, 9, 14, 3, 0))
    save_place_name(owndb, place_name_row(1, "ok", 1, "万象天地"))
    save_place_name(owndb, place_name_row(3, "ok", 1, "坂田地铁站"))
    save_place_name(owndb, place_name_row(4, "skip", 1, ""))


def _locs(auth):
    return auth.get(API).json()


def test_locations_amap_name_first(auth, db, owndb):
    _seed(db, owndb)
    assert _locs(auth) == [
        {"name": "万象天地", "trips": 2, "lat": 22.61, "lng": 114.06,
         "raws": ["万象天地"], "orig": None, "spots": [{"lat": 22.61, "lng": 114.06}],
         "details": [{"name": "万象天地", "trips": 2,
                      "lat": 22.61, "lng": 114.06}]},
        {"name": "东京塔停车场", "trips": 1, "lat": 35.68, "lng": 139.73,
         "raws": ["东京塔停车场"], "orig": None, "spots": [{"lat": 35.68, "lng": 139.73}],
         "details": [{"name": "东京塔停车场", "trips": 1,
                      "lat": 35.68, "lng": 139.73}]},
        {"name": "华为旧车库", "trips": 1, "lat": 22.62, "lng": 114.07,
         "raws": ["华为旧车库"], "orig": None, "spots": [{"lat": 22.62, "lng": 114.07}],
         "details": [{"name": "华为旧车库", "trips": 1,
                      "lat": 22.62, "lng": 114.07}]},
        {"name": "坂田地铁站", "trips": 1, "lat": 22.63, "lng": 114.08,
         "raws": ["坂田地铁站"], "orig": None, "spots": [{"lat": 22.63, "lng": 114.08}],
         "details": [{"name": "坂田地铁站", "trips": 1,
                      "lat": 22.63, "lng": 114.08}]},
    ]


def test_rename_works_on_amap_names(auth, db, owndb):
    """改名照旧好使: 高德名当原名进 place_aliases, 并组后 raws 带高德名。"""
    _seed(db, owndb)
    r = auth.post(POST, json={"places": ["万象天地", "华为旧车库"],
                              "alias": "公司"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _locs(auth) == [
        {"name": "公司", "trips": 3, "lat": 22.61, "lng": 114.06,
         "raws": ["万象天地", "华为旧车库"], "orig": "万象天地",
         "details": [{"name": "万象天地", "trips": 2, "lat": 22.61, "lng": 114.06},
                     {"name": "华为旧车库", "trips": 1,
                      "lat": 22.62, "lng": 114.07}],
         "spots": [{"lat": 22.61, "lng": 114.06}, {"lat": 22.62, "lng": 114.07}]},
        {"name": "东京塔停车场", "trips": 1, "lat": 35.68, "lng": 139.73,
         "raws": ["东京塔停车场"], "orig": None, "spots": [{"lat": 35.68, "lng": 139.73}],
         "details": [{"name": "东京塔停车场", "trips": 1,
                      "lat": 35.68, "lng": 139.73}]},
        {"name": "坂田地铁站", "trips": 1, "lat": 22.63, "lng": 114.08,
         "raws": ["坂田地铁站"], "orig": None, "spots": [{"lat": 22.63, "lng": 114.08}],
         "details": [{"name": "坂田地铁站", "trips": 1,
                      "lat": 22.63, "lng": 114.08}]},
    ]


def test_no_cache_rows_keeps_old_behavior(auth, db):
    """一行缓存都没有 (worker 没跑过 / 全失败) = 旧口径原样: TeslaMate 名。"""
    db.add(Address(id=1, name="华为立体车库", display_name="广东省深圳市龙岗区",
                   latitude=22.61, longitude=114.06))
    seed_drive(db, id=1, start_address_id=1, end_address_id=None)
    assert _locs(auth) == [
        {"name": "华为立体车库", "trips": 1, "lat": 22.61, "lng": 114.06,
         "raws": ["华为立体车库"], "orig": None, "spots": [{"lat": 22.61, "lng": 114.06}],
         "details": [{"name": "华为立体车库", "trips": 1,
                      "lat": 22.61, "lng": 114.06}]},
    ]
