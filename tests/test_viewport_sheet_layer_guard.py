"""视口赖账自愈 + 弹层闲置层降级测试 (IMG_7556 定案的守卫)。

7556 像素级复盘: 裸 Safari 里 100dvh 带旧值不刷新 (布局视口 731, dvh 停
438) → 滚动器按矮值排 (下半屏纯黑) + 弹层被 92dvh 压扁 (顶在 432) + 弹层
壳的独立合成层留旧栅格 (背景/圆角整块不画)。四道保险各自的静态断言:

  ① tesla-viewport: 裸 Safari 也有医 (dvh 探针对账钉 --shell-h), 键盘
     拆锁不再只限独立模式, 末拍 lift 带 force 硬回锁;
  ② 四张弹层 CSS: 开态 transform:none (闲置不顶变换层), 高度/封顶吃
     --shell-h (钉高后弹层跟着回满; 足迹地图详情弹层 2026-09-29 随「点路
     不弹窗」退役, 原五张); #acct-sheet (账号) 3.0 并页裸进文档流没穿
     弹层壳, 键盘解锁期顶到最前面盖住所有视图 (2026-09-21 用户实报),
     当天补齐同款基座;
  ③ bindSheetSettle: 视口折腾后强制废弃旧栅格, 四张弹层都接上
     (足迹地图详情弹层 2026-09-29 随「点路不弹窗」退役, 原五张);
  ④ body 尺寸单点: 只许 base.css 定 —— 并页搬进来的视图 css 重复声明
     会把 var(--shell-h) 盖掉 (同特异度后来者胜), 钉高全盘失灵。
     (抽屉的回前台 snap 收净是 7556 的第五道保险 —— 3.3.0 定稿抽屉回归,
     复用 bindSheetSettle($("#drawer"), "on"), 钉在 test_drawer)

弹层拖拽接线 (test_sheet_drag_wiring) 与独立模式冻矮自愈
(test_shell_height_frozen_short_self_heal) 2026-09-21 从 test_shell_wiring
搬来 (那边超 200 行硬上限; 主题本就同族, 一处看全)。
2026-09-26 行程弹层收口两钉搬去 test_trips_sheet_dom, 版本钉与条数/标题
锁步拆去 test_asset_versions (这边又满 200 行硬上限)。"""
from tests.tesla_static_files import served_page


SHELL = "/tesla"
VIEWPORT_JS = "js/tesla-viewport.js"
SHEET_DRAG_JS = "js/tesla-sheet-drag.js"


def _js(auth, name):
    return auth.get(f"/tesla/static/{name}").text


def test_viewport_dvh_lie_probe_pinned(auth):
    """① 裸 Safari 的 dvh 赖账: 探针 (fixed 100dvh 标尺, 不吃 --shell-h)
    比文档根矮超 120px 且稳 0.7s → 钉 --shell-h; 回平 (差 ≤12) 撤。"""
    js = _js(auth, VIEWPORT_JS)
    for frag in ("function probeDvh()", "height:100dvh",
                 "function dvhLie()", "shellH(true, root.clientHeight)",
                 "clientHeight - probeDvh() < 120", "gap <= 12"):
        assert frag in js, f"dvh 探针缺 {frag}"
    # 探针必须绕开 --shell-h (钉了高也量真 dvh), 不然钉完测不出回平
    assert "var(--shell-h" not in js


def test_viewport_keyboard_unlock_covers_safari(auth):
    """① 键盘拆锁扩到裸 Safari (之前只限独立模式, 7556 正是裸 Safari 的
    账); 末拍 lift(true) 防 Safari 工具栏状态变了后文档一直敞着。"""
    js = _js(auth, VIEWPORT_JS)
    assert "const appleTouch = ()" in js
    assert "if (!appleTouch()) return;" in js          # focusin 拆锁门槛
    assert "if (!patient()) { dvhLie(); return; }" in js   # 探针走 Safari 分支
    assert "lift(force)" in js and "() => lift(true), 1800" in js


def test_sheets_open_state_transform_none(auth):
    """② 四张弹层开态 transform:none —— 闲置不顶独立变换层 (iOS 折腾完
    键盘/工具栏不留旧栅格); none↔105% 按单位矩阵插值, 滑入滑出照旧。
    translateY(0) 的开态不许回潮。"""
    page = served_page(auth, "/tesla")
    for sel in ("#chg-sheet.on", "#sheet.show", "#cm-sheet.show",
                "#acct-sheet.show"):
        assert f"{sel} {{ transform: none; }}" in page, f"{sel} 开态不是 none"
    assert "transform: translateY(0); }" not in page, "有弹层开态仍是 translateY(0)"


def test_sheets_height_consume_shell_h(auth):
    """② 弹层高度/封顶吃 --shell-h: 钉高后弹层跟着回满 (7556 的压扁当场
    弹回来); 未钉时 calc(var(--shell-h, 100dvh) * N) 与裸 dvh 等值。
    #acct-sheet 裸奔两天的基座 (fixed/105%/z 91) 一并钉死。"""
    page = served_page(auth, "/tesla")
    # chg/acct 内容自高只封顶 (4 份); 其余两张固定高度 82% + 封顶 92%
    # (足迹地图详情弹层 2026-09-29 随「点路不弹窗」退役, 原 5/3 份)
    assert page.count("max-height: calc(var(--shell-h, 100dvh) * .92);") == 4
    assert page.count("height: calc(var(--shell-h, 100dvh) * .82);") == 2
    block = page[page.index("#acct-sheet {"):page.index("}", page.index("#acct-sheet {"))]
    for need in ("position: fixed", "bottom: 0; z-index: 91",
                 "transform: translateY(105%)"):
        assert need in block, f"#acct-sheet 基座缺 {need}"
    for gone in ("max-height: 92dvh", "height: 82dvh"):
        assert gone not in page, f"弹层还吃裸 dvh: {gone}"


def test_body_sizing_declared_once_in_base(auth):
    """④ 壳高单点 (7556 收尾自查抓的雷): 3.0 并页时各视图 css 把独立页
    时代的 body 高度 (height/min-height 100dvh) 原样搬了进来 —— 与
    base.css 同特异度且在级联后面, 把 var(--shell-h) 整个盖掉, 钉高机制
    钉了也白发 (7556 的下半屏黑正是 body 被盖在矮值上)。日历菜单的矮屏
    封顶同一颗雷, 5 处一起吃 --shell-h。"""
    page = served_page(auth, SHELL)
    base = page.index("height: var(--shell-h, 100dvh);")
    for gone in ("height: 100dvh;", "height: 100vh;",
                 "min-height: 100dvh;", "min-height: 100vh;"):
        assert gone not in page[base:], f"base.css 之后又定 body 尺寸: {gone}"
    assert page.count("max-height: calc(var(--shell-h, 100vh) - 130px);") == 5


def test_sheet_settle_wired_on_all_four_sheets(auth):
    """③ bindSheetSettle: 视口折腾 (visualViewport resize / 回前台) 后给
    开着的弹层过一遍微变换回 none, 强制废弃已烂的栅格; 收起瞬间 MutationObserver
    清 inline none, 不压住类里的 105% 滑出。四张弹层全接上 (足迹地图详情
    弹层 2026-09-29 随「点路不弹窗」退役)。"""
    js = _js(auth, SHEET_DRAG_JS)
    for frag in ("function bindSheetSettle(sheet, openClass)",
                 'sheet.style.transform = "translateY(0.01px)"',
                 'sheet.style.transform = "none"',
                 "attributeFilter: [\"class\"]",
                 'sheet.style.transform === "none"'):
        assert frag in js, f"settle 缺 {frag}"
    for wiring in ('bindSheetSettle(chgSheet, "on")',
                   'bindSheetSettle($("#sheet"), "show")',
                   'bindSheetSettle($("#cm-sheet"), "show")',
                   'bindSheetSettle($("#acct-sheet"), "show")'):
        assert wiring in served_page(auth, "/tesla"), f"没接上 {wiring}"


def test_sheet_drag_wiring(auth):
    """详情弹层信息区下滑收起 (用户点名): 四张明细弹层 (充电/行程/充电地图/
    账号) 共用壳级 tesla-sheet-drag —— 拖着跟手, 松手回弹, 拉过 90px 才关,
    拖过 8px 抑制随后的 click; 把手点一下也关, 信息区点一下不关 (✕/下拉框
    在上面)。move/up 挂 window 级不捕获: iOS Safari 对 touch 指针 capture
    会当场 pointercancel (2026-09-13 用户实测拉不动)。
    轴向仲裁 (2026-09-27 用户点名「左右滑会被判定下滑」): slop 内弹层
    不动; 横向占优 = 横滑交还原生 (弹层分页切页/地图平移) 并解绑弹回;
    明确向下 (vy > 2|dx|) 才接管 —— 45° 斜角拖着弹层乱晃的旧路不许回潮。"""
    page = served_page(auth, SHELL)
    assert "tesla-sheet-drag.js" in page          # 壳级共用助手已挂
    for token in ('window.addEventListener("pointermove", move)',
                  'window.addEventListener("pointerup", release)',
                  'window.removeEventListener("pointermove", move)',
                  "translateY(${dy}px)", "if (dy > 90) onClose()",
                  "e.stopImmediatePropagation(); e.preventDefault(); dy = 0; return;",
                  # 轴向仲裁三态: 横滑交还原生 / 明确向下才接管 / 斜向未定不动;
                  # 横滑分支不碰样式 (仲裁窗口内改祖先样式掐死原生滚动起手),
                  # 接管过的松手才清 (moved 闸)
                  'if (Math.abs(dx) > Math.abs(vy)) {', 'axis = "x"; detach();',
                  'if (vy > Math.abs(dx) * 2) axis = "y";',
                  'if (moved) { sheet.style.transition = ""; sheet.style.transform = ""; }',
                  # 四张弹层的接线 (把手 tap 关 / 信息区只拖不点关;
                  # 充电详情正文一屏装下, 正文区整片同绑;
                  # 足迹地图详情弹层 2026-09-29 随「点路不弹窗」退役)
                  'bindSheetDrag(chgSheet, $("#chg-grab-zone"), chgCloseSheet, true)',
                  'bindSheetDrag(chgSheet, chgSheetBody, chgCloseSheet, false)',
                  'bindSheetDrag($("#sheet"), $("#grab"), closeTrip, true)',
                  'bindSheetDrag($("#cm-sheet"), $("#cm-sheet"), cmCloseSheet, false)',
                  'bindSheetDrag($("#acct-sheet"), $("#acct-sheet .grab"), closeAcct, true)'):
        assert token in page, f"弹层拖拽缺 {token}"
    assert "setPointerCapture(e.pointerId)" not in page


def test_shell_height_frozen_short_self_heal(auth):
    """壳高冻矮自愈 (用户点名修底部黑边, music 1.8.32 同病同方): iOS 独立
    模式冷开时还原高度跨重启赖账, 壳矮一截底下露黑带、整程永不自愈 ——
    医生实锤冻矮就把壳高钉记档的满高 (--shell-h), 黑带当场补回, 回满自动撤;
    平时壳高就是真 100dvh。"""
    page = served_page(auth, SHELL)
    assert "height: var(--shell-h, 100dvh);" in page
    doctor = _js(auth, VIEWPORT_JS)
    assert 'setProperty(\n      "--shell-h"' in doctor
    assert 'removeProperty("--shell-h")' in doctor
    # 满高钳屏内 (转屏防基线被瞬时值带高, 补偿铺出屏外截掉底栏);
    # Safari 探针分支传自己的参考值 (px), 独立模式缺省用记档满高 (full)
    assert "Math.min(px != null ? px : full, capOf())" in doctor
    # 实锤闩住回满才解, 健在分支撤补偿
    assert "declared = true;" in doctor and "shellH(false);" in doctor
