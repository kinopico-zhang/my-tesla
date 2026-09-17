"""充电地点筛选测试: 省市区级联端点与会话过滤, 时间菜单日历,
弹层把手, 费用筛选菜单。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime

from app.tesla.models import Address
from tests.seed_factories import seed_addresses, seed_charge, seed_charging
from tests.charging_page_scripts import CHARGING_ASSETS, _page_scripts

# ---------------------------------------------------------------- 地点筛选
def test_charging_regions_endpoint(auth, db):
    """充电地点省市区三级树 (每级按次数降序); 解析不出省的地址不进树。

    覆盖两种 display_name: 连写 "广东省深圳市龙岗区坂田街道" 与 OSM 逗号链。
    """
    db.add(Address(id=3, name="无名地", city=None, display_name="某处"))
    db.add(Address(id=4, name="翠湖边", city=None,
                   display_name="翠湖西路, 华山街道, 五华区, 昆明市, 云南省, 650031, 中国"))
    db.commit()
    seed_addresses(db)                       # 1=深圳市龙岗区 2=东莞市长安镇
    seed_charging(db, id=1, address_id=1)
    seed_charging(db, id=2, address_id=1)
    seed_charging(db, id=3, address_id=2)
    seed_charging(db, id=4, address_id=4)    # 云南 (OSM 逗号链, 带邮编带中国)
    seed_charging(db, id=5, address_id=3)    # 解析不出省 → 不进树
    assert auth.get("/tesla/charging/api/regions").json() == [
        {"name": "广东省", "count": 3, "children": [
            {"name": "深圳市", "count": 2, "children": [
                {"name": "龙岗区", "count": 2, "children": []}]},
            {"name": "东莞市", "count": 1, "children": [
                {"name": "长安镇", "count": 1, "children": []}]}]},
        {"name": "云南省", "count": 1, "children": [
            {"name": "昆明市", "count": 1, "children": [
                {"name": "五华区", "count": 1, "children": []}]}]}]


def test_charging_sessions_filters_by_region(auth, db):
    """地点筛选: 省/市/区县逐级精确 ("/" 路径 1~3 段), 可与快慢充叠加。"""
    db.add(Address(id=3, name="无名地", city=None, display_name="某处"))
    db.commit()
    seed_addresses(db)
    seed_charging(db, id=1, address_id=1)    # 深圳 慢充 (无采样 → 非快充)
    seed_charging(db, id=2, address_id=1,
                  start_date=datetime(2026, 9, 8, 15, 50),
                  end_date=datetime(2026, 9, 8, 23, 2))
    seed_charge(db, 2, date=datetime(2026, 9, 8, 16, 0))   # 深圳 快充
    seed_charging(db, id=3, address_id=2,    # 东莞 慢充 (日期再早一档, 排序确定)
                  start_date=datetime(2026, 9, 6, 15, 50),
                  end_date=datetime(2026, 9, 6, 23, 2))
    seed_charging(db, id=4, address_id=3)    # 解析不出省 → 只在全列表出现

    def ids(**params):
        return [i["id"] for i in auth.get(
            "/tesla/charging/api/sessions", params=params).json()["items"]]

    assert ids(region="广东省") == [2, 1, 3]             # 省: 全省
    assert ids(region="广东省/深圳市") == [2, 1]         # 市
    assert ids(region="广东省/深圳市/龙岗区") == [2, 1]  # 区县
    assert ids(region="广东省/东莞市") == [3]
    assert ids(region="云南省") == []
    assert ids(region="广东省/深圳市", type="fast") == [2]
    assert auth.get("/tesla/charging/api/sessions",
                    params={"region": "省/市/区/街道"}).status_code == 400  # 最多 3 段


def test_charging_page_time_menu_calendar_and_region_filter(auth):
    """顶栏时间下拉 (快捷档 + 自定义日历) + 筛选行省市区级联, 筛选写进 URL。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    for frag in ['id="time-menu"', 'data-v="24h"', 'data-v="7d"', 'data-v="30d"',
                 'data-v="180d"', 'data-v="1y"', 'data-v="all"',
                 'data-v="custom"', 'id="tm-cal"', 'id="tm-prev"', 'id="tm-next"',
                 'id="tm-ym"', 'id="tm-sel"', 'id="tm-apply"', 'function calRender()',
                 '再点结束日期',
                 # 时间菜单在顶栏 nav-row (全站统一位置; 本页品牌旁还有车名胶囊)
                 '<span class="car-pill" id="car-pill">Tesla</span>\n'
                 '    <details class="nav-menu time-menu" id="time-menu">',
                 'id="loc-menu"', 'id="loc-opts"', "/tesla/charging/api/regions",
                 # 地点省市区级联 (行程页同款): 钻取行/返回行/面包屑/限高滚动
                 'class="menu loc-menu"', 'class="loc-back"', 'class="loc-crumb"',
                 '<button class="loc-row', "const locParam = () =>", "钻下一级",
                 # 快充/慢充筛选改下拉 (与地点筛选同款, 分段钮太占地方)
                 'id="type-menu"', 'id="type-opts"', 'id="type-lb"',
                 'data-v="fast"', "⚡ 快充", "🔌 慢充", "TYPE_LABELS",
                 '$("#type-opts").addEventListener',
                 "function syncURL()", 'u.searchParams.set("region", state.region)',
                 # 手机: 下拉面板锚全宽 header (日历行 ~300px, 挂胶囊右缘必出屏)
                 '@media (max-width: 479px)', '.nav-menu { position: static; }']:
        assert frag in html, f"充电页缺少 {frag}"
    assert "chips-range" not in html and 'id="tm-from"' not in html
    assert 'id="seg-type"' not in html and ".seg {" not in html   # 分段钮样式不许回来
    for i in ('time-menu', 'time-lb', 'time-opts', 'tm-dates', 'tm-cal', 'tm-prev',
              'tm-next', 'tm-ym', 'tm-sel', 'brand-menu', 'logout', 'loc-opts',
              'type-opts'):
        assert html.count(f'id="{i}"') == 1, f"页面 {i} 重复"
    # 筛选行太宽时手机端自己横滑, 不把整个页面带着滑 (下拉锚在 header 不受裁)
    assert ".filters { overflow-x: auto; scrollbar-width: none; }" in html
    assert ".filters::-webkit-scrollbar { display: none; }" in html


def test_charging_sheet_grab_drag_close(auth):
    """充电详情弹层手柄: 点一下关, 拖 >90px 松手也关 (跟手 + 回弹)。

    iOS Safari 对 touch 指针 setPointerCapture 会当场 pointercancel
    (用户实测拉不动), move/up 挂 window 级不捕获 —— 手指出界照样收,
    各端行为一致 (2026-09-13 修)。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    for frag in ['id="grab-zone"', "touch-action: none",
                 'window.addEventListener("pointermove", move)',
                 'window.addEventListener("pointerup", release)',
                 'window.removeEventListener("pointermove", move)',
                 "translateY(${dy}px)", "if (dy > 90) closeSheet()",
                 # 点一下也关; 拖过 8px 抑制随后的 click (trips 手柄同款)
                 'if (dy > 8) { dy = 0; return; }']:
        assert frag in html, f"充电页缺少 {frag}"
    assert "setPointerCapture(e.pointerId)" not in html   # iOS capture 即 cancel, 别回潮
    assert "touchstart" not in html          # 旧 touch 三件套已废 (鼠标拖不动)


def test_charging_page_cost_filter_menu(auth):
    """费用筛选下拉 (全部/已记录/未记录): 与类型筛选同款收起式, 写进 URL。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    for frag in ['id="cost-menu"', 'id="cost-opts"', 'id="cost-lb"',
                 'data-v="recorded"', 'data-v="missing"', "已记录费用", "未记录费用",
                 "COST_LABELS", '$("#cost-opts").addEventListener',
                 'u.searchParams.set("cost", state.cost)',
                 'cost: state.cost',                       # 列表请求带费用筛选
                 'qs0.get("cost")']:                       # URL 深链带入
        assert frag in html, f"充电页缺少 {frag}"
