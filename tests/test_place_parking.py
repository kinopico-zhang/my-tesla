"""常去地点停车事件口径测试 (2026-09-30 用户点名「你应该只看我停车是在
哪, 而不是路过哪. 比如 4栋 这个位置, 我都没去过」—— 4栋 的 40 次实锤
几乎全是 0.0-0.3 公里、一两分钟的停车坪小挪动): 挪车微程 (短于
PLACE_MIN_KM=0.5km) 整程不计; 同一次停车只计一次 (到达记一次, 下一程的
起点还是同一停车 —— 按折入后的组名比, 地理编码漂移不拆账 —— 不再计);
首程与断链 (上一程无终点) 后的起点照计。同名并组 (地址链折入裸地名)
的细验也搬来这 (2026-10-03 从 test_place_alias 迁入 —— 那边 details
钉一加顶到 200 行上限)。"""
from datetime import datetime

from app.tesla.models import Address
from tests.seed_factories import seed_drive

API = "/tesla/trips/api/stats/locations"


def _seed(db):
    """地址 9=家, 10=公司, 11=「广东省深圳市龙华区家」(地理编码漂移的同一家,
    地址链并组用), 12=4栋 (同停车坪)。真行程 10/11/13/14/15, 挪车 12
    (0.2km)。"""
    db.add(Address(id=9, name="家", display_name="广东省深圳市",
                   latitude=22.60, longitude=114.05))
    db.add(Address(id=10, name="公司", display_name="广东省深圳市龙岗区",
                   latitude=22.66, longitude=114.07))
    db.add(Address(id=11, name=None, display_name="广东省深圳市龙华区家",
                   latitude=22.61, longitude=114.06))
    db.add(Address(id=12, name="4栋", display_name="广东省深圳市观澜",
                   latitude=22.72, longitude=114.02))
    seed_drive(db, id=10, start_address_id=9, end_address_id=10)
    seed_drive(db, id=11, start_address_id=10, end_address_id=9,
               start_date=datetime(2026, 9, 11, 2, 0),
               end_date=datetime(2026, 9, 11, 3, 0))
    seed_drive(db, id=12, start_address_id=9, end_address_id=12,  # 挪车: 整程不计
               distance=0.2, duration_min=1,
               start_date=datetime(2026, 9, 12, 2, 0),
               end_date=datetime(2026, 9, 12, 2, 1))
    seed_drive(db, id=13, start_address_id=12, end_address_id=10,
               start_date=datetime(2026, 9, 13, 2, 0),
               end_date=datetime(2026, 9, 13, 3, 0))
    seed_drive(db, id=14, start_address_id=10, end_address_id=11,  # 链名家到达
               start_date=datetime(2026, 9, 14, 2, 0),
               end_date=datetime(2026, 9, 14, 3, 0))
    seed_drive(db, id=15, start_address_id=11, end_address_id=10,  # 同一停车不再计
               start_date=datetime(2026, 9, 15, 2, 0),
               end_date=datetime(2026, 9, 15, 3, 0))


def test_place_parking_events(auth, db):
    """4栋 只剩 1 次 (挪车 12 整程被滤, 起点 9 与终点 12 都不出现); 家 = 3
    次 (10 出发 + 11 到达 + 14 链名到达; 15 的起点与 14 的终点是同一停车,
    不二计); 公司 = 3 (10/13/15 到达, 11/13/15 的起点都接着上一终到, 不
    计)。同组多点坐标 spots 全录, 主坐标跟次数最多的原名走。"""
    _seed(db)
    assert auth.get(API).json() == [
        {"name": "公司", "trips": 3, "lat": 22.66, "lng": 114.07,
         "raws": ["公司"], "orig": None, "spots": [{"lat": 22.66, "lng": 114.07}],
         "details": [{"name": "公司", "trips": 3, "lat": 22.66, "lng": 114.07}]},
        {"name": "家", "trips": 3, "lat": 22.60, "lng": 114.05,
         "raws": ["家", "广东省深圳市龙华区家"], "orig": None,
         "details": [{"name": "家", "trips": 2, "lat": 22.60, "lng": 114.05},
                     {"name": "广东省深圳市龙华区家", "trips": 1,
                      "lat": 22.61, "lng": 114.06}],
         "spots": [{"lat": 22.60, "lng": 114.05}, {"lat": 22.61, "lng": 114.06}]},
        {"name": "4栋", "trips": 1, "lat": 22.72, "lng": 114.02,
         "raws": ["4栋"], "orig": None, "spots": [{"lat": 22.72, "lng": 114.02}],
         "details": [{"name": "4栋", "trips": 1, "lat": 22.72, "lng": 114.02}]},
    ]


def test_place_micro_drive_edge(auth, db):
    """0.5km 整数关口照走 (挪车滤的是「短于」), 1km 的短途真行程照计 ——
    门槛只拦停车坪挪车, 不吃掉真出行的短途。"""
    db.add(Address(id=13, name="便利店", display_name="广东省深圳市",
                   latitude=22.61, longitude=114.05))
    db.add(Address(id=14, name="家", display_name="广东省深圳市",
                   latitude=22.60, longitude=114.05))
    seed_drive(db, id=20, start_address_id=14, end_address_id=13,
               distance=0.5)      # 不短于 0.5: 真行程
    seed_drive(db, id=21, start_address_id=13, end_address_id=14,
               distance=0.4,      # 挪车: 整程不计 (连起点停车都不算到访)
               start_date=datetime(2026, 9, 11, 2, 0),
               end_date=datetime(2026, 9, 11, 2, 4))
    assert auth.get(API).json() == [
        {"name": "便利店", "trips": 1, "lat": 22.61, "lng": 114.05,
         "raws": ["便利店"], "orig": None, "spots": [{"lat": 22.61, "lng": 114.05}],
         "details": [{"name": "便利店", "trips": 1, "lat": 22.61, "lng": 114.05}]},
        {"name": "家", "trips": 1, "lat": 22.60, "lng": 114.05,
         "raws": ["家"], "orig": None, "spots": [{"lat": 22.60, "lng": 114.05}],
         "details": [{"name": "家", "trips": 1, "lat": 22.60, "lng": 114.05}]},
    ]


def test_place_chain_bare_auto_merge(auth, db):
    """同名并组 (2026-09-30 用户点名「如果两个地名是一样的, 就合并进行统
    计」): 省级前缀的地址链 (name 空时露脸的 display_name 长串) 末端就是
    某裸地名 → 同一处并成一根柱, 坐标跟组内次数最多的原名走; 碰巧同尾串
    的不同地名 (环城东路/城东路) 不是一个地方, 不误并。"""
    db.add(Address(id=5, name="天玑公馆", display_name="广东省深圳市龙华区",
                   latitude=22.71, longitude=114.01))
    db.add(Address(id=6, name=None,
                   display_name="广东省深圳市龙华区福城街道天玑公馆",
                   latitude=22.72, longitude=114.02))
    db.add(Address(id=7, name="城东路", display_name="广东省东莞市长安镇",
                   latitude=22.82, longitude=113.75))
    db.add(Address(id=8, name="环城东路", display_name="广东省东莞市长安镇",
                   latitude=22.83, longitude=113.76))
    seed_drive(db, id=5, start_address_id=5, end_address_id=None)
    seed_drive(db, id=6, start_address_id=6, end_address_id=None,
               start_date=datetime(2026, 9, 11, 2, 0),
               end_date=datetime(2026, 9, 11, 3, 0))
    seed_drive(db, id=7, start_address_id=6, end_address_id=None,
               start_date=datetime(2026, 9, 12, 2, 0),
               end_date=datetime(2026, 9, 12, 3, 0))
    seed_drive(db, id=8, start_address_id=7, end_address_id=None,
               start_date=datetime(2026, 9, 13, 2, 0),
               end_date=datetime(2026, 9, 13, 3, 0))
    seed_drive(db, id=9, start_address_id=8, end_address_id=None,
               start_date=datetime(2026, 9, 14, 2, 0),
               end_date=datetime(2026, 9, 14, 3, 0))
    assert auth.get(API).json() == [
        {"name": "天玑公馆", "trips": 3, "lat": 22.72, "lng": 114.02,
         "raws": ["广东省深圳市龙华区福城街道天玑公馆", "天玑公馆"], "orig": None,
         "details": [{"name": "广东省深圳市龙华区福城街道天玑公馆", "trips": 2,
                      "lat": 22.72, "lng": 114.02},
                     {"name": "天玑公馆", "trips": 1, "lat": 22.71, "lng": 114.01}],
         "spots": [{"lat": 22.72, "lng": 114.02}, {"lat": 22.71, "lng": 114.01}]},
        {"name": "城东路", "trips": 1, "lat": 22.82, "lng": 113.75,
         "raws": ["城东路"], "orig": None, "spots": [{"lat": 22.82, "lng": 113.75}],
         "details": [{"name": "城东路", "trips": 1, "lat": 22.82, "lng": 113.75}]},
        {"name": "环城东路", "trips": 1, "lat": 22.83, "lng": 113.76,
         "raws": ["环城东路"], "orig": None, "spots": [{"lat": 22.83, "lng": 113.76}],
         "details": [{"name": "环城东路", "trips": 1, "lat": 22.83, "lng": 113.76}]},
    ]
