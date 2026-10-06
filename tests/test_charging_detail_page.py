"""充电详情弹层的页面接线测试: 档位条渲染 / 标签排布 / 双轴合并图 /
统计区收格 / 导航与 ✕ 撤除的守卫。

拆自 test_charging_session_details.py (2026-09-21 超 200 行硬上限拆出:
那边留 API 口径, 这边收静态页面断言; 代码逐字节未动)。"""
from tests.charging_page_scripts import CHARGING_ASSETS, _page_scripts
from tests.tesla_static_files import served_page


def test_charging_detail_pw_tabs_render(auth):
    """档位条按后端 tabs 渲染: 静态三连按钮已废, 上次选的档这次没有就折回
    功率, 只剩一档时整条不渲染 (监听器对缺位的 #pw-seg 有守卫)。"""
    page = served_page(auth, "/tesla")
    for frag in ("const pwTabs = d.curve.tabs",
                 'if (!pwTabs.includes(pwMode)) pwMode = "kw"',
                 "pwTabs.length > 1",
                 'pwTabs.map(k => `<button data-v="${k}"',
                 "if (pwSeg) pwSeg.addEventListener"):
        assert frag in page, f"充电详情缺少 {frag}"
    for gone in ('<button data-v="voltage">电压</button>',
                 '<button data-v="current">电流</button>'):
        assert gone not in page, f"充电曲线静态档位残留 {gone}"


def test_charging_detail_tag_beside_date(auth):
    """详情弹层快慢充标签与日期同行钉右上角 (用户点名): 日期大标题占左,
    标签 pill 靠右; 下方标签行只剩线缆/类型, 两个都没有时收掉不留空行;
    地点行大→小且与列表同口径 (fmtPlace)。"""
    page = served_page(auth, "/tesla")
    for frag in ('id="chg-sh-tag"', '$("#chg-sh-tag").innerHTML',
                 ".sheet-head .sh-date-row", ".sheet-head .sh-row:empty",
                 '$("#chg-sh-loc").textContent = fmtPlace(d);'):
        assert frag in page, f"充电详情缺 {frag}"
    # 快慢充 pill 照旧 (2026-09-27 用户点名「该是快充和慢充还是要打对应的
    # tag」): 两处 ternary 链不再有 Tesla 分支 —— 类别标与品牌标分家
    assert page.count('d.is_fast ? "tag-fast" : "tag-slow"') == 1
    assert page.count('it.is_fast ? "tag-fast" : "tag-slow"') == 1
    # Tesla 官方桩是「额外的 tag」(用户点名): 字标 TESLA_MARK 与快慢充
    # pill 同组 (列表卡 .cs-tags / 弹层 #chg-sh-tag), 不再顶掉类别标;
    # 同日用户再点名「换个位置, 快慢充一直在右上角」: pill 常驻组内最右
    # (卡右上角), 字标立在它左边; 字标没有可读文字 → 补 aria-label 给读屏
    cards = auth.get("/tesla/static/js/view/charging-cards.js").text
    detail = auth.get("/tesla/static/js/view/charging-detail.js").text
    common = auth.get("/tesla/static/js/tesla-common.js").text
    assert '<span class="cs-tags">${it.tesla_supercharger' in cards
    assert '}<span class="tag ${tagCls}">${tagLb}</span></span>' in cards
    assert 'class="tesla-mark" aria-label="Tesla 超充">${TESLA_MARK}</span>' in cards
    # 弹层同款: 字标段在前, pill 段收尾 (concat 顺序钉死)
    i_mark = detail.index('aria-label="Tesla 超充">${TESLA_MARK}</span>` : "") +')
    assert '<span class="tag ${shCls}">${shLb}</span>`;' in detail
    assert i_mark < detail.index('<span class="tag ${shCls}">${shLb}</span>`;')
    # 附加标样式 (用户点名「白色字体, 没有 border」): 白字裸标不套 pill
    # 底色, 尺寸钉在 .tesla-mark svg (长宽比 7.67:1, 高 9.5px); 弹层右
    # 上容器同款并排 (gap 对齐列表卡)
    assert ".cs-tags { display: inline-flex; align-items: center; gap: 6px;" \
        " flex: none; }" in page
    assert ".tesla-mark { display: inline-flex; color: var(--ink-1); }" in page
    assert ".tesla-mark svg { display: block; height: 9.5px; width: 72.9px; }" in page
    assert "#chg-sh-tag { display: inline-flex; align-items: center;" \
        " gap: 6px; }" in page
    # 官方字标本体 (Wikimedia Commons「Tesla Motors Logo.svg」压平, 8 子路径
    # T/E/S/L/A; 两层 transform 烘进坐标): 钉住 viewBox/配色交接/收尾
    assert 'const TESLA_MARK =' in common
    assert 'viewBox="0 0 1236.01 161.13" aria-hidden="true"' in common
    assert 'fill="currentColor"' in common
    assert common.count("</svg>';") == 1   # 字标常量只此一份, 串收尾
    # 红 pill 旧样式 (tag-tesla 整链) 不许回潮
    assert "tag-tesla" not in page, "tag-tesla 红标样式回潮了"
    # 旧的文字角标不许回潮 (钉在两个视图脚本里, aria-label 里的字样不算)
    for js in (cards, detail):
        assert '? "Tesla 超充" :' not in js, "「Tesla 超充」文字角标回潮了"
    # 头顶地点与列表同款只留最小两段, 整链留在最底地址行 (用户点名)
    assert '<div class="sh-addr">${esc(d.address || "")}' in page


def test_charging_detail_chart_merged_dual_axis(auth):
    """电量曲线与充电曲线合并成一张双轴图 (用户点名): 左轴电量 % (绿), 右轴
    功率/电压/电流随档换色; 两轴刻度各染各的曲线色, 横轴截到曲线终点
    (用户点名: 轴色对应曲线 + 多的截掉); 分体图 (#chart-soc + connect
    联动) 不许回潮。"""
    js = _page_scripts(auth, *CHARGING_ASSETS)
    for frag in ('id="chart-pw"', "yAxisIndex: 0", "yAxisIndex: 1",
                 'color: "#1fa349", fontSize: 10, formatter: "{value}%"',
                 "cv.minutes.length ? cv.minutes[cv.minutes.length - 1] : null",
                 "max: xMax",
                 'name: "电量 %", nameGap: 8',              # 左右轴义标在轴顶 (用户点名)
                 "name: `${s.name} ${s.unit}`, nameGap: 8",  # 右轴义随档换
                 "grid: { left: 6, right: 6, top: 26, bottom: 0, containLabel: true }",
                 "renderPwChart"):
        assert frag in js, f"合并图表缺 {frag}"
    for gone in ('id="chart-soc"', "ec.connect([chSoc, chPw])",
                 '<div class="sh-chart-title">电量 %</div>'):
        assert gone not in js, f"分体电量图残留 {gone}"


def test_charging_detail_stat_row_compact(auth):
    """统计区只留曲线里没有的 (用户点名): 电量变化/峰值功率撤掉 (横轴/
    左轴/右轴就是它们); 一行 = 充入/表计电量 + 续航增加, 二行 = 总价/
    每度价格/充电时间。总价 2026-09-29 从占两格收成一格 (用户点名「充电
    明细总价这个框改到1格宽, 多出来的位置加一个充电时间」), 时长当初撤掉
    (看图就有) 这次点名要回 —— 改口充电时间住末格, fmtDur「1时44分」与
    行程页同口径。总价仍可点补录 —— 但补录入口不带 ✎ 提示 (用户点名
    "怎么设置菜单出来了", 卡片胶囊的 ✎ 才是显式入口); 禁令圈在充电
    资产里。"""
    js = _page_scripts(auth, *CHARGING_ASSETS)
    for frag in ('<div class="lb">充入电量</div>', '<div class="lb">表计电量</div>',
                 '<div class="lb">续航增加</div>', '<div class="lb">总价</div>',
                 '<div class="lb">每度价格</div>', '<div class="lb">充电时间</div>',
                 'id="st-cost-tile"',
                 'id="st-cost-val"', 'id="st-price-val"',
                 "fmtDur(d.duration_min)",
                 "grid-template-columns: repeat(3, 1fr)",
                 ".st-cost .val { font-size: 17px; }"):
        assert frag in js, f"统计区缺 {frag}"
    for gone in ('<div class="lb">电量变化</div>',
                 '<div class="lb">峰值功率</div>', '<div class="lb">电价</div>',
                 '<div class="lb">平均价格</div>',
                 "grid-column: span 2", ".st-cost .val { font-size: 18px; }",
                 ".sc-price", ".sc-main", '.st-cost .lb::after'):
        assert gone not in js, f"统计区残留 {gone}"


def test_charging_detail_nav_and_close_removed(auth):
    """「导航到充电站」整套与详情右上角 ✕ 已撤 (用户点名): 导航选单
    (挑地图 App / 长按隐藏 / ＋ 恢复 / GCJ-02 换算) 一并下线, 关闭走
    下滑/把手/蒙层/Esc。都不许回潮。"""
    page = served_page(auth, "/tesla")
    for gone in ('id="nav-go"', "导航到充电站", 'id="chg-nav-bd"',
                 'id="chg-nav-apps"', "charging-nav.js", "navHiddenApps",
                 "chgOpenNavChooser", "navAppUrl",
                 'id="chg-sheet-close"', 'class="sheet-close"',
                 "⚡ 快充", "🔌 慢充"):
        assert gone not in page, f"充电详情残留 {gone}"
    # Esc 一层一关 (2026-10-02 全弹窗「从哪来回哪去」): 关了层才拦断; 费用
    # 编辑框的 keydown 对 Esc 放行 —— 开层即自动聚焦, 掐死就永远 Esc 不掉
    assert 'if (!chgAlertBd.hidden) chgCloseAlert();' in page
    assert 'if (e.key === "Escape") return;' in page
