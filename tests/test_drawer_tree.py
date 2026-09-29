"""3.3.0 抽屉树状改款测试 (用户点名「菜单窄一点, 一级二级菜单改成树状
结构, 图标从 iconfont 找一些, 界面现代一点, 要好看, iOS 风格」): 一级 =
状态/行程/充电/设置四张分组卡 (iOS 设置页 inset-grouped 口径), 组行点开
手风琴展开二级; 图标 = Lucide 开源线性集 (iconfont 同款风格, path 数据
原样内联进 DRW_ICONS 表)。

抽屉机械件 (开合/拖拽/手势面/宽度钉/账号卡) 住 test_drawer —— 这里只钉
树状结构与图标的对账: DRW_ICONS 的键与 NAV_GROUPS 的组 ic/页 key 是两处
手工同步的事实源, 靠肉眼必缺 —— 缺一枚组行/叶行就裸奔无图标, 对账钉住
立即红。
"""
import re

from tests.tesla_static_files import served_page

SHELL = "/tesla"
DRAWER_JS = "js/tesla-drawer.js"


def _js(auth):
    return auth.get(f"/tesla/static/{DRAWER_JS}").text


def test_drawer_tree_structure(auth):
    """树状结构: 多页组 = 分组行 + 手风琴二级 (一次只开一组, 再点同组收
    起), 当前视图所在组自动展开; 单页组 (状态) 直接叶行卡。iOS 口径: 44px
    叶行 / 组内缩进 + hairline 分隔 / 选中蓝满行 / chevron 展开转 180°,
    二级展开走 grid-rows 0fr→1fr 高度动画。账号不随树状改版回搬; 车辆选择
    3.3.0 定稿住抽屉顶 (车辆卡钉在 test_drawer_car_section), 时间筛选已
    下线 —— 抽屉纯导航的底线钉在这。"""
    page, js = served_page(auth, SHELL), _js(auth)
    for frag in ("grid-template-rows: 0fr",
                 ".drw-grp.open .drw-sub { grid-template-rows: 1fr; }",
                 ".drw-grp.open .chev { transform: rotate(180deg); }",
                 ".drw-sub-in .drw-leaf { border-top: 1px solid var(--hairline); }",
                 ".drw-grp .drw-leaf { padding-left: 28px; }",
                 ".drw-leaf.on { color: #7db3f0; background: rgba(57,135,229,.14); }"):
        assert frag in page, f"树状样式缺 {frag}"
    for frag in ("if (items.length === 1)",        # 单页组: 直接叶行卡
                 'document.querySelectorAll("#drw-nav .drw-grp.open")',
                 'c.querySelector(`.drw-leaf[data-nav="${key}"]`)'):
        assert frag in js, f"树状接线缺 {frag}"
    drw = page[page.index('<aside id="drawer"'):page.index("</aside>")]
    for gone in ("acct", "time-menu", "logout"):
        assert gone not in drw, f"抽屉里混进了 {gone}"


def test_drawer_tree_icons(auth):
    """图标对账: NAV_GROUPS 用到的组图标 (ic) 和页图标 (key) 每一枚都要
    在 DRW_ICONS 里 (缺了行就裸奔); 口径 = Lucide 24px 网格线性描边,
    stroke 跟文字色, chevron 用 chevron-down 的 path。"""
    js = _js(auth)
    i = js.index("const NAV_GROUPS")
    need = set(re.findall(r'(?:key|ic): "([\w-]+)"', js[i:js.index("];", i)]))
    j = js.index("const DRW_ICONS")
    have = set(re.findall(r'^\s+"?([\w-]+)"?: "<', js[j:js.index("};", j)], re.M))
    assert need <= have, f"DRW_ICONS 缺图标: {sorted(need - have)}"
    assert "chev" in have and "d='m6 9 6 6 6-6'" in js   # chevron-down path
    for frag in ('viewBox="0 0 24 24"', 'stroke="currentColor"',
                 'stroke-width="1.8"'):
        assert frag in js, f"图标描边口径缺 {frag}"


def test_drawer_car_section(auth):
    """车辆选择卡 (3.3.0 用户令「选择车辆放在菜单里, 选中之后对所有页面都
    生效」): 住抽屉顶 (导航之上, 不随导航滚), 点 pill = 全局 setCar —— 行
    程/充电/统计/地图/驾驶全按选中车取数 (订阅方 refreshCurrent); 抽屉不
    关, 点完继续导航; 单车显示静态车名, 拉不到列表整卡藏起。pills 显式
    display:block 盖掉充电旧页 .car-pill 基类的窄屏 (≤359px) 隐藏。"""
    page = served_page(auth, SHELL)
    cs = auth.get("/tesla/static/js/tesla-car-switcher.js").text
    drw = page[page.index('<aside id="drawer"'):page.index("</aside>")]
    assert 'class="drw-cars" id="drw-cars"' in drw and 'id="car-pills"' in drw
    assert drw.index("drw-cars") < drw.index('class="drw-nav"')  # 卡在导航上
    assert "cars.length === 1" in cs                       # 单车: 静态车名行
    assert 'setCar(b.dataset.car === "" ? null : +b.dataset.car);' in cs
    assert "closeDrawer" not in cs and "currentCarLabel" not in cs  # 不关抽屉
    assert 'getJSON("/tesla/charging/api/car")' in cs
    i = page.index(".drw-cars {")
    assert "border-radius: 14px" in page[i:page.index("}", i)]
    assert ".drw-cars .car-pill.on { color: #7db3f0;" in page
    assert "display: block; max-width: 100%;" in page   # 盖旧页窄屏隐藏
    # 车图功能 (2026-09-27 两上两撤, 用户点名「设置车的图片的按钮也去掉」)
    # 整链退役: 图块/相机钮/上传接线一并拆净, 车辆卡回到标签行 + pills
    for gone in ("drw-carimg", "drw-img-btn", "drw-img-file", "carImgFocus",
                 "shrinkImage", "refreshCarImg", "drw-cars-top"):
        assert gone not in page, f"车图功能残留: {gone}"
