"""行程统计视图骨架测试 (2026-09-27 拆自 test_trip_stats.py —— 司机里程
分布批次把那边顶到 200 行硬上限; 接口测试留在原处, 这里只钉壳内视图)。"""
import re

from tests.tesla_static_files import served_page


def test_tripstats_view_skeleton(auth):
    """行程统计视图骨架: 一级标题 + 统计卡行 + 八张图表卡 (月度趋势两幅
    柱状 + 出发时段/常去地点/驾驶员/距离/时长/车速/速度·电耗), 与充电统计
    同款布局 (ts- 前缀自家一份 id; 图表底座/落档器/统计卡样式复用充电
    统计的全局)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        '<div class="sec-head"><h2>行程统计</h2></div>',
        'class="stats-grid" id="ts-row"',
        'id="view-tripstats"', 'data-view="tripstats"',
        'id="ts-row"', 'id="ts-grid"',
        'id="chart-ts-km"', 'id="chart-ts-kwh"',       # 月度两幅柱状
        '<span class="mc-name">月度里程</span>', 'id="ts-km-total"',
        '<span class="mc-name">月度电耗</span>', 'id="ts-kwh-total"',
        'id="ts-slider-row"', 'id="ts-window"',        # 共享时间窗滑块 (range)
        'id="ts-win-first"', 'id="ts-win-last"',
        'id="chart-ts-hour"', 'id="chart-ts-loc"',
        'id="chart-ts-drv"', 'id="chart-ts-dist"', 'id="chart-ts-dur"',
        'id="chart-ts-spd"', 'id="chart-ts-wh"',
        '<div class="cc-title">出发时段</div>',
        '<div class="cc-title">常去地点</div>',
        '<div class="cc-title">驾驶员里程分布</div>',   # 2026-09-30 改名 (原司机里程分布)
        '<div class="cc-title">单程距离分布</div>',
        '<div class="cc-title">行驶时长分布</div>',
        '<div class="cc-title">车速分布</div>',
        '<div class="cc-title">速度·电耗</div>',        # 2026-09-30 重做 (原平均电耗分布)
        '"/tesla/trips/api/stats/summary?"',           # 五路统计接口
        '"/tesla/trips/api/stats/monthly?"',
        '"/tesla/trips/api/stats/locations?"',
        '"/tesla/trips/api/stats/drivers?"',
        '"/tesla/trips/api/stats/dimensions?"',
        "tsRenderMonthly", "tsRenderLocations",         # 图表渲染器
        "tsRenderDrivers", "tsRenderHour", "tsRenderDist",
        "tsRenderDur",
        "tsRenderSpd", "tsRenderWh",
        "TS_MONTH_WINDOW", "tsDrawWindow",              # 12 个月窗口 + 滑块重绘
        "tsValueFromCenter",                            # 滑块拖拽自管指针 (同充电款)
        'setProperty("--win"',                          # 滑块块身宽度 = 12/N 轨道宽
        "DIST_LB", "TDUR_LB", "SPD_LB",                # 落档区间文案 (副题/气泡)
        "DIST_AX", "TDUR_AX", "SPD_AX", "WH_COLORS",   # 轴标 = 档位起点 + 电耗柱色
        'id="ts-spd-sub">按车速分组的行驶里程',      # 车速图 = 真速度分布
        'id="ts-drv-sub">按驾驶员标注归集',        # 驾驶员图 = 里程归集口径
        'id="ts-wh-sub">行车功率积分 (含动能回收)',  # 速度·电耗口径
        'mkChart("tsDrv")',                         # 横向条形 (2026-09-30 用户点名)
        "thousands(Math.round(over120))",            # 副题报里程 (km) 不报次数
        "${num(bins[i])} km</b>",                    # 气泡同口径
        'mkChart("tsWh")',                           # 速度·电耗 (不用落档底座了)
        "by_spd_kwh",                                # 段电量 ÷ 段里程 = 平均电耗
        'registerView("tripstats"',                     # 生命周期 (echarts 按需注入)
        "tsBooted",                                     # 首次进视图才 boot
        'bindGestures(tsScroll, { drawer: true, ptr: true, onRefresh: tsRefetch })',
        'title: "行程统计"',
    ]:
        assert frag in html, f"行程统计视图缺少 {frag}"
    assert 'class="chart-box chart-monthly-pair" id="chart-ts-km"' in html
    # 2026-09-28 名字类条形图改竖排; 2026-09-30 常去地点柱位定 12 根 (用户
    # 点名「就保留 12 个吧」—— 副题把全量地点数说全, 加高 340 见
    # #chart-ts-loc 规则), 柱名挂点击开改名弹层 (trips-place-dialog);
    # 驾驶员里程分布改横向条形 (名字横排不截断, 高度 JS 随人数走 ——
    # 两图都不再挂 vlabel 家族类); 气泡按下标取行 —— 旧版按名字 find,
    # 截断过的名字对不上会炸 (服务日志 window_error 实锤)
    assert 'class="chart-box" id="chart-ts-loc"' in html
    assert 'class="chart-box" id="chart-ts-drv"' in html
    ts_charts = auth.get("/tesla/static/js/view/trips-stats-charts.js").text
    assert ts_charts.count(
        "rows.map(d => stackLabel(truncateName(d.name, 10)))") == 1
    assert "tLocData.find" not in ts_charts
    assert "tLocData.slice(0, 12)" in ts_charts        # 柱位画最常 12 根
    # 柱名可点要两面旗: 轴级 triggerEvent 挂 eventData (componentType/dataIndex),
    # axisLabel 级保标签非静默 —— 只写后者点了不响 (v7-v9 实踩, 用户报「点
    # 地名没弹重命名」)
    assert ts_charts.count("triggerEvent: true") == 2
    assert 'mkChart("tsLoc").on("click"' in ts_charts
    # 柱顶不标次数 (用户点名「不需要在柱状图上面标记次数」), 看数走气泡;
    # 气泡口径 = 停车次数 (2026-09-30 用户点名「只看我停车是在哪, 而不是
    # 路过哪」—— 旧「起终点并计」翻倍账不许回潮)
    assert 'formatter: "{c} 次"' not in ts_charts
    assert "次停车 (挪车不计)" in ts_charts
    assert "起终点并计" not in ts_charts
    # 只有柱名 (xAxis 轴标签) 开弹层 —— 柱身点按留给气泡看数 (用户点名
    # 「点击文字才弹出框, 点击柱状图只显示数据」, v8 曾放开柱身又收回)
    assert 'if (e.componentType !== "xAxis") return;' in ts_charts
    assert 'e.componentType !== "series"' not in ts_charts
    assert "openPlaceDialog(row, loadTAll)" in ts_charts
    assert "type: \"category\", inverse: true" in ts_charts   # 驾驶员横向
    # inverse 翻身把默认 'end' 轴名带到轴底压横轴 (2026-09-30 用户报) —
    # 钉 start 翻回顶端
    assert 'nameLocation: "start"' in ts_charts
    # 2026-09-30 用户点名「横纵坐标都要标记是什么」: 数值轴标单位 /
    # 类目轴标内容, 轴名样式一份 (axNameStyle) 全图共用
    assert ts_charts.count("nameTextStyle: axNameStyle") >= 8
    for unit in ('name: "km"', 'name: "kWh"', 'name: "次数"', 'name: "点"',
                 'name: "km/h"', 'name: "Wh/km"', 'name: "地点"', 'name: "月份"'):
        assert unit in ts_charts, f"轴名缺 {unit}"
    # 统计样式已类化 (充电统计的 id 规则退役, 行程统计视图复用): 月度双柱
    # 降高/滑块轨道/网格 dim 全走类选择器 (拼串口径下 JS 的 $("#...") 撞
    # 不上 CSS 选择器, 这里钉 CSS 文件本身)
    stats_css = auth.get("/tesla/static/css/tesla-stats.css").text
    for gone in ("#chart-monthly-kwh", "#monthly-window", "#charts-grid"):
        assert gone not in stats_css, f"统计样式 id 规则残留: {gone}"
    assert ".chart-monthly-pair { height: 180px; }" in stats_css
    assert ".mc-slider input[type=\"range\"] {" in stats_css
    assert ".charts-grid.dim { opacity: .45; pointer-events: none; }" in stats_css
    assert "#chart-ts-loc { height: 340px; }" in stats_css   # 12 根竖排标签加高一档


# 图表消费方 (mkChart/renderDimBins 的字面键都在这六个文件里)
CHART_CONSUMERS = ("stats-chart-trend.js", "stats-chart-dimensions.js",
                   "stats-page.js", "trips-stats-page.js",
                   "trips-stats-charts.js", "battery-page.js")


def test_chart_registry_covers_every_chart(auth):
    """图表位注册表对账 (2026-09-27 实锤翻车): mkChart(name) 从 CHART_ELS
    拿选择器, 键漏登记 → 选择器 undefined → echarts.init(null) 在压缩库里
    getAttribute 炸, 行程统计整页报「数据加载失败: null is not an object
    (evaluating 't.getAttribute')」—— 司机里程分布图首秀就漏了 tsDrv。两处
    手工同步的事实源 (消费方的图键 × 注册表 × 壳里的图位 div) 靠对账钉死,
    缺哪个键立即红 (与抽屉 DRW_ICONS/NAV_GROUPS 对账同款规矩)。"""
    trend = auth.get("/tesla/static/js/view/stats-chart-trend.js").text
    reg = dict(re.findall(r'(\w+): "(#chart-[\w-]+)"', trend))
    assert "tsDrv" in reg                       # 本次翻车的键: 司机里程分布
    used = set()
    for fname in CHART_CONSUMERS:
        body = auth.get(f"/tesla/static/js/view/{fname}").text
        used |= set(re.findall(r'mkChart\("(\w+)"\)', body))
        used |= set(re.findall(r'renderDimBins\("(\w+)"', body))
    assert used <= set(reg), f"CHART_ELS 缺登记: {sorted(used - set(reg))}"
    html = served_page(auth, "/tesla")
    for name, sel in reg.items():
        assert f'id="{sel[1:]}"' in html, f"图位 {sel} ({name}) 不在壳里"
