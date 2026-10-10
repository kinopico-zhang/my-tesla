"""place_names 域测试 (2026-10-02 #171「用 GPS 坐标结合高德, 不要信 teslamate」):
取名策略 / regeo 协议 / 读侧过滤 / worker 轮次 (AmapClient 换假件)。API 级在 test_place_amap_naming。"""
import httpx
import pytest

from app.tesla import place_worker, roads_amap
from app.tesla.models import Address, AppSetting
from app.tesla.repository.place_names import (done_address_ids,
                                              place_name_map,
                                              place_name_row,
                                              save_place_name)
from app.tesla.roads_amap_wire import Regeocode

SZ_LNG, SZ_LAT = 114.06, 22.61   # 深圳 (境内)


# ---------------------------------------------------------------- 取名策略
def test_pick_prefers_nearest_poi():
    """最近的 POI 优先 (pois 不保证按距离排, 得自己挑), 且非首个。"""
    geo = Regeocode.model_validate(
        {"pois": [{"name": "远处商场", "distance": 200},
                  {"name": "近处学校", "distance": 40}]})
    assert place_worker.pick_place_name(geo) == "近处学校"


def test_pick_poi_beyond_300m_falls_to_road():
    geo = Regeocode.model_validate(
        {"pois": [{"name": "远处商场", "distance": 500}],
         "roads": [{"name": "坂田大道", "distance": 30}]})
    assert place_worker.pick_place_name(geo) == "坂田大道"


def test_pick_road_beyond_100m_falls_to_district():
    geo = Regeocode.model_validate(
        {"pois": [{"name": "远处商场", "distance": 500}],
         "roads": [{"name": "远路", "distance": 400}],
         "addressComponent": {"district": "花都区", "township": "新雅街道"}})
    assert place_worker.pick_place_name(geo) == "花都区新雅街道"


def test_pick_filters_list_empty_fields_and_unnamed_poi():
    """addressComponent 的空字段是 [] 不是 "": 验形收编成空串; 没名字的近
    POI 不算, 落到道路; 区划全空回 "" (落 skip)。"""
    geo = Regeocode.model_validate(
        {"pois": [{"name": "", "distance": 10}],
         "roads": [{"name": "环城东路", "distance": 20}],
         "addressComponent": {"district": [], "township": "新雅街道"}})
    assert place_worker.pick_place_name(geo) == "环城东路"
    geo2 = Regeocode.model_validate(
        {"addressComponent": {"district": [], "township": []}})
    assert place_worker.pick_place_name(geo2) == ""
    assert len(place_worker.pick_place_name(Regeocode.model_validate(
        {"pois": [{"name": "名" * 80, "distance": 5}]}))) == 60   # 截 60 字


# ---------------------------------------------------------------- regeo 协议
def _regeo_client(resp, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(dict(request.url.params))
        return httpx.Response(200, json=resp)
    return roads_amap.AmapClient("k", transport=httpx.MockTransport(handler))


def test_regeo_parses_and_converts_to_gcj():
    """status 是字符串 "1"; location 收 GCJ-02 (WGS 进门换算过)。"""
    calls: list[dict[str, str]] = []
    geo = Regeocode.model_validate(
        {"pois": [], "addressComponent": {"district": "南山区"}})
    c = _regeo_client({"status": "1", "regeocode": {
        "pois": [], "addressComponent": {"district": "南山区"}}}, calls)
    assert c.regeo(SZ_LNG, SZ_LAT) == geo
    assert calls[0]["extensions"] == "all"
    assert calls[0]["location"] != f"{SZ_LNG:.6f},{SZ_LAT:.6f}"   # 已换 GCJ
    assert calls[0]["location"].startswith("114.0")               # 但还在原地附近


def test_regeo_quota_and_error_classify():
    c = _regeo_client({"infocode": "10003", "info": "DAILY_QUERY_OVER_LIMIT"})
    with pytest.raises(roads_amap.AmapQuota):
        c.regeo(SZ_LNG, SZ_LAT)
    c2 = _regeo_client({"status": "0", "infocode": "10001",
                        "info": "INVALID_USER_KEY"})
    with pytest.raises(roads_amap.AmapError):
        c2.regeo(SZ_LNG, SZ_LAT)


def test_regeo_abroad_short_circuits_no_request():
    """境外坐标问不出中国名: 不发请求不耗配额, 直接回 None (调用方落 skip)。"""
    calls: list[dict[str, str]] = []
    c = _regeo_client({"status": "1"}, calls)
    assert c.regeo(139.7, 35.68) is None       # 东京
    assert not calls and c.calls == 0


# ---------------------------------------------------------------- 读侧过滤
def test_place_name_map_filters(owndb):
    save_place_name(owndb, place_name_row(1, "ok", 1, "甲"))
    save_place_name(owndb, place_name_row(2, "skip", 1, "乙"))   # 境外: 不进读侧
    save_place_name(owndb, place_name_row(3, "ok", 1, ""))       # 空名: 同上
    assert place_name_map(owndb, [1, 2, 3, 99]) == {1: "甲"}
    assert place_name_map(owndb, []) == {}      # 空 ids 短路 (in_() 吃空列表查成全表)
    # 水位: ok/skip 都算已处理, 只按 v (旧版本的不算)
    assert done_address_ids(owndb, 1) == {1, 2, 3} and done_address_ids(owndb, 2) == set()


# ---------------------------------------------------------------- worker 轮次
class _FakeClient:
    mode = "ok"           # ok / abroad / quota / error
    made = 0
    regeo_calls = 0

    def __init__(self, key, transport=None, min_interval=0.0):
        self.calls = 0
        _FakeClient.made += 1

    def regeo(self, lng, lat):
        """逆地理 (mode 切换成功/境外/配额/网络错误)。"""
        _FakeClient.regeo_calls += 1
        mode = _FakeClient.mode
        if mode == "quota":
            raise roads_amap.AmapQuota("over limit")
        if mode == "error":
            raise roads_amap.AmapError("boom")
        if mode == "abroad":
            return None
        return Regeocode.model_validate(
            {"pois": [{"name": "高德大厦", "distance": 25}],
             "roads": [], "addressComponent": {}})

    def close(self):
        """假件无操作。"""


def _factories():
    from app import database  # pylint: disable=import-outside-toplevel
    return database.session_factory(), database.own_session_factory()


def _round(monkeypatch, mode="ok", key="k"):
    monkeypatch.setattr(roads_amap, "AmapClient", _FakeClient)
    _FakeClient.mode = mode
    _FakeClient.made = _FakeClient.regeo_calls = 0
    tesla_f, own_f = _factories()
    with own_f() as own:                     # pylint: disable=not-callable
        # Web 服务 Key 只认设置页 (2026-10-08 收敛): key 写进设置行, 没给
        # 就清 —— conftest 的已初始化口径种着 web key, 别让它顶上来
        own.merge(AppSetting(id=1, amap_web_key=key or ""))
        own.commit()
    return place_worker._round(tesla_f, own_f)   # pylint: disable=protected-access


def _seed(db, *ids):
    for i in ids:
        db.add(Address(id=i, name=f"旧名{i}",
                       display_name="广东省深圳市龙岗区坂田街道",
                       latitude=22.61, longitude=114.06))
    db.commit()


def test_round_without_key_idles(db, monkeypatch):
    _seed(db, 1)
    assert _round(monkeypatch, key=None) == (False, 0.0)
    assert _FakeClient.made == 0


def test_round_backfills_then_watermark(db, owndb, monkeypatch):
    _seed(db, 1, 2)
    assert _round(monkeypatch) == (True, 0.0)
    assert done_address_ids(owndb, place_worker.PLACE_NAME_V) == {1, 2}
    assert place_name_map(owndb, [1, 2]) == {1: "高德大厦", 2: "高德大厦"}
    assert _round(monkeypatch) == (False, 0.0)     # 水位已到: 不再构造 client
    assert _FakeClient.made == 0
    # 策略版本没到的行重查 (v bump = 全量换名机制)
    save_place_name(owndb, place_name_row(1, "ok", 0, "旧策略名"))
    assert _round(monkeypatch)[0]
    assert place_name_map(owndb, [1]) == {1: "高德大厦"}   # 换成新策略名


def test_round_abroad_lands_skip(db, owndb, monkeypatch):
    """境外坐标落 skip 行: 占水位不再试, 但不进读侧 (回退 TeslaMate 名)。"""
    _seed(db, 1)
    assert _round(monkeypatch, mode="abroad") == (True, 0.0)
    assert done_address_ids(owndb, place_worker.PLACE_NAME_V) == {1}
    assert place_name_map(owndb, [1]) == {}


def test_round_quota_pauses_without_row(db, owndb, monkeypatch):
    _seed(db, 1)
    progressed, pause = _round(monkeypatch, mode="quota")
    assert (progressed, pause) == (False, place_worker.QUOTA_PAUSE_S)
    assert not done_address_ids(owndb, place_worker.PLACE_NAME_V)   # 下轮重试


def test_round_gives_up_after_three_errors(db, owndb, monkeypatch):  # pylint: disable=protected-access
    """网络/服务错误 3 次后放弃 (第 4 轮不再调; 直呼 _round, helper 会清计数)。"""
    _seed(db, 1)
    monkeypatch.setattr(roads_amap, "AmapClient", _FakeClient)
    _FakeClient.mode = "error"
    _FakeClient.made = _FakeClient.regeo_calls = 0
    tesla_f, own_f = _factories()
    with own_f() as own:                         # pylint: disable=not-callable
        own.merge(AppSetting(id=1, amap_web_key="k"))
        own.commit()
    for _ in range(3):
        assert place_worker._round(tesla_f, own_f) == (False, 0.0)
    assert _FakeClient.regeo_calls == 3
    assert not done_address_ids(owndb, place_worker.PLACE_NAME_V)
    place_worker._round(tesla_f, own_f)        # attempts 满了
    assert _FakeClient.regeo_calls == 3        # 不再调用
