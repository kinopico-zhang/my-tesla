"""地点显示模板测试 (2026-10-17 用户点名「高德给的地址要完完整整的结构化地
存起来, 然后在设置界面, 可以设置各个界面显示地点的模板」): 组件提取/模板
渲染/显示层口径的单元账 + 模板设置接口 (存/预览, 空串 = 回默认的独立语义)
+ 三张消费面 (行程起终点/充电地点/常用地点) 与设置页前端接线。
regeo 协议与 worker 轮次在 test_place_names; 别名并组细账在 test_place_alias。"""
from datetime import datetime

from app.tesla.models import Address, Geofence
from app.tesla.place_naming import (PlaceFields, place_fields, place_tpl_map,
                                    render_place, shown_place_name)
from app.tesla.repository.place_names import (PlaceInfo, place_name_row,
                                              save_place_name)
from app.tesla.roads_amap_wire import Regeocode
from tests.seed_factories import seed_addresses, seed_charging, seed_drive
from tests.tesla_static_files import served_page

TAPI = "/tesla/api/place-templates"
LOCS = "/tesla/trips/api/stats/locations"


# ---------------------------------------------------------------- 组件提取
def _geo():
    return Regeocode.model_validate({
        "pois": [{"name": "万象城", "distance": 200},
                 {"name": "远处商场", "distance": 500}],
        "roads": [{"name": "深南大道", "distance": 80}],
        "addressComponent": {"province": "广东省", "city": "深圳市",
                             "district": "南山区", "township": "粤海街道",
                             "streetNumber": {"street": "深南大道",
                                              "number": "88号"},
                             "adcode": "440305"},
        "formatted_address": "广东省深圳市南山区万象城"})


def test_place_fields_extracts_components():
    """v3 组件随行: 镇/门牌街/门牌号/最近道路/最近 POI/区划码/推荐串逐项
    提出 (POI/道路与取名策略同门, 就近一条)。"""
    assert place_fields(_geo()) == PlaceFields(
        township="粤海街道", street="深南大道", number="88号",
        road="深南大道", poi="万象城", adcode="440305",
        rec="广东省深圳市南山区万象城", raw="")


def test_place_fields_gates_and_none():
    """距离门与取名同门: POI >300m / 道路 >100m 不算「就在这」(门外空串,
    模板渲染出空不冒充); 境外/失败 (None) 全空。"""
    geo = Regeocode.model_validate({
        "pois": [{"name": "远处商场", "distance": 500}],
        "roads": [{"name": "远路", "distance": 400}]})
    f = place_fields(geo)
    assert f.poi == "" and f.road == ""
    assert place_fields(None) == PlaceFields()


def test_place_fields_truncates_to_columns():
    """截长对齐落库列 (place_name_row 同款, 双保险)。"""
    geo = Regeocode.model_validate({
        "addressComponent": {"township": "镇" * 40,
                             "streetNumber": {"street": "街" * 99,
                                              "number": "号" * 40},
                             "adcode": "1" * 20},
        "formatted_address": "推" * 200})
    f = place_fields(geo)
    assert (len(f.township), len(f.street), len(f.number),
            len(f.adcode), len(f.rec)) == (24, 48, 24, 12, 120)


def test_place_name_row_packs_fields():
    """v3 组件打包在 fields (逐个拆传会超参数上限): fields 缺省 = 组件全空
    (v1/v2 老路径手搓行不炸), 超长双保险截。"""
    row = place_name_row(
        7, "ok", 3, "万象天地", province="广东省", city="深圳市",
        district="南山区",
        fields=PlaceFields(township="粤海街道", street="深南大道",
                           number="88号", road="深南大道", poi="万象城",
                           adcode="440305", rec="推荐串", raw='{"pois":[]}'))
    assert (row.township, row.street, row.number, row.road, row.poi,
            row.adcode, row.rec, row.raw) == (
        "粤海街道", "深南大道", "88号", "深南大道", "万象城", "440305",
        "推荐串", '{"pois":[]}')
    old = place_name_row(8, "ok", 2, "旧名", province="广东省")
    assert old.township == "" and old.raw == "" and old.v == 2
    fat = place_name_row(9, "ok", 3, "x",
                         fields=PlaceFields(poi="p" * 80, raw="r" * 70000))
    assert len(fat.poi) == 60 and len(fat.raw) == 65535


# ---------------------------------------------------------------- 模板渲染
_INFO = PlaceInfo(name="万象天地", province="广东省", city="深圳市",
                  district="南山区", township="粤海街道", street="深南大道",
                  number="88号", poi="万象城", rec="广东省深圳市南山区万象城")


def test_render_place_substitutes_vars():
    assert render_place("{市}{区} · {POI}", _INFO) == "深圳市南山区 · 万象城"
    assert render_place("{名字}({门牌})", _INFO) == "万象天地(88号)"
    # {路} = 门牌街 || 最近道路 (同概念两个来源, 模板只记一条)
    assert render_place("{路}", _INFO) == "深南大道"
    assert render_place("{路}", _INFO._replace(street="", road="坂田大道")) \
        == "坂田大道"


def test_render_place_cleans_glue_and_keeps_unknown():
    """空组件不留悬空分隔: 首尾扫掉, 中间连排并回一段; 空白折成一个空格;
    不认识的变量原样保留 (写错看得见)。"""
    bare = PlaceInfo("旧名", "", "", "南山区")    # v1 老行: 组件全缺
    assert render_place("{区} · {镇} · {POI}", bare) == "南山区"
    assert render_place("{省} · 、{市}", _INFO._replace(province="")) == "深圳市"
    assert render_place("{区}\n  {POI}", _INFO) == "南山区 万象城"
    assert render_place("{foo}", _INFO) == "{foo}"


def test_render_place_empty_paths():
    """没模板 / 没缓存行 / 组件全缺渲染空 → "" (调用方走默认拼装)。"""
    assert render_place("", _INFO) == ""
    assert render_place("{区}", None) == ""
    assert render_place("{镇}·{POI}", PlaceInfo("旧名", "", "", "")) == ""


def test_place_tpl_map_first_seen():
    """高德名 → 组件行: 同名多址取先见 (同一展示名下的地址组件近乎相同)。"""
    m = place_tpl_map({1: PlaceInfo("甲", "", "", "一"),
                       2: PlaceInfo("甲", "", "", "二"),
                       3: PlaceInfo("", "", "", "")})
    assert set(m) == {"甲"} and m["甲"].district == "一"


def test_shown_place_name_display_only():
    """常用地点组名只动显示层: 没模板 / 别名没缓存行 → 原样 (用户起的名
    永远赢); 渲染空回原名; 隐藏查渲染名 (删除动作送来的是屏幕行名)。"""
    info = PlaceInfo("万象天地", "", "", "南山区", poi="万象城")
    assert shown_place_name("万象天地", info, "", set()) == "万象天地"
    assert shown_place_name("我的地库", None, "{区}", set()) == "我的地库"
    assert shown_place_name("万象天地", info, "{区} · {POI}", set()) \
        == "南山区 · 万象城"
    assert shown_place_name("万象天地", info, "{区} · {POI}",
                            {"南山区 · 万象城"}) is None    # 整组隐
    assert shown_place_name("万象天地", PlaceInfo("旧名", "", "", ""), "{镇}",
                            set()) == "万象天地"    # 老行组件缺: 渲染空回原名


# ---------------------------------------------------------------- 接口
def test_place_templates_roundtrip_and_empty_means_default(auth, owndb):
    """专用端点的立身之本 (主设置保存把空串当「保持现值」的密码语义, 模板
    的空串是合法值 = 回默认, 两家合不得一个接口): 全量提交, 现读现生效,
    首尾空白剥掉。"""
    assert auth.get(TAPI).json() == {"trips": "", "charging": "", "places": ""}
    r = auth.post(TAPI, json={"trips": "{区} · {POI}", "charging": "{POI}",
                              "places": "  {镇}{路}  "})
    assert r.json() == {"trips": "{区} · {POI}", "charging": "{POI}",
                        "places": "{镇}{路}"}
    assert auth.get(TAPI).json() == r.json()
    # 空提交把已存的盖掉 (= 回默认), 不是「保持现值」
    auth.post(TAPI, json={"trips": "", "charging": "", "places": ""})
    assert auth.get(TAPI).json() == {"trips": "", "charging": "", "places": ""}


def test_place_templates_rejects_overlong(auth, owndb):
    """模板上限 80 字 (schema 拦, 手搓请求也进不来)。"""
    r = auth.post(TAPI, json={"trips": "长" * 81, "charging": "", "places": ""})
    assert r.status_code == 422
    assert auth.get(TAPI).json()["trips"] == ""      # 没存进去


def test_place_templates_preview_renders_fullest_row(auth, db, owndb):
    """预览拿组件最全的缓存行当样例 (每个变量都渲染得出来), 三界面各渲染
    一行 —— 渲染单一源在服务端, 前端只搬运不重抄。"""
    save_place_name(owndb, place_name_row(1, "ok", 3, "残行",
                                          district="南山区"))  # 组件缺: 不挑它
    save_place_name(owndb, place_name_row(
        2, "ok", 3, "万象天地", province="广东省", city="深圳市",
        district="南山区",
        fields=PlaceFields(township="粤海街道", street="深南大道",
                           number="88号", poi="万象城")))
    d = auth.post(TAPI + "/preview",
                  json={"trips": "{市}{区}", "charging": "{POI}",
                        "places": "{镇}"}).json()
    assert d == {"sample": "万象天地", "trips": "深圳市南山区",
                 "charging": "万象城", "places": "粤海街道"}


def test_place_templates_preview_without_rows(auth, owndb):
    """还没跑过命名: 预览没原料, 样例空 (前端转「暂无样例」提示)。"""
    d = auth.post(TAPI + "/preview",
                  json={"trips": "{区}", "charging": "", "places": ""}).json()
    assert d == {"sample": "", "trips": "", "charging": "", "places": ""}


# ---------------------------------------------------------------- 三张消费面
def _save_full(owndb, addr_id=1):
    """地址 1 的组件齐全缓存行 (三张消费面共用)。"""
    save_place_name(owndb, place_name_row(
        addr_id, "ok", 3, "万象天地", province="广东省", city="深圳市",
        district="南山区",
        fields=PlaceFields(township="粤海街道", street="深南大道",
                           number="88号", poi="万象城")))


def test_trips_list_renders_place_template(auth, db, owndb):
    """行程起终点: 模板整行进 from_place/to_place (空 = None, 前端走本地
    拼装); 没缓存行的那头照旧 None。"""
    seed_addresses(db)          # 1=深圳南山(起), 2=东莞长安(终)
    seed_drive(db, id=1)
    _save_full(owndb)
    it = auth.get("/tesla/trips/api/sessions").json()["items"][0]
    assert it["from_place"] is None and it["to_place"] is None   # 没模板不套
    auth.post(TAPI, json={"trips": "{区} · {POI}", "charging": "", "places": ""})
    it = auth.get("/tesla/trips/api/sessions").json()["items"][0]
    assert it["from_place"] == "南山区 · 万象城"
    assert it["to_place"] is None          # 终点没缓存行: 渲染空回退默认


def test_charging_place_template_and_geofence_wins(auth, db, owndb):
    """充电地点: 模板整行进 place; 围栏名 (家/公司) 是用户手定的, 有它就
    不套; 详情与列表同口径。"""
    seed_addresses(db)
    db.add(Geofence(id=1, name="家"))
    seed_charging(db, id=1)                                   # 09-07, 无围栏
    seed_charging(db, id=2, geofence_id=1,
                  start_date=datetime(2026, 9, 8, 10, 0),
                  end_date=datetime(2026, 9, 8, 12, 0))
    _save_full(owndb)
    auth.post(TAPI, json={"trips": "", "charging": "{区} · {POI}", "places": ""})
    by_id = {i["id"]: i
             for i in auth.get("/tesla/charging/api/sessions").json()["items"]}
    assert by_id[1]["place"] == "南山区 · 万象城"
    assert by_id[2]["place"] is None and by_id[2]["location"] == "家"
    assert auth.get("/tesla/charging/api/sessions/1").json()["place"] \
        == "南山区 · 万象城"          # 详情同口径


def test_locations_template_display_only(auth, db, owndb):
    """常用地点: 组名套模板只动显示层 —— raws/details (改名/管理键) 照旧
    raw 名; 别名 (用户起的名) 不套; 删除按屏幕行名 (渲染名) 隐整组。"""
    db.add(Address(id=1, name="华为立体车库",
                   display_name="广东省深圳市龙岗区",
                   latitude=22.61, longitude=114.06))
    seed_drive(db, id=1, start_address_id=1, end_address_id=None)
    seed_drive(db, id=2, start_address_id=1, end_address_id=None,
               start_date=datetime(2026, 9, 11, 2, 0),
               end_date=datetime(2026, 9, 11, 3, 0))
    _save_full(owndb)
    auth.post(TAPI, json={"trips": "", "charging": "", "places": "{区} · {POI}"})
    assert auth.get(LOCS).json() == [
        {"name": "南山区 · 万象城", "trips": 2, "lat": 22.61, "lng": 114.06,
         "raws": ["万象天地"], "orig": None,
         "spots": [{"lat": 22.61, "lng": 114.06}],
         "details": [{"name": "万象天地", "trips": 2,
                      "lat": 22.61, "lng": 114.06}]}]
    # 别名赢过模板: 用户起的名不在缓存里, 天然不套 (raws 照旧是改名键)
    auth.post("/tesla/trips/api/stats/place-alias",
              json={"places": ["万象天地"], "alias": "我的地库"})
    locs = auth.get(LOCS).json()
    assert locs[0]["name"] == "我的地库" and locs[0]["raws"] == ["万象天地"]
    auth.post("/tesla/trips/api/stats/place-alias",
              json={"places": ["万象天地"], "alias": ""})     # 还原
    # 删除送的是屏幕行名 (渲染名): 命中隐整组
    auth.post("/tesla/trips/api/stats/place-hide",
              json={"places": ["南山区 · 万象城"], "hidden": True})
    assert auth.get(LOCS).json() == []


# ---------------------------------------------------------------- 设置页接线
def test_place_template_card_wiring(auth):
    """设置页「地点显示」卡: 三界面输入框 (80 字上限) + 变量说明 + 预览块 +
    保存钮; JS 走专用端点, 输入停 300ms 防抖预览, 进页现拉现值, 三张列表
    卡优先吃服务端渲染行。"""
    page = served_page(auth, "/tesla")
    for frag in ('id="ptpl-card"', "<h2>地点显示</h2>",
                 'id="ptpl-trips"', 'id="ptpl-charging"', 'id="ptpl-places"',
                 'maxlength="80"', 'class="ptpl-vars"', 'id="ptpl-preview"',
                 'id="ptpl-save"',
                 "{省} {市} {区} {镇} {路} {门牌} {POI} {名字} {推荐}",
                 "整条留空 = 默认显示"):
        assert frag in page, f"地点显示卡缺少 {frag}"
    for frag in ('getJSON("/tesla/api/place-templates")',
                 '"/tesla/api/place-templates/preview"',
                 "setTimeout(ptplPreview, 300)",
                 "地点显示已保存",
                 "it.from_place || shortPlace(it.from_region",     # 行程卡
                 "it.from_place || gtrShortPlace(it.from_region",  # 分组明细卡
                 "if (it.place) return [it.place];"):              # 充电卡
        assert frag in page, f"地点显示接线缺少 {frag}"
