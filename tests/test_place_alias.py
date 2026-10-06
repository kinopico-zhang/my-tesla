"""常用地点改名测试 (2026-09-30 用户点名「点击地点名称弹出修改地点名称
对话框…用户可以给地点进行重命名。同时在设置页面上也加一个常用地点管理」):
place_aliases 自有表 + locations 接口的别名并组/坐标/raws 口径 + POST 改名
接口往返 + 弹层/管理页前端钉 (新文件的 ?v= 版本钉也住这, test_asset_versions
已顶到 200 行硬上限)。"""
from datetime import datetime

from app.tesla.models import Address, PlaceAlias
from tests.seed_factories import seed_drive

API = "/tesla/trips/api/stats/locations"
POST = "/tesla/trips/api/stats/place-alias"


def _seed(db):
    """带坐标的地址: 1=华为立体车库 (南山, 走 3 次), 2=同车库旧名 (并组用),
    3=长安镇。行程 1/2 起点地址 1, 行程 3 起点地址 2 (最近的华为出现),
    行程 4 起点地址 3。"""
    db.add(Address(id=1, name="华为立体车库", display_name="广东省深圳市龙岗区",
                   latitude=22.61, longitude=114.06))
    db.add(Address(id=2, name="华为旧车库", display_name="广东省深圳市龙岗区",
                   latitude=22.62, longitude=114.07))
    db.add(Address(id=3, name="长安镇", display_name="广东省东莞市长安镇",
                   latitude=22.82, longitude=113.75))
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


def _locs(auth):
    return auth.get(API).json()


def test_place_alias_merge_and_coords(auth, db, owndb):
    """别名并组: 两处原名改成同名 → 一根柱; 组坐标 = 组内次数最多原名的
    最近一次出现 (rows 按出发升序后写覆盖 → 行程 1 的地址 1 坐标); raws
    按次数降序带上并组原名 (改名接口的键); orig = 组里被改过名的最常原名
    (2026-10-04 天玑公馆撞名组实锤后后端点名, 前端不再自己猜)。"""
    _seed(db)
    assert _locs(auth) == [
        {"name": "华为立体车库", "trips": 2, "lat": 22.61, "lng": 114.06,
         "raws": ["华为立体车库"], "orig": None, "spots": [{"lat": 22.61, "lng": 114.06}],
         "details": [{"name": "华为立体车库", "trips": 2,
                      "lat": 22.61, "lng": 114.06}]},
        {"name": "华为旧车库", "trips": 1, "lat": 22.62, "lng": 114.07,
         "raws": ["华为旧车库"], "orig": None, "spots": [{"lat": 22.62, "lng": 114.07}],
         "details": [{"name": "华为旧车库", "trips": 1,
                      "lat": 22.62, "lng": 114.07}]},
        {"name": "长安镇", "trips": 1, "lat": 22.82, "lng": 113.75,
         "raws": ["长安镇"], "orig": None, "spots": [{"lat": 22.82, "lng": 113.75}],
         "details": [{"name": "长安镇", "trips": 1,
                      "lat": 22.82, "lng": 113.75}]},
    ]
    # 两个原名改成同一个「公司」: 并组次数 3, 坐标跟次数最多的原名走;
    # spots 把组内各原名的坐标全录 (弹层小地图多点标记)
    r = auth.post(POST, json={"places": ["华为立体车库", "华为旧车库"],
                              "alias": "公司"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _locs(auth) == [
        {"name": "公司", "trips": 3, "lat": 22.61, "lng": 114.06,
         "raws": ["华为立体车库", "华为旧车库"], "orig": "华为立体车库",
         "details": [{"name": "华为立体车库", "trips": 2,
                      "lat": 22.61, "lng": 114.06},
                     {"name": "华为旧车库", "trips": 1,
                      "lat": 22.62, "lng": 114.07}],
         "spots": [{"lat": 22.61, "lng": 114.06}, {"lat": 22.62, "lng": 114.07}]},
        {"name": "长安镇", "trips": 1, "lat": 22.82, "lng": 113.75,
         "raws": ["长安镇"], "orig": None, "spots": [{"lat": 22.82, "lng": 113.75}],
         "details": [{"name": "长安镇", "trips": 1,
                      "lat": 22.82, "lng": 113.75}]},
    ]
    # raws 原样回传是改名键: 行程统计柱名/管理页改名钮都靠它续改
    assert owndb.query(PlaceAlias).count() == 2


def test_place_alias_restore_and_rematch(auth, db, owndb):
    """空 alias = 删行还原原名; 别名撞上另一处原名也算并组 (两处合成一根
    柱, 撞名那侧的次数合过来)。"""
    _seed(db)
    auth.post(POST, json={"places": ["华为立体车库"], "alias": "长安镇"})
    assert _locs(auth) == [
        {"name": "长安镇", "trips": 3, "lat": 22.61, "lng": 114.06,
         "raws": ["华为立体车库", "长安镇"], "orig": "华为立体车库",
         "details": [{"name": "华为立体车库", "trips": 2,
                      "lat": 22.61, "lng": 114.06},
                     {"name": "长安镇", "trips": 1,
                      "lat": 22.82, "lng": 113.75}],
         "spots": [{"lat": 22.61, "lng": 114.06}, {"lat": 22.82, "lng": 113.75}]},
        {"name": "华为旧车库", "trips": 1, "lat": 22.62, "lng": 114.07,
         "raws": ["华为旧车库"], "orig": None, "spots": [{"lat": 22.62, "lng": 114.07}],
         "details": [{"name": "华为旧车库", "trips": 1,
                      "lat": 22.62, "lng": 114.07}]},
    ]
    # 还原: 空 alias 删行, 两处原名各回各的柱
    auth.post(POST, json={"places": ["华为立体车库"], "alias": ""})
    assert _locs(auth) == [
        {"name": "华为立体车库", "trips": 2, "lat": 22.61, "lng": 114.06,
         "raws": ["华为立体车库"], "orig": None, "spots": [{"lat": 22.61, "lng": 114.06}],
         "details": [{"name": "华为立体车库", "trips": 2,
                      "lat": 22.61, "lng": 114.06}]},
        {"name": "华为旧车库", "trips": 1, "lat": 22.62, "lng": 114.07,
         "raws": ["华为旧车库"], "orig": None, "spots": [{"lat": 22.62, "lng": 114.07}],
         "details": [{"name": "华为旧车库", "trips": 1,
                      "lat": 22.62, "lng": 114.07}]},
        {"name": "长安镇", "trips": 1, "lat": 22.82, "lng": 113.75,
         "raws": ["长安镇"], "orig": None, "spots": [{"lat": 22.82, "lng": 113.75}],
         "details": [{"name": "长安镇", "trips": 1,
                      "lat": 22.82, "lng": 113.75}]},
    ]
    assert owndb.query(PlaceAlias).count() == 0


def test_place_alias_validation(auth, db):
    """422 防线: places 空列表 / alias 超 60 字 (前端 maxlength 同口径;
    60 = 下拉能领进的原始地址链长度, 2026-10-02 从 30 放宽)。"""
    _seed(db)
    assert auth.post(POST, json={"places": [], "alias": "x"}).status_code == 422
    assert auth.post(POST, json={"places": ["a"],
                                 "alias": "超" * 61}).status_code == 422


# ---------------------------------------------------------------- 前端钉
def test_place_dialog_and_settings_page(auth, db):
    """改名弹层 (壳级 sheet: 把手 + 输入框 + 位置小地图) + 设置页常用地点管理
    + 柱名/柱身点击接线 + 新脚本 ?v= (版本钉住这, test_asset_versions 顶着
    上限)。弹层基座是 scoped 规则 (壳里没有裸 .sheet 家族规则, 首版漏写
    整组基座成过页面底部裸内容 —— 2026-09-30 当晚实测补齐, 这里钉住不再
    漏)。"""
    page = auth.get("/tesla/app", follow_redirects=True).text
    for token in ('id="place-backdrop"', 'id="place-sheet"',
                  'id="place-hint"', 'id="place-input"', 'maxlength="60"',
                  'id="place-down"', 'id="place-pops"',
                  'id="place-save"', 'id="place-map"',
                  'data-view="settings-places"', 'id="plc-scroll"',
                  'id="plc-list"', 'id="plc-empty"',
                  "<h2>常用地点</h2>", "trips-place-dialog.js?v=7",
                  "trips-place-detail.js?v=11", "settings-places.js?v=8"):
        assert token in page, f"常用地点前端缺 {token}"
    # 脚本序: 弹层在壳级拖拽件之后 (bindSheetDrag 是它的依赖)。弹层只剩
    # 行程统计柱名/柱身一个入口 (2026-10-05 晚详情层改名改内联输入后,
    # 没有谁再运行时叠它); 组详情层在左滑删除件之后 (bindSwipeDelete,
    # 详情层行上还在用) 且在管理页之前 (openPlaceDetail 是它的依赖),
    # 管理页殿后。
    assert page.index("tesla-sheet-drag.js") < page.index("trips-place-dialog.js?v=7")
    assert page.index("tesla-swipe-delete.js?v=4") < \
        page.index("trips-place-detail.js?v=11") < \
        page.index("settings-places.js?v=8")
    js = auth.get("/tesla/static/js/view/trips-place-dialog.js").text
    for frag in ("function openPlaceDialog(row, onSaved)",
                 "function placeLoadNames()", "function placePopsShow()",
                 'class="pp-item"',
                 'addEventListener("pointerdown"',   # 点外收走 pointerdown (地图画布吞 click)
                 'sendJSON("/tesla/trips/api/stats/place-alias"',
                 "places: placeRow.raws",
                 "mapLib.gcj([s.lng, s.lat])",
                 "placeMap.setFitView(placeMarkers, false, [36, 36, 36, 36])",
                 'content: \'<div class="place-pin"></div>\'',   # 位置标出来
                 "ViewportDoctor.settled()",
                 'bindSheetDrag($("#place-sheet")',
                 '$("#place-input").addEventListener("keydown"',
                 "if (cb) cb(ali);"):   # v6: 存完带新名回传 (详情层按它续开)
        assert frag in js, f"改名弹层缺 {frag}"
    plc = auth.get("/tesla/static/js/view/settings-places.js").text
    for frag in ("openPlaceDetail(row,", 'registerView("settings-places"',
                 'title: "常用地点"',
                 # v8 (2026-10-05 晚): 原名行退役, 并进多处的组报「N 个地点
                 # 的汇总」; 回调带 hint (存下的新名), 删点路不带按旧名找
                 "个地点的汇总",
                 "plcRows.find(r => r.name === (hint ?? row.name)) || null"):
        assert frag in plc, f"管理页缺 {frag}"
    css = auth.get("/tesla/static/css/tesla-settings.css").text
    # 弹层基座整组 (固定底板/105% 藏/show 滑入) + 把手 + 位置圆点 + 管理行
    for frag in ("#place-sheet {", "transform: translateY(105%);",
                 "#place-sheet.show { transform: none; }",
                 "#place-sheet .grab", ".plc-row {", "#place-map {",
                 "#place-down {", "#place-pops {", "height: min(52vh, 430px)",
                 ".place-pin::after"):
        assert frag in css, f"弹层样式缺 {frag}"
    # 设置组导航 + 图标 (DRW_ICONS 对账在 test_drawer, 这里钉存在)
    drw = auth.get("/tesla/static/js/tesla-drawer.js").text
    assert '"settings-places": "<path' in drw
