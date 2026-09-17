"""行程筛选测试: 日期 / OSM 与旧版地区串 / 里程区间 / 地区树端点。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime
from app.tesla import repository
from app.tesla.models import Address
from tests.seed_factories import seed_addresses, seed_drive


def test_trips_sessions_filters_by_date(auth, db):
    """from/to 按出发日 (本地日期) 过滤; 快捷档与自定义日历共用这两个参数。"""
    seed_addresses(db)
    for i, day in enumerate((10, 20, 25)):
        seed_drive(db, id=i + 1, distance=10.0, duration_min=10, speed_max=50,
                   start_date=datetime(2026, 8, day, 4, 0),
                   end_date=datetime(2026, 8, day, 5, 0))
    base = "/tesla/trips/api/sessions"

    def ids(qs):
        return [i["id"] for i in auth.get(base + qs).json()["items"]]

    assert ids("?from=2026-08-21") == [3]           # 只剩 8/25
    assert ids("?from=2026-08-11&to=2026-08-24") == [2]   # 自定义区间
    assert ids("?to=2026-08-24") == [2, 1]
    assert auth.get(base, params={"from": "abc"}).status_code == 400
    assert auth.get(base, params={"to": "2026-13-99"}).status_code == 400


def test_parse_region_osm_and_legacy_formats():
    """display_name → (省, 市, 区县): OSM 逗号链 / 旧连写 / 各种真实脏数据。

    真库 547 条地址全量验证过的样本: 街道邮编中国大陆尾巴、区县重复
    ("…, 顺德区, 佛山市, 顺德区, 广东省")、POI 名带区字样、省直辖县、自治州。
    """
    p = repository.parse_region
    assert p("竹村, 福城街道, 龙华区, 深圳市, 广东省, 518110, 中国") == \
        ("广东省", "深圳市", "龙华区")
    # 尾巴带 "中国大陆" + 邮编
    assert p("广百新一城, 宝岗大道, 龙凤街道, 海珠区, 广州市, 广东省, "
             "中国大陆, 510250, 中国") == ("广东省", "广州市", "海珠区")
    # 区县重复: 从省向左先找到市 (佛山市), 再向左找到区 (顺德区)
    assert p("容山路, 食品厂, 容桂街道, 顺德区, 佛山市, 顺德区, 广东省, "
             "528300, 中国") == ("广东省", "佛山市", "顺德区")
    # POI 名带 "区" 字样 (A区/园区) 不会误当行政区
    assert p("华为溪流背坡村A区, 松山湖园区, 大朗镇, 东莞市, 广东省, "
             "523003, 中国") == ("广东省", "东莞市", "大朗镇")
    # 省直辖县: 没有市级, 区县提升到市层 (与级联菜单的第二级对齐)
    assert p("曼旦村, 勐腊县, 云南省, 666300, 中国") == ("云南省", "勐腊县", None)
    # 自治州作市层, 县级市作区县层
    assert p("广场大道, 曼景兰, 允景洪街道, 景洪市, 西双版纳傣族自治州, "
             "云南省, 666100, 中国") == ("云南省", "西双版纳傣族自治州", "景洪市")
    # 旧版连写格式 (conftest 种子 / 老数据)
    assert p("广东省深圳市龙岗区坂田街道") == ("广东省", "深圳市", "龙岗区")
    assert p("广东省东莞市长安镇") == ("广东省", "东莞市", "长安镇")
    # 解析不出省 = 无地区信息
    assert p("某处") == (None, None, None)
    assert p("") == (None, None, None)


def test_trips_sessions_filters_by_region_and_km(auth, db):
    """from_loc/to_loc 按省/市/区县路径过滤 (段数即精确度), km 按里程; 可叠加。"""
    db.add(Address(id=3, name="花城广场", city="广州市",
                   display_name="广东省广州市天河区"))
    db.commit()
    seed_addresses(db)
    # 1: 深圳→东莞 42.5km; 2: 东莞→广州 350km; 3: 深圳→深圳 15km
    seed_drive(db, id=1, distance=42.5, start_address_id=1, end_address_id=2)
    seed_drive(db, id=2, distance=350.0, start_address_id=2, end_address_id=3)
    seed_drive(db, id=3, distance=15.0, start_address_id=1, end_address_id=1)
    base = "/tesla/trips/api/sessions"

    def ids(**params):
        return [i["id"] for i in auth.get(base, params=params).json()["items"]]

    assert ids(from_loc="广东省") == [1, 2, 3]        # 省级: 整省
    assert ids(from_loc="广东省/深圳市") == [1, 3]    # 市级
    assert ids(from_loc="广东省/深圳市/龙岗区") == [1, 3]   # 区县级
    assert ids(to_loc="广东省/东莞市") == [1]
    assert ids(to_loc="广东省/东莞市/长安镇") == [1]
    assert ids(from_loc="广东省/深圳市", to_loc="广东省/东莞市") == [1]
    assert ids(km_min=20, km_max=100) == [1]          # 42.5km
    assert ids(km_min=300) == [2]
    assert ids(km_max=20) == [3]                      # 里程档 "20km 内"
    assert ids(from_loc="广东省/深圳市", km_min=300) == []  # 叠加无交集 → 空
    assert ids(from_loc="不存在的省") == []
    # 路径超过 3 段 → 400
    assert auth.get(base, params={"from_loc": "广东省/深圳市/龙岗区/坂田街道"}
                    ).status_code == 400


def test_trips_sessions_rejects_bad_km(auth):
    assert auth.get("/tesla/trips/api/sessions",
                    params={"km_min": -1}).status_code == 400
    assert auth.get("/tesla/trips/api/sessions",
                    params={"km_min": 100, "km_max": 20}).status_code == 400
    assert auth.get("/tesla/trips/api/sessions",
                    params={"km_max": 1e7}).status_code == 400


def test_trips_regions_endpoint(auth, db):
    """起终点省市区树: 三级嵌套 + 计数 (次数降序); 未结束行程不计,
    解析不出省的地址不进树。"""
    db.add(Address(id=3, name="花城广场", city="广州市",
                   display_name="广东省广州市天河区"))
    db.add(Address(id=6, name="曼旦村", city=None,
                   display_name="曼旦村, 勐腊县, 云南省, 666300, 中国"))
    db.add(Address(id=7, name="无名地", city=None, display_name="某处"))
    db.commit()
    seed_addresses(db)
    # 1: 深圳→东莞; 2: 东莞→广州; 3: 深圳→东莞; 5: 云南→东莞;
    # 4: 起点"某处"且未结束 → 两边都不计
    seed_drive(db, id=1, distance=10.0, start_address_id=1, end_address_id=2)
    seed_drive(db, id=2, distance=10.0, start_address_id=2, end_address_id=3)
    seed_drive(db, id=3, distance=10.0, start_address_id=1, end_address_id=2)
    seed_drive(db, id=5, distance=10.0, start_address_id=6, end_address_id=2)
    seed_drive(db, id=4, distance=10.0, start_address_id=7, end_address_id=2,
               end_date=None)
    d = auth.get("/tesla/trips/api/regions").json()
    assert d == {"start": [
        {"name": "广东省", "count": 3, "children": [
            {"name": "深圳市", "count": 2, "children": [
                {"name": "龙岗区", "count": 2, "children": []}]},
            {"name": "东莞市", "count": 1, "children": [
                {"name": "长安镇", "count": 1, "children": []}]}]},
        {"name": "云南省", "count": 1, "children": [
            {"name": "勐腊县", "count": 1, "children": []}]},
    ], "end": [
        {"name": "广东省", "count": 4, "children": [
            {"name": "东莞市", "count": 3, "children": [
                {"name": "长安镇", "count": 3, "children": []}]},
            {"name": "广州市", "count": 1, "children": [
                {"name": "天河区", "count": 1, "children": []}]}]},
    ]}
