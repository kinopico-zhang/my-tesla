"""充电统计的城市口径测试: 城市分布只到市 (区/县并上级市) 与城市双击
下钻区/县/镇二级 —— 2026-09-27 随 #52 分布图批次立进 test_stats.py,
同日行程统计批次时拆独立文件 (那边顶到 200 行硬上限)。"""
from app.tesla.models import Address
from tests.seed_factories import seed_addresses, seed_charging


def test_dimensions_districts_endpoint(auth, db):
    """城市下钻 (2026-09-27 用户点名「双击后展开二级地区充电分布」): 某市的
    区/县/镇分布, 城市口径与 by_city 同源 —— 区并市的逆操作; display_name
    链里市名前一段是区/县/镇, 解析不出退回原始 city (直筒子市整市一根柱)。"""
    seed_addresses(db)                   # 1=深圳市 (连写链, 无逗号) 2=东莞市
    db.add(Address(id=3, name="琶洲", city="海珠区",
                   display_name="磨碟沙, 琶洲街道, 海珠区, 广州市, 广东省, 510310, 中国"))
    db.add(Address(id=4, name="坂田", city="龙岗区",
                   display_name="坂田街道, 龙岗区, 深圳市, 广东省, 518129, 中国"))
    db.commit()
    seed_charging(db, id=5, address_id=3, cost=1.0)          # 广州市 · 海珠区
    seed_charging(db, id=6, address_id=4, cost=2.0)          # 深圳市 · 龙岗区
    seed_charging(db, id=7, address_id=4)                    # 深圳市 · 龙岗区 (再一笔)
    seed_charging(db, id=8, address_id=1)                    # 深圳市 · 连写链 → 原值兜底
    seed_charging(db, id=9, address_id=2)                    # 东莞市 (直筒子市)
    d = auth.get("/tesla/charging/api/districts",
                 params={"city": "深圳市"}).json()
    assert d == [
        {"district": "龙岗区", "sessions": 2,
         "energy": 96.0, "cost": 27.5},   # 次数降序; 两笔默认 48 kWh / 25.5+2 元
        {"district": "深圳市", "sessions": 1, "energy": 48.0, "cost": 25.5},
    ]
    assert auth.get("/tesla/charging/api/districts",
                    params={"city": "广州市"}).json() == [
        {"district": "海珠区", "sessions": 1, "energy": 48.0, "cost": 1.0}]
    # 链里解析不出区段的 (连写链): 退回原始 city 字段, 整市一根柱
    assert auth.get("/tesla/charging/api/districts",
                    params={"city": "东莞市"}).json() == [
        {"district": "东莞市", "sessions": 1, "energy": 48.0, "cost": 25.5}]
    assert auth.get("/tesla/charging/api/districts",
                    params={"city": "没有充电的城市"}).json() == []


def test_dimensions_city_maps_district_to_city(auth, db):
    """城市分布只到市 (2026-09-27 用户点名「都改成市, 去掉区」): 反向地理编码
    把区写进 city 时, 从 display_name 完整链里找回上级市; 本来就是市的不动,
    链里找不到市的保持原值。"""
    seed_addresses(db)
    db.add(Address(id=3, name="琶洲", city="海珠区",
                   display_name="磨碟沙, 琶洲街道, 海珠区, 广州市, 广东省, 510310, 中国"))
    db.add(Address(id=4, name="断链区", city="龙华区", display_name="某街道, 龙华区"))
    db.commit()
    seed_charging(db, id=5, address_id=3, cost=1.0)                    # 海珠区 → 广州市
    seed_charging(db, id=6, address_id=4, cost=1.0)                    # 断链 → 保持龙华区
    seed_charging(db, id=7)                                            # 本来就是市 (深圳)
    d = auth.get("/tesla/charging/api/dimensions").json()
    cities = {c["city"]: c["sessions"] for c in d["by_city"]}
    assert cities["广州市"] == 1 and "海珠区" not in cities
    assert cities["龙华区"] == 1          # 链里没有市: 原值兜底, 总比丢了强
    assert cities["深圳市"] == 1          # 本来就是市: 不进区映射分支
