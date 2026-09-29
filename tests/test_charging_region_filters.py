"""充电地点筛选测试: 省市区级联端点与会话过滤,
弹层把手, 费用筛选菜单。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime

from app.tesla.models import Address
from tests.charging_page_scripts import CHARGING_ASSETS, _page_scripts
from tests.seed_factories import seed_addresses, seed_charge, seed_charging
from tests.tesla_static_files import served_page

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


def test_charging_view_region_chips(auth):
    """屏底筛选条三枚 chips (类型/费用/地点省市区级联), 选完即收; 偏好住
    localStorage (不再写 URL, 旧链接参数冷启折进偏好)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        'registerChips("charging"',
        "TYPE_LABELS", "COST_LABELS",
        "/tesla/charging/api/regions",
        # 地点省市区级联 (行程页同款): 钻取行/返回行/面包屑
        'class="loc-back"', 'class="loc-crumb"', 'class="loc-row', "钻下一级",
        "快充", "慢充",
        "已记录费用", "未记录费用",
        "chgSaveFilters", "refreshBarChips",
        'p.set("region", chgState.region)',   # 列表请求带地点筛选
        'qs.get("region")',                   # 旧 URL 深链折进偏好 (tesla-shell)
        'qs.get("cost")', 'qs.get("type")',
    ]:
        assert frag in html, f"充电视图缺少 {frag}"


def test_charging_list_month_groups(auth):
    """充电记录按月分组 (用户点名): 列表日期倒序, 跨月处插 .month-head
    月份小标 ("2026年9月" 款), 同月不重插; 下拉刷新/筛选重灌时月账归零
    (chgLastMonth 清空), 不然重灌后首月没头。"""
    page = served_page(auth, "/tesla")
    for frag in ("month-head",                     # 小标类 (样式在 charging-cards css)
                 "chgLastMonth",
                 "const key = m[1] + m[2]",
                 "if (key === chgLastMonth) return null",
                 "`${+m[1]}年${+m[2]}月`",
                 "frag.append(head, card)",        # 月头带首卡一起进栏 (分页骨架不动)
                 'chgLastMonth = "";'):            # refetch 清账
        assert frag in page, f"充电月分组缺 {frag}"


def test_charging_list_place_and_slim_cards(auth):
    """列表卡片 (用户点名): 地点只留最小两段 (fmtPlaceShort, 常态 区 · 地名,
    解析不出省退化到市级) —— 前段弱色前缀 + 地名, 整链在详情底部地址;
    卡片底下的时长/峰值/温度行撤掉, 卡片收干净。"""
    page = served_page(auth, "/tesla")
    for frag in ("const pp = fmtPlaceShort(it),",
                 "pp[pp.length - 1]",
                 'class="cs-region"',
                 "function fmtPlaceShort(it)", "function fmtPlace(it)"):
        assert frag in page, f"充电列表缺 {frag}"
    for gone in ('class="cs-sub"', "fmtDur(it.duration_min)",
                 "峰值 ${it.power_max", "const region = fmtRegion(it);"):
        assert gone not in page, f"充电列表残留 {gone}"


def test_charging_sheet_grab_drag_close(auth):
    """充电详情弹层下滑关闭: 把手点一下关 / 拖 >90px 松手也关; 上部信息区
    (日期/地点/标签行) 也能拖着收起 (用户点名), 点一下不关 (✕ 在上面);
    正文整片 (统计格/费用条/图表/地址) 同绑 (用户点名: 没有下滑事件的
    控件全补上, 点按不受影响)。拖拽本体在壳级 tesla-sheet-drag
    (test_shell_wiring 钉), 这里钉充电侧接线与 iOS 安全规矩。

    iOS Safari 对 touch 指针 setPointerCapture 会当场 pointercancel
    (用户实测拉不动), move/up 挂 window 级不捕获 —— 手指出界照样收,
    各端行为一致 (2026-09-13 修)。"""
    html = served_page(auth, "/tesla")
    for frag in ['id="chg-grab-zone"', "touch-action: none",
                 'bindSheetDrag(chgSheet, $("#chg-grab-zone"), chgCloseSheet, true)',
                 'bindSheetDrag(chgSheet, $("#chg-sheet .sheet-head"), chgCloseSheet, false)',
                 'bindSheetDrag(chgSheet, chgSheetBody, chgCloseSheet, false)',
                 'class="sheet-head sheet-drag"']:
        assert frag in html, f"充电视图缺少 {frag}"
    # iOS capture 即 cancel, 别回潮 (抽屉的拖拽是另一模式: 元素自身捕获,
    # 串的是 d.setPointerCapture(pid), 不在此列)
    assert "setPointerCapture(e.pointerId)" not in html
    # 旧 touch 三件套已废 (鼠标拖不动) —— 只对充电视图自有脚本 (trips 的
    # 地图双指探测合法用 touchstart)
    assert "touchstart" not in _page_scripts(auth, *CHARGING_ASSETS)
