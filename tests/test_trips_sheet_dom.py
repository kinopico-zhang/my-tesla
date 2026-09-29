"""行程弹层 DOM 收口测试: 头部一行 / 把手各归各弹层 / 下滑关闭; .sh-title
/.sh-sub/.sh-cell 被充电地图与足迹明细共用, 后加载的同名裸表会顶掉行程侧
的字号与 margin —— scoped 收口与盒模型自查。2026-09-26 拆自
test_trips_pages (头部/把手/拖关) 与 test_viewport_sheet_layer_guard
(scoped 两钉 —— 两边都满了 200 行硬上限)。"""
import re

from tests.tesla_static_files import page_js, served_page


def test_trips_view_sheet_grab_drag_close(auth):
    """轨迹弹层下滑关闭: 把手点一下关 / 拖 >90px 松手也关; 上部信息区
    (日期时长/驾驶员/统计格) 和左滑过去的动态页/统计页 (各自三张图卡)
    也能拖着收起 (用户点名; 统计页 2026-09-27 再点名补上), 点一下不关
    (那里有驾驶员下拉框); 播放条与地图是控件区, 不在此列。拖拽本体在
    壳级 tesla-sheet-drag (test_shell_wiring 钉)。"""
    both = served_page(auth, "/tesla")
    js = page_js(auth, "/tesla")
    for frag in ['id="grab"', "touch-action: none", ".grab::before",   # 整行命中区
                 'bindSheetDrag($("#sheet"), $("#grab"), closeTrip, true)',
                 '#sheet .sh-head, #sheet .sh-cells, #sheet .tp-stats, #sheet .tp-hist',
                 'class="sh-head sheet-drag"', 'class="sh-cells sheet-drag"']:
        assert frag in both, f"行程视图缺少 {frag}"
    assert "setPointerCapture(e.pointerId)" not in both   # iOS touch 指针 capture 即 cancel, 别回潮
    assert '$("#grab").addEventListener("click", closeTrip);' not in js
    assert 'grab.addEventListener("touchstart"' not in js   # 手柄不吃旧 touch 三件套


def test_trips_sheet_header_one_row(auth):
    """弹层头部一行 (用户点名再排): 日期带年份 + 出发时刻并到左边一串,
    右上角 2026-09-24 用户点名让给驾驶员 (原是当前页标题, 页标题退役 ——
    切页点底行页标区); 驾驶员纯文字可点 (点击弹底部选单换人, 不再框椭圆
    胶囊 —— 原生 select 的文字不听页面 CSS, 三样字体凑不齐, 用户实报字
    体不一样); 字号一致 (13px/600), 同一水平线 (行高钉 25px, 按钮同高);
    时间只显出发时刻 (范围太长), 合并多段前缀段数。高速费行整行撤掉
    (先去掉)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        # 日期+时刻并进左侧一串 (时间 span 内嵌颜色压一档), 驾驶员真文字
        # 按钮独占右栏 (2026-09-24 用户点名从左串时间后面挪来右上角)
        '<div class="sh-title"><span id="sh-date">–</span>'
        '<span class="sh-sub" id="sh-time"></span></div>',
        '<button type="button" class="sh-drv" id="sh-drv-btn" aria-label="切换驾驶员" hidden></button>',
        "font-size: 13px; font-weight: 600; display: flex;",
        # 左串 flex 排: 日期位独扛收缩 (分组名 30 字省略号兜底), 时间定宽;
        # margin 声明死 —— 后加载裸 .sh-sub 的竖向 margin 在 flex 盒里真生效
        # (2026-09-22 用户实报「时间突出来了」)
        "#sh-date {", "flex: 0 1 auto; min-width: 0;",
        "margin: 0 0 0 6px;",
        # 同一套字 + 同一水平线: 行高钉 25px, 按钮定高 25px 同线
        "line-height: 25px;", "height: 25px;",
        # 日期带年份 (fmtFullDate); 时间并进左串。
        # fmtFullDate/fmtFullStamp/shiftStamp 必须随解构接线 (trips-sheet-page
        # 从 FormatUtil 解构, 漏了就是 ReferenceError, 弹层整个打不开 ——
        # 2026-09-22 用户实报)
        "const { fmtTime, fmtFullDate, fmtFullStamp, shiftStamp, fmtDurLive } = FormatUtil;",
        "fmtFullDate(it.start)",
        '$("#sh-time").textContent = fmtTime(it.start);',
        # 合并副标题静态口径收进 mergedSub (打开时/收尾定格同一份; 播放中
        # 由 setSegTitle 动态换段, 2026-09-25 用户点名): 分组名下显整组起始
        # 日期+时刻 (星期让位给具体时:分), 非分组合并显出发时刻
        'it.n + " 段行程 · " + (it.gname ? fmtFullStamp(it.start) : fmtTime(it.start))',
        # 分组 (分组页打开, 2026-09-22 用户点名): 名字当主标题, 只留起始
        # 日期不要时刻; 名字最长 30 字, 靠左串日期位的省略号兜底
        '$("#sh-date").textContent = it.gname;',
        # 占位期名字先亮 (数据在路上也不空白)
        "it && it.gname ? it.gname : \"连续轨迹\"",
        "grid-template-columns: minmax(0, 1fr) auto;",   # 左串弹性 + 右栏驾驶员
        "border-radius: 3px; background: #48484a; margin: 0 auto;",
        # 纯文字按钮: 蓝色示意可点, 背景/边框全撤, 最宽 40vw 别挤走日期
        "color: var(--blue);", "background: none; border: 0;",
        "max-width: 40vw;",
        # 点击弹底部选单换人 (与卡片 pill 同一张); 标注写库后就地刷按钮文案
        '$("#sh-drv-btn").addEventListener("click"',
        "syncDrvBtn(it);", "if (it === sheetTrip) syncDrvBtn(it);",
    ]:
        assert frag in html, f"行程弹层头部缺少 {frag}"
    # 原生 select 整链退场 (胶囊样式/option/宽上限全拆); 页标题整颗退役
    # (2026-09-24 用户点名右上角给驾驶员, 切页点底行页标区)
    assert "sh-drv-sel" not in html and "sh-drv-pick" not in html
    assert "sh-page" not in html
    assert '<span class="lb">驾驶员</span>' not in html   # 标签文字删了
    # 高速费行 (chip + metaRowSync) 已整行撤掉
    assert 'id="sh-toll"' not in html and "metaRowSync" not in html


def test_trips_sheet_handle_scoped_and_map_on_top(auth):
    """把手各归各弹层: 3.0 四弹层共用 .grab 类名, 裸规则互串 —— map-canvas
    的 38px hairline 胶囊 (元素底色) 叠着行程侧的实色 ::before 胶囊 = 重影
    (2026-09-21 用户实报); 三张用 .grab 的弹层各自 scoped, 足迹/账号顺手
    统一成实色。轨迹详情地图与统计格调换 (用户点名): 打开先见轨迹, 数字
    垫底; 数字带/播放条 2026-09-25 挪到分页外公共带 (三页等高修平,
    播放条不播不占位, 用户点名不放地图里; 更早的让位带方案两头都挨过批
    —— 底部空间没吃满 + 控制框周围黑边)。"""
    html = served_page(auth, "/tesla")
    for frag in ["#sheet .grab {", "#sheet .grab::before",   # 行程: 实色胶囊
                 "#acct-sheet .grab {"]:   # 账号: 各归各 (足迹弹层已随点路
                                           # 不弹窗整块退役, 2026-09-29)
        assert frag in html, f"弹层句柄缺少 scoped 样式 {frag}"
    # 地图在上: DOM 里 trip-map-wrap → 数字带 → 播放条 (数字带/播放条
    # 2026-09-25 挪到分页外公共带, 三页共享), 播放条不在地图区里
    assert html.index('class="trip-map-wrap"') < html.index('class="sh-cells sheet-drag"')
    assert html.index('class="sh-cells sheet-drag"') < html.index('id="playbar"')
    assert "gap: 8px;\n  margin: 8px 0 0;" in html   # 贴地图下, 底缝归播放条


def test_trips_sheet_scoped_rules_survive_later_sheets(auth):
    """行程弹层的 .sh-title/.sh-sub/.sh-cell 必须收口在 #sheet 下: 这三个
    类名被充电地图明细 (chargemap-map.css) 和足迹明细 (map-canvas.css)
    共用, 那两张的样式表都排在 trips-sheet.css 之后 —— 裸规则同特异度
    后来者胜, 行程弹层的日期被顶成 17px/700 还下沉 10px、时间被压成
    12px、统计格数字 15px→18px (2026-09-22 用户报: 三样字体凑不齐、
    驾驶员跟时间高低不齐)。#sheet (1,1,0) 压过任何后加载的 (0,1,0) 裸
    规则 —— 与 .sheet 基座/.grab 句柄同款老病同款收口 (3.0 并页起第
    三次实报)。.sh-head/.sh-drv/.sh-cells 名字独占, 裸着没事。"""
    css = auth.get("/tesla/static/css/tesla-trips-sheet.css").text
    for scoped in ("#sheet .sh-title { font-size: 13px; font-weight: 600;",
                   "#sheet .sh-sub { font-size: 13px; font-weight: 600;",
                   "#sheet .sh-cell { background: var(--surface);",
                   "#sheet .sh-cell .val { font-size: 15px;",
                   "#sheet .sh-cell .val .n { display: inline-block;"):
        assert scoped in css, f"行程弹层规则没收口 (会被后加载的同名表盖掉): {scoped}"
    for bare in (".sh-title", ".sh-sub", ".sh-cell"):
        assert not re.search(rf"^{re.escape(bare)}(?![a-z-])", css, re.M), \
            f"{bare} 裸规则回潮: 后加载的 chargemap-map/map-canvas 同名表会盖掉"


def test_trips_sheet_header_owns_its_box_model(auth):
    """收口只盖同名属性 —— 对方声明而我没声明的属性照漏 (2026-09-22 用户实报
    「时间突出来了」): 后加载的 chargemap/map-canvas 裸 .sh-sub 带 2px/14px
    竖向 margin、裸 .sh-title 带 10px, v13 时代时间是内联 span (竖向 margin
    被内联化吞掉) 无感; 头部改 flex 后成了真 flex 盒, 漏进来的竖向 margin 当
    生效把时间顶出日期线。#sheet 收口规则必须连 margin 一起声明死。"""
    css = auth.get("/tesla/static/css/tesla-trips-sheet.css").text
    for sel, own in (("#sheet .sh-title", "margin: 0;"),
                     ("#sheet .sh-sub", "margin: 0 0 0 6px;")):
        block = css[css.index(sel):css.index("}", css.index(sel))]
        assert own in block, f"{sel} 没把 margin 声明死 (后加载裸规则的竖向 margin 会漏进来)"
