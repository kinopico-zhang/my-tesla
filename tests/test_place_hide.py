"""常用地点删除/恢复测试 (2026-10-03 #172 用户点名「点击一个地点, 要展开
这个地点所有的真实地点, 用户可以用左滑删除按钮删除, 常用地点本身也要
支持删除」; 2026-10-04 #173 展开班交组详情层): hidden_places 自有表 +
locations 读侧过滤 (隐 raw 该地址停车不计数、组次数随之缩 / 隐组显示名
整组不回 / 组内 raw 全隐组自然消失) + POST place-hide / GET place-hidden
往返 + 管理页/组详情层前端钉 (左滑删除件 / 已删除恢复区)。行程数据从头
到尾不动 —— 删除只是统计视图的开关。"""
from datetime import datetime

from app.tesla.models import Address, HiddenPlace
from tests.seed_factories import seed_drive

API = "/tesla/trips/api/stats/locations"
HIDE = "/tesla/trips/api/stats/place-hide"
HIDDEN = "/tesla/trips/api/stats/place-hidden"
ALIAS = "/tesla/trips/api/stats/place-alias"


def _seed(db):
    """与 test_place_alias 同款种子: 地址 1=华为立体车库 (走 2 次),
    2=同地旧名 (别名并组用), 3=长安镇。行程 1/2 起点地址 1, 行程 3 起点
    地址 2, 行程 4 起点地址 3 (都断链, 起点各计一次)。"""
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


def _hide(auth, places, hidden=True):
    r = auth.post(HIDE, json={"places": places, "hidden": hidden})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_hide_raw_shrinks_group(auth, db, owndb):
    """隐 raw 原名: 该地址停车不再计数, 组次数缩 (3→1), 剩下的 raw 照留
    (raws/details/坐标都对账); 隐藏行落库, 恢复区名单见它。"""
    _seed(db)
    auth.post(ALIAS, json={"places": ["华为立体车库", "华为旧车库"],
                           "alias": "公司"})
    _hide(auth, ["华为立体车库"])
    assert _locs(auth) == [
        {"name": "公司", "trips": 1, "lat": 22.62, "lng": 114.07,
         "raws": ["华为旧车库"], "orig": "华为旧车库", "spots": [{"lat": 22.62, "lng": 114.07}],
         "details": [{"name": "华为旧车库", "trips": 1,
                      "lat": 22.62, "lng": 114.07}]},
        {"name": "长安镇", "trips": 1, "lat": 22.82, "lng": 113.75,
         "raws": ["长安镇"], "orig": None, "spots": [{"lat": 22.82, "lng": 113.75}],
         "details": [{"name": "长安镇", "trips": 1,
                      "lat": 22.82, "lng": 113.75}]},
    ]
    assert auth.get(HIDDEN).json() == ["华为立体车库"]
    assert owndb.query(HiddenPlace).count() == 1


def test_hide_group_name_hides_whole(auth, db, owndb):
    """隐组显示名: 整组不回 (别名并组后删的正是显示名「公司」), 组员
    raws 一个都没动 —— 别的组也不受牵连。"""
    _seed(db)
    auth.post(ALIAS, json={"places": ["华为立体车库", "华为旧车库"],
                           "alias": "公司"})
    _hide(auth, ["公司"])
    assert [g["name"] for g in _locs(auth)] == ["长安镇"]
    assert auth.get(HIDDEN).json() == ["公司"]
    assert owndb.query(HiddenPlace).count() == 1


def test_hide_all_raws_group_gone(auth, db):
    """组内 raw 全隐: 组自然消失 (不靠隐藏组名那行), 别名行原样留着
    (恢复任一 raw 组就回来)。"""
    _seed(db)
    _hide(auth, ["华为立体车库", "华为旧车库"])
    assert [g["name"] for g in _locs(auth)] == ["长安镇"]
    assert auth.get(HIDDEN).json() == ["华为旧车库", "华为立体车库"]


def test_restore_roundtrip(auth, db, owndb):
    """恢复 = 删隐藏行: 名单消, 统计原样回来, 库里无残留。"""
    _seed(db)
    _hide(auth, ["长安镇"])
    assert [g["name"] for g in _locs(auth)] == ["华为立体车库", "华为旧车库"]
    _hide(auth, ["长安镇"], hidden=False)
    assert auth.get(HIDDEN).json() == []
    assert owndb.query(HiddenPlace).count() == 0
    assert len(_locs(auth)) == 3


def test_place_hide_validation(auth, db):
    """422 防线: places 空列表 (前端单名一单, 这里只钉接口闸)。"""
    _seed(db)
    assert auth.post(HIDE, json={"places": []}).status_code == 422


# ---------------------------------------------------------------- 前端钉
def test_management_page_frontend(auth, db):
    """管理页 + 组详情层钉 (3.4.1): 点组行开 #placed-sheet (上地图下真实地
    点列表, 点行 setZoomAndCenter 跳那 + 选中高亮) + 左滑删除件 (壳级脚本
    在两页之前) + 已删除恢复区 (#plc-hid-list) + 红钮原生 confirm 二次确认
    (2026-10-04 用户报武装式没看见「点好多次才删掉」, 改回 music 路线)。
    v5 (同日用户点名): 组行删除 = 解除编组 —— 删除走改名接口空 alias 还原路
    (place-alias, places: row.raws), 不再 place-hide 藏整组; place-hide 在管
    理页只剩恢复区那条。v6 (同日): 行上常显改名钮退役, 左滑露出操作面板
    (编辑; 改过名的组 + 删除), 横线钉到 .plc-item 层 (v5 换行结构时裸行
    丢了横线的回修)。驾驶员页同日跟进左滑三钮: 面板规则共用 .swipe-list
    (css v13 rescop), 驾驶员那半边钉在 test_settings。v7 (2026-10-05 用户
    点名「编辑按钮去掉, 单击打开的界面就可以编辑名称」+「响应速度太慢,
    改成异步」): 行上编辑钮退役 (改名住详情层标题行 #placed-rename, 没
    改过名的组行连左滑面板都不挂), 加载异步化 (首拉加载态 / 签名没变不
    重铺 / 分批铺 80 根一批)。v8 (同日晚「改名没必要再弹一个框, 直接把
    textbox 改成 inputbox」): 标题就地翻输入框 (#placed-input, 驾驶员行内
    改名同款) + 保存/取消; Enter 存, Esc 弃编辑。v9 同批: 提示行整行退役。
    v10 (2026-10-05 晚用户点名「常用地点左滑删除去掉吧…重命名的点开后
    最下面加红色删除钮, 点击删除, 需要二次确认」+「不显示原名, 显示是几
    个地点的汇总」): 管理页行上左滑整链退役 (#plc-list 摘 .swipe-list,
    解除编组删除搬进详情层底部红钮 #placed-del), 原名行退役改「N 个地点
    的汇总」(.plc-sum, 单点组不带小字)。
    v11 (2026-10-06 用户点名「不从底下弹窗, 而是从右侧滑入窗口, 全屏,
    弹出后, 在屏幕左侧滑动推出。弹入弹出要有动画效果, 要跟手」): 详情层
    改全屏右滑页 —— 蒙版 (#placed-backdrop)/把手/整片下拉收层退役,
    translateX(100%) 藏 / show 滑入, 左缘 .placed-edge 竖条 + 返回钮
    (#placed-back) 右拖跟手推出 (bindPlacedDrag)。
    v12 (同日用户点名「地图下面的地点列表太丑了」): 列表行改圆角小卡
    (surface 面 12px 圆角, 8px 间隔, 按下深一档, 选中描蓝边), 次数挪出
    名字块到右缘同行 (单行卡); 顺手补上 wrap 漏关的 </div> —— 块流年代
    3.4.1 起各 wrap 俄套着, flex+gap 只认直接子孩, 一漏间隔全丢。v21
    (同日 v20 自伤回修): 列表改 flex 容器后 wrap 吃默认 flex-shrink, 卡
    多了硬塞列表高每张压成 21px 半截卡 (行只顶上 21px 可命中, 左滑起手
    落在容器上永远 engage 不了 —— 浏览器验证逐点扫描抓到), wrap 加
    flex: none 叫停收缩, 超出交 overflow-y 滚。
    """
    page = auth.get("/tesla/app", follow_redirects=True).text
    for token in ('id="plc-hid-sec"', 'id="plc-hid-list"',
                  "tesla-settings.css?v=22",
                  'id="placed-sheet"', 'class="placed-edge"',
                  'id="placed-back"', 'id="placed-title"', 'id="placed-rename"',
                  'id="placed-input"', 'id="placed-cancel"',
                  'id="placed-map"', 'id="placed-list"',
                  'id="plc-loading"', '<div id="plc-list"></div>',
                  'id="placed-foot"', 'class="placed-del" id="placed-del"',
                  "trips-place-detail.js?v=11"):
        assert token in page, f"管理页缺 {token}"
    assert 'id="placed-backdrop"' not in page, "蒙版随右滑全屏页退役"
    # 管理页长提示段整段退役 (2026-10-04 用户点名删): 行为说明住更新日志,
    # 页面只留列表。负钉防回潮 —— 这词唯此一段, 不撞别处 (弹层/详情层各有
    # 自己的短 hint, 不在撤编之列)。卡里的小标题「常用地点管理」同日点名
    # 删掉 (负钉钉标签形态: 文件头注释里还有这词, 裸串会误伤)
    assert "删除即解除编组" not in page
    assert "<h2>常用地点管理</h2>" not in page
    assert "左滑可删除" not in page   # 详情层提示行 v9 退役 (唯此一段, 注释「左滑删 raw」不同串)
    assert page.index("tesla-swipe-delete.js?v=4") < \
        page.index("trips-place-detail.js?v=11") < \
        page.index("settings-places.js?v=8")
    plc = auth.get("/tesla/static/js/view/settings-places.js").text
    for frag in ('sendJSON("/tesla/trips/api/stats/place-hide"',  # 只剩恢复区
                 '"/tesla/trips/api/stats/place-hidden"',
                 "plc-restore",
                 # v10: 行不显示原名, 并进多处的组报「N 个地点的汇总」
                 'class="plc-sum"', "个地点的汇总",
                 # v7 异步化: 代际防串台 / 首拉加载态 / 签名没变不重铺 / 分批铺
                 "const gen = ++plcGen;", '$("#plc-loading")',
                 "JSON.stringify(all)", "requestAnimationFrame(step)"):
        assert frag in plc, f"管理页脚本缺 {frag}"
    # v10 左滑整链退役: 行上没有滑出面板, 也没有原名行 (负钉防回潮)
    for gone in ("bindSwipeDelete", "swipe-actions", "swipe-wrap", "plc-orig"):
        assert gone not in plc, f"管理页左滑/原名残党 {gone}"
    det = auth.get("/tesla/static/js/view/trips-place-detail.js").text
    for frag in ("/* exported openPlaceDetail, closePlaceDetail */",
                 "function openPlaceDetail(row, onChanged)",
                 "placedRow.details", "mapLib.gcj(",
                 "setZoomAndCenter(16", 'class="place-pin',
                 'bindSwipeDelete($("#placed-list")',
                 'sendJSON("/tesla/trips/api/stats/place-hide"',
                 "window.confirm(`删除「", "ViewportDoctor.settled()",
                 # v11 右滑全屏页: 左缘条 + 返回钮跟手推出, 蒙版/把手退役
                 "function bindPlacedDrag(els, onClose)",
                 'bindPlacedDrag(document.querySelectorAll("#placed-sheet .placed-edge, #placed-back")',
                 '$("#placed-back").addEventListener("click", closePlaceDetail)',
                 "sheet.style.transform = `translateX(${dx}px)`",
                 "if (dx > w / 3 || (vx > 0.5 && dx > 20)) onClose();",
                 "sheet.classList.add(\"dragging\")",
                 # v12 行卡: 次数挪出名字块, 名字/次数各归一格; wrap 双 </div>
                 # 关牢 (漏关会俄套, flex+gap 只认直接子孩)
                 '`<span class="placed-name">${esc(d.name)}</span>`',
                 '`<span class="plc-n">${d.trips} 次</span>`',
                 '删除</button></div></div>`',
                 "async function placedSave()", "val === placedRow.name",
                 'if (!$("#placed-input").hidden) placedExitEdit()',
                 '$("#placed-rename")',
                 # v10 底部红钮: 解除编组从管理页左滑搬来, 只给改过名的组
                 '$("#placed-foot").hidden = placedRow.raws.includes(placedRow.name)',
                 '$("#placed-del").addEventListener("click"',
                 'places: placedRow.raws, alias: ""',
                 "window.confirm(`删除常用地点「",
                 "if (placedChanged) await placedChanged();"):
        assert frag in det, f"组详情层缺 {frag}"
    for gone in ("placed-backdrop", 'bindSheetDrag($(', 'e.stopPropagation()'):
        assert gone not in det, f"底部弹窗残党 {gone}"
    swipe = auth.get("/tesla/static/js/tesla-swipe-delete.js").text
    for frag in ("/* exported bindSwipeDelete */", "const SWIPE_REVEAL = 72",
                 "function swipePanel(wrap)",   # v3: 面板缺省回退单钮 (详情层)
                 'closest(".swipe-del, .swipe-edit")',   # 双钮分派
                 "setPointerCapture",
                 "if (wrap.isConnected) setSwipeTransform(wrap, 0);"):
        assert frag in swipe, f"左滑删除件缺 {frag}"
    css = auth.get("/tesla/static/css/tesla-settings.css").text
    # 左滑家族 scoped 到 .swipe-list (v13: 驾驶员页共用) —— v10 起地点管理页
    # 不挂这个类, 消费只剩 #drv-list; 三钮宽档 w3 (216, 驾驶员) —— 双钮档
    # w2 (144) 随地点行编辑钮退役 (v14) 没有消费者了
    for frag in (".swipe-list .swipe-wrap {", ".swipe-list .swipe-del {",
                 ".swipe-list .swipe-actions {", ".swipe-list .swipe-edit {",
                 ".swipe-list .swipe-wrap.w3::after { right: 216px; }",
                 ".plc-item { border-bottom: 1px solid var(--hairline); }",
                 ".plc-hid-row {", "pointer-events: none",
                 ".plc-n { display: block;", ".plc-sum {",
                 # v11 全屏右滑页: 四边钉死 + translateX(100%) 藏, 左缘条/
                 # 窄柱/返回钮, 拖拽跟手关动画
                 "#placed-sheet {", "#placed-sheet.show { transform: none; }",
                 "#placed-sheet.dragging { transition: none; }",
                 "#placed-sheet .placed-edge {", "#placed-sheet .placed-in {",
                 "#placed-sheet .placed-back {",
                 # v12 行卡: 圆角小卡 + 8px 间隔, 按下深一档, 选中描蓝边,
                 # 次数右缘单行
                 "flex-direction: column; gap: 8px;",
                 ".placed-row:active { background: var(--surface-2); }",
                 ".placed-row.on { box-shadow: inset 0 0 0 1.5px rgba(57,135,229,.5); }",
                 "#placed-list .plc-n { flex: none; margin: 0; }",
                 # v21: wrap 不收缩 (flex 容器默认 shrink 压半截卡, 见上)
                 "#placed-list .swipe-wrap { position: relative; overflow: hidden;"
                 " border-radius: 12px; flex: none; }",
                 "#placed-sheet .placed-head {", ".plc-loading {",
                 "#placed-map {", "#placed-list {",
                 "#placed-list .swipe-del {", ".placed-row {",
                 ".placed-row.on .placed-name", ".place-pin.sel::after",
                 "#placed-sheet .placed-foot {", "#placed-sheet .placed-del {"):
        assert frag in css, f"管理页样式缺 {frag}"
    assert ".swipe-wrap.w2::after" not in css, "双钮档 w2 已随编辑钮退役"
    assert ".plc-orig" not in css, "原名行样式已随「显示汇总」退役"
    for gone in ("#placed-backdrop", "#placed-sheet .grab"):
        assert gone not in css, "底部弹窗基座残党 " + gone
