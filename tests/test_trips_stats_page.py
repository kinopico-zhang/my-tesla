"""行程详情左滑动态页测试 (2026-09-22 用户点名「往左划显示行程统计页面」→
后点名「统计改成动态, 整个页面都换掉」→ 2026-09-23 点名「不需要动画,
直接展示全貌」): 整页对换的分页容器/三张图卡的 markup 与样式。三页独立
(2026-09-27 用户点名「三个页面不需要联动…地图大小不要变来变去, 柱状图
大小也不要变来变去」): 每页自带完整布局, 数字带/播放条住回轨迹页, 翻页
不收不还, 三页互不联动 (空态各跟各的数据)。切页接线/退役禁词/版本钉
2026-09-26 拆去 test_trips_stats_wiring.py, 三图曲线与直方图画法拆去
test_trips_stats_charts.py (这边满 200 行硬上限)。纯函数 (kwhAt/
niceCeil) node 直测见 tests/js/trips-sheet-stats.test.mjs。"""
from tests.tesla_static_files import served_page


def test_stats_pager_markup(auth):
    """三页整页对换, 各页自有完整布局 (2026-09-27 三页独立: 轨迹页 = 地图
    + 数字带 + 播放条, 动态页/统计页 = 自己的图卡, 互不联动、布局恒定);
    页底页签与图卡标题 (2026-09-23 用户点名撤掉) 都不在了 —— 切页靠横滑
    + 点底行页标区 (2026-09-24 用户点名; 右上角页标题同日让位给驾驶员),
    图上轴名/刻度照旧 (2026-09-25「只要柱状图」一轮曾整批撤掉, 同日用户
    澄清原意是撤图下面的带子, 全部复原), 数值点查/点柱读出。空态各跟各
    的数据: 动态页等数据会话 (curSess, 不等地图预载), 统计页等服务端直
    方图 (开弹层即取) —— 轨迹没加载完不再拖累另两页转圈。"""
    html = served_page(auth, "/tesla")
    for frag in [
        '<div class="tp-pager" id="tp-pager">',
        '<div class="tp-track">',
        '<section class="tp-stats" id="tp-stats">',
        'id="tps-cv-spd"',
        'id="tps-card-kwh"', 'id="tps-cv-kwh"',
        'id="tps-card-alt"', 'id="tps-cv-alt"',
        'id="tps-empty">数据加载中…</p>',
        # 弹层头部右上角 (2026-09-24 用户点名): 页标题退役, 该位让给驾驶员
        # 纯文字按钮 (从左串时间后挪来; 没配驾驶员/合并多段 JS 整颗藏)
        '<button type="button" class="sh-drv" id="sh-drv-btn" aria-label="切换驾驶员" hidden></button>',
        # 弹层底一行 (2026-09-23 用户点名: 最下方的空白放当前页标题 + 白点
        # 页标, 类似 iOS 桌面的白点): 轨迹页「行驶轨迹」/ 动态页「行驶数
        # 据」/ 统计页「行驶统计」, 三枚圆点亮当前页 (JS 切页同步);
        # 2026-09-24 用户点名竖排 —— 圆点在上标题在下, 点整块切下一页
        '<div class="tp-foot" id="tp-foot">',
        '<span class="tp-dots" id="tp-dots"><i class="on"></i><i></i><i></i></span>',
        '<span class="tp-foot-lb" id="tp-foot-lb">行驶轨迹</span>',
        # 第三页「行驶统计」(2026-09-23 用户点名, 同日点名拆两张卡, 2026-09-24
        # 对账官方口径换三张): 速度直方图 / 各档里程 / 各档平地电耗各一张卡
        # (点柱读值); 自己的空态 (统计读取中, 不跟轨迹加载联动)
        '<section class="tp-hist" id="tp-hist">',
        'id="tps-cv-hist"',
        'id="tps-card-histkm"', 'id="tps-cv-histkm"',
        'id="tps-card-hist2"', 'id="tps-cv-hist2"',
        'id="tps-empty-h">统计读取中…</p>',
    ]:
        assert frag in html, f"动态页 markup 缺 {frag}"
    # 底行在动态页之后、分页容器外 (吃掉原来最下方的空白, 贴弹层底);
    # 统计页排在动态页后、底行前 (分页容器里的第三页); 底行竖排: 圆点在
    # 上标题在下 (2026-09-24 用户点名)
    assert html.index('class="tp-stats"') < html.index('id="tp-hist"')
    assert html.index('id="tp-hist"') < html.index('id="tp-foot"')
    assert html.index('id="tp-dots"') < html.index('id="tp-foot-lb"')
    # 右上角页标题 2026-09-24 退役 (让位给驾驶员): markup 与 JS 一根不留
    assert "sh-page" not in html and "sh-page" not in \
        auth.get("/tesla/static/js/view/trips-sheet-stats.js").text
    # 速度/电耗卡的副行 (最高·平均 / 总·平均) 2026-09-22 用户点名撤了; 海拔
    # 卡的爬升/最高副行随 2026-09-23 静态全量改造撤 (不再算到车头)
    assert "tps-sub-spd" not in html and "tps-sub-kwh" not in html \
        and "tps-sub-alt" not in html
    # 图卡标题行与播放头竖线元素 2026-09-23 用户点名退役 (不带标题 / 全量
    # 静态, 不跟播放走): markup 与样式一根不留
    assert "tps-head" not in html and "tps-cur" not in html
    # 三页独立 (2026-09-27 用户点名「三个页面不需要联动…地图大小不要变
    # 去变」): 数字带/播放条住回轨迹页 (2026-09-25 三页等高修平时曾挪出
    # 分页当公共带 + 二三页整带收放, 带子一收一还地图就变一次大小 —— 「地
    # 图大小变来变去」正是这么来的, 整套撤掉) —— 轨迹页自带地图+数字带+
    # 播放条, 排序: 轨迹页 (地图→数字带→播放条) → 动态页 (下方另钉底行序)
    assert html.index('class="tp-track"') < html.index('class="trip-map-wrap"')
    assert html.index('class="trip-map-wrap"') < html.index('class="sh-cells sheet-drag"')
    assert html.index('class="sh-cells sheet-drag"') < html.index('id="playbar"')
    assert html.index('id="playbar"') < html.index('class="tp-stats"')
    # 页底页签整块撤掉 (2026-09-22 用户点名): 切页只剩横滑
    assert "tp-tabs" not in html and "tp-tabs" not in \
        auth.get("/tesla/static/css/tesla-trips-sheet.css").text


def test_stats_pager_css(auth):
    """分页是原生 snap 横滚 (音乐 App 设置/搜索子页同款); 数字带/播放条是
    轨迹页自己的两行 (2026-09-27 三页独立: 布局恒定, 翻页不收不还), 整带
    收放规则一根不留; touch-action 只落在动态页 (给容器声明会把地图自己
    的手势也劫去滚页); 动态页一页塞下不滚屏 (图卡 flex:1 均分页高, 曲线
    高度跟卡走, 两卡/三卡都自动铺满); 进度条的手势仍拦死 (拖进度别漏给
    任何横向消费方)。"""
    css = auth.get("/tesla/static/css/tesla-trips-sheet.css").text
    for frag in [
        "scroll-snap-type: x mandatory; overscroll-behavior-x: contain;",
        ".tp-track {",   # 轨迹页: 地图 + 数字带 + 播放条 (各页自有布局)
        "scroll-snap-align: start;\n  display: flex; flex-direction: column;",
        ".trip-map-wrap {",   # 地图区: 轨迹页主区
        "position: relative; flex: 1; min-height: 0;",
        ".sh-cells {", "gap: 8px;\n  margin: 8px 0 0;",   # 轨迹页数字带: 贴地图下, 底缝归播放条
        # 动态页不滚屏: overflow hidden + 图卡均分页高 (用户点名「搞扁一点,
        # 放到一个页面里, 不要滚屏」); 手势放行收纯横轴 (2026-09-27 用户实报
        # 「还是不灵敏, 卡卡的」): 竖向整链没得滚, pan-y 只是喂 iOS 仲裁一个
        # 认不出的轴 —— 横滑定轴慢半拍/斜起手半路死掉, 只能等松手转发 (不跟手)
        ".tp-stats {", "scroll-snap-align: start;\n  overflow: hidden;",
        "touch-action: pan-x;",
        ".tps-card {", "flex: 1; min-height: 0; background: var(--surface); border-radius: 14px;",
        ".tps-chart { position: relative; flex: 1; min-height: 0; }",
        # 弹层底一行 (2026-09-23 用户点名用最下方的空白): 主区竖排 —— 分页
        # flex:1 吃满, 底行页标题 + 白点页标贴底; #sheet 底衬从 +22px 收到
        # +8px (空白改放底行)
        ".tp-pager-zone { position: relative; flex: 1; min-height: 0;",
        "display: flex; flex-direction: column; }",
        "flex: 1; min-height: 0; display: flex;",
        "padding: 10px 20px calc(env(safe-area-inset-bottom) + 8px);",
        # 弹层底一行 (2026-09-23 用户点名: 页标题 + iOS 桌面同款白点页标;
        # 2026-09-24 点名竖排: 圆点在上标题在下, 点整块切下一页 → cursor)
        ".tp-foot { flex: none; display: flex; flex-direction: column; align-items: center;",
        "justify-content: center; gap: 6px; padding: 8px 0 2px;",
        "cursor: pointer; -webkit-tap-highlight-color: transparent; }",
        # 页标文字是页面标题不是脚注 (2026-09-24 用户点名放大: 12→14 加粗)
        ".tp-foot-lb { font-size: 14px; font-weight: 600; color: var(--ink-2); }",
        ".tp-dots {",
        ".tp-dots i {", ".tp-dots i.on { background: #f5f5f7; }",
        # 第三页「行驶统计」: 与动态页同款整页布局 (一张直方图卡吃满页高)
        ".tp-hist {", "scroll-snap-align: start;\n  overflow: hidden;",
    ]:
        assert frag in css, f"动态页样式缺 {frag}"
    # 图卡标题/播放头竖线的样式随 markup 退役 (2026-09-23): 不许回潮
    assert "tps-head" not in css and "tps-cur" not in css
    # 双轴放行不许回潮 (2026-09-27 收纯横轴定案的禁词): 统计页同款 pan-x
    assert "pan-x pan-y" not in css
    pb = auth.get("/tesla/static/css/tesla-trips-playback.css").text
    # 播放条 = 轨迹页底一行 (2026-09-22 用户点名「不放地图里」; 更早的让位
    # 带方案两头挨批: 底部没吃满 + 控制框周围黑边): 不播整行收掉不占位,
    # 播放中数字带下展开, 投影撤掉; 进分页的进度条 touch-action 拦滚 (拖
    # 进度不被滚页抢走); 视角基线回贴地图右下角
    assert "flex: none; margin: 8px 0 0;" in pb
    pb_block = pb[pb.index(".playbar {"):pb.index("}", pb.index(".playbar {"))]
    assert "box-shadow" not in pb_block   # 播放条投影撤掉 (黑边观感来源); pb-zoom 浮地图上照留
    assert "position: absolute; right: 10px; bottom: 10px; z-index: 12;" in pb
    assert "flex: 1; min-width: 0; touch-action: none;" in pb
