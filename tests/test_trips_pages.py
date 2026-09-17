"""行程页接线测试: 顶栏时间菜单 / 弹层把手 / 单列布局 / 消费与
司机筛选 / 实时能耗。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""

from tests.trips_page_assets import _trips_scripts

# ---------------------------------------------------------------- 页面
def test_trips_page_time_menu_and_filter_row(auth):
    """顶栏时间下拉 (快捷档 + 自定义日历) + 筛选行 (起终点省市区级联, 里程档),
    全部编码进 URL, 且与 ?id=/ ?ids= 深链共存。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ['id="time-menu"', 'data-v="24h"', 'data-v="7d"', 'data-v="30d"',
                 'data-v="180d"', 'data-v="1y"', 'data-v="all"',
                 'data-v="custom"', 'id="tm-cal"', 'id="tm-prev"', 'id="tm-next"',
                 'id="tm-ym"', 'id="tm-sel"', 'id="tm-apply"', 'function calRender()',
                 '再点结束日期', 'id="fc-menu"', 'id="tc-menu"', 'id="km-menu"',
                 # 时间菜单在顶栏 nav-row (全站统一位置)
                 '</details>\n    <details class="nav-menu time-menu" id="time-menu">',
                 'data-k="0-20"', 'data-k="20-100"', 'data-k="100-300"',
                 'data-k="300+"', "/tesla/trips/api/regions",
                 "function filterQS()", "function listURL(", "function syncURL()",
                 "function bindLocMenu(", 'class="menu loc-menu"',
                 'p.set("from_loc", state.fromLoc)', 'p.set("km_min", kb.min)',
                 # 手机: 下拉面板锚全宽 header (日历行 ~300px, 挂胶囊右缘必出屏)
                 '@media (max-width: 479px)', '.nav-menu { position: static; }']:
        assert frag in html, f"行程页缺少 {frag}"
    assert "chips-range" not in html and "/tesla/trips/api/cities" not in html
    assert 'id="tm-from"' not in html
    for i in ('time-menu', 'time-lb', 'time-opts', 'tm-dates', 'tm-cal', 'tm-prev',
              'tm-next', 'tm-ym', 'tm-sel', 'brand-menu', 'logout',
              'fc-opts', 'tc-opts', 'km-opts'):
        assert html.count(f'id="{i}"') == 1, f"页面 {i} 重复"
    # 筛选行太宽时手机端自己横滑, 不把整个页面带着滑 (下拉锚在 header 不受裁)
    assert ".filters { overflow-x: auto; scrollbar-width: none; }" in html
    assert ".filters::-webkit-scrollbar { display: none; }" in html


def test_trips_page_sheet_grab_drag_close(auth):
    """轨迹弹层手柄: 点一下关, 拖 >90px 松手也关 (pointer 统一触摸/鼠标,
    跟手 + 回弹); 拖过 8px 抑制随后的 click, 不把刚弹回的弹层又关掉。"""
    html = auth.get("/tesla/trips").text
    js = _trips_scripts(auth)
    both = html + js
    for frag in ['id="grab"', "touch-action: none", ".grab::before",   # 整行命中区
                 'window.addEventListener("pointermove", move)',
                 'window.addEventListener("pointerup", release)',
                 'window.removeEventListener("pointermove", move)',
                 "translateY(${dy}px)", "if (dy > 90) closeTrip()",
                 "e.stopImmediatePropagation()"]:
        assert frag in both, f"行程页缺少 {frag}"
    assert "setPointerCapture(e.pointerId)" not in both   # iOS touch 指针 capture 即 cancel, 别回潮
    assert '$("#grab").addEventListener("click", closeTrip);' not in js
    assert 'grab.addEventListener("touchstart"' not in js   # 手柄不吃旧 touch 三件套


def test_trips_page_has_playbar_and_single_column(auth):
    """播放控制条 + 单列列表 都在页面上; 统计格不占地图高度。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ['id="playbar"', 'id="pb-toggle"', 'id="pb-seek"', 'id="pb-speed"',
                 'id="sh-cell-pw"', 'id="sh-pw-lb"', "ICON_REPLAY",
                 # 播放条是贴弹层底部的浮层玻璃胶囊 (不占一整行), 地图
                 # margin-bottom 让位 —— 跟车的动态轨迹不再被控制条压住;
                 # 统计格单行横滑 (不折 2×3 网格), 弹层整体加高
                 "position: absolute; left: 14px; right: 14px;",
                 "margin-bottom: 62px;",
                 "backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);",
                 "overflow-x: auto; scrollbar-width: none;",
                 "height: 82vh; height: 82dvh;",
                 "flex: none; background: var(--surface); border-radius: 12px; padding: 8px 12px;",
                 # 视角基线: 播放条上加减按钮, 随速变焦整条平移
                 'id="pb-zout"', 'id="pb-zin"', 'id="pb-zval"',
                 "bumpZoomBias", "trip-zoom-bias",
                 # 开场视角直接到位 (不缓动), 档位取整避开 AMap 小数吸附
                 "zoom = Math.round(zoom);", "tripMap.setZoom(zoom, true)",
                 'id="list"', "最高车速"]:
        assert frag in html, f"行程页缺少 {frag}"
    assert "spd-legend" not in html   # 速度图例已按需求移除
    # 刷新: 顶栏按钮 (下拉手势已按需求撤掉)
    for frag in ['id="refresh-btn"', "function refreshList(",
                 "refresh-spin", 'body.selecting #refresh-btn']:
        assert frag in html, f"行程页缺少刷新片段 {frag}"
    assert 'id="ptr"' not in html and "setupPullRefresh" not in html
    # 瀑布流的列容器已删
    assert "m-col" not in html


def test_trips_page_consumption_and_driver_filter(auth):
    """卡片与弹层显示总电耗/平均电耗; 筛选行有驾驶员菜单且请求带驾驶员参数。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in [
        'id="sh-cell-kwh"', 'id="sh-cell-avg"',       # 弹层: 总电耗/平均电耗格
        'class="ct-cells"',                            # 卡片统计瓷砖 (量): 里程/时长/总电耗
        "总电耗", "平均电耗 ${num(it.wh_per_km, 0)}",     # 率 (均速/平均电耗) 收进子行
        'id="drv-menu"', 'id="drv-opts"', 'id="drv-lb"',   # 驾驶员筛选菜单
        'p.set("driver_id", state.drvId)',            # 列表请求/地址栏都带驾驶员
        "function fillSheetHeader(",                  # 弹层填充电耗格
    ]:
        assert frag in html, f"行程页缺少 {frag}"
    # 电耗格初始隐藏, 有数据才亮 (充电换算系数缺失时整块不出)
    assert 'id="sh-cell-kwh" hidden' in html
    # 驾驶员菜单没配驾驶员时整颗藏掉
    assert 'id="drv-menu" hidden' in html


def test_trips_page_live_energy_and_standalone(auth):
    """播放中电耗/平均电耗按能耗模型动态累积; 桌面图标全屏 meta。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in [
        # 能耗模型: 每公里 = 滚阻 + 风阻·v², 全程定标到整体 kWh
        "const energyWeightKm = v => 1 + 3 * Math.pow(v / 100, 2);",
        "function energyStep(pts, cum, i) {",
        "ecum.push(ecum[i - 1] + TripPlayback.energyStep(pts, cum, i));",
        # setLive: 两格都随模型走 (流式追加段也延伸权重)
        "const kwhNow = it.kwh * eNow / ecum[N - 1];",
        'num(kwhNow / kmNow * 1000, 0) + "</span><small>Wh/km</small>"',
        # 收尾 setOfficial 定格回整体值
        'if (it.kwh != null) $("#sh-kwh").innerHTML = \'<span class="n">\' + num(it.kwh)',
        '$("#sh-avg").innerHTML = \'<span class="n">\' + num(it.wh_per_km, 0)',
        # 桌面图标全屏: trips 页曾缺 standalone meta, 从其他页切过来会被
        # iOS 弹回 Safari 露地址栏 (其余页都有, 本页补齐)
        'name="apple-mobile-web-app-capable" content="yes"',
        'name="apple-mobile-web-app-status-bar-style" content="black-translucent"',
    ]:
        assert frag in html, f"行程页缺少 {frag}"


def test_trips_page_playback_pacing_and_nowrap(auth):
    """超长轨迹不再 12 秒放完: 时长含里程分量 + 0.5× 慢速档; 统计值不折行。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in [   # 时长公式在 animDurMs (预载扫路共用, 口径一致)
                 "Math.min(Math.max(n / 300, 3 + km * 1.4), 300)",
                 "PB_SPEEDS = [0.5, 1, 2, 4, 8]",
                 "white-space: nowrap",
                 # 进度条是播放条里唯一可缩项: flex 项 <input> 默认 min-width:auto
                 # = 控件内在宽 (Chromium 129px / Safari 更宽), 不压 0 的话
                 # 窄屏会把 +/− 视角钮挤出屏幕右缘 (E2E repro54)
                 "flex: 1; min-width: 0;"]:
        assert frag in html, f"行程页缺少 {frag}"
    # 时长紧凑格式 (两个页面统一)
    assert "`${h}时${m ? m + \"分\" : \"\"}`" in html
