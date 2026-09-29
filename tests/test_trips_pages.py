"""行程视图接线测试: 单列布局 / 消费与司机筛选 / 实时能耗。
拆自 test_trips.py (结构化重构; P7 起按 3.0 单壳改口径 —— 时间档在抽屉,
起终点/里程/驾驶员是屏底筛选条 chips); 弹层头部/把手/拖关 2026-09-26
拆去 test_trips_sheet_dom.py (这边满 200 行硬上限)。"""

from tests.tesla_static_files import served_page

# ---------------------------------------------------------------- 视图
def test_trips_view_filter_chips(auth):
    """屏底筛选条 chips: 起终点省市区级联 (树按当前车重拉) + 里程档 +
    驾驶员 (没配过驾驶员整枚不出现); 偏好住 localStorage, 深链加载期消费。"""
    html = served_page(auth, "/tesla")
    for frag in ['registerChips("trips"',
                 'buildTrLocPop(p, "fromLoc", "start")',
                 'buildTrLocPop(p, "toLoc", "end")',
                 '"起点: "', '"终点: "', "KM_BUCKETS", '"里程: "',
                 'v: "0-20"', 'v: "20-100"', 'v: "100-300"', 'v: "300+"',
                 "/tesla/trips/api/regions",
                 'class="loc-back"', 'class="loc-crumb"', 'class="loc-row',
                 "钻下一级", "trSaveFilters", "resetList",
                 'p.set("from_loc", state.fromLoc)', 'p.set("km_min", kb.min)',
                 'p.set("driver_id", state.drvId)',
                 "drivers.some(d => d.id === state.drvId)"]:   # 已删驾驶员回落全部
        assert frag in html, f"行程视图缺少 {frag}"


def test_trips_view_has_playbar_and_single_column(auth):
    """播放控制条 + 单列列表 都在; 统计格不占地图高度。"""
    html = served_page(auth, "/tesla")
    for frag in ['id="playbar"', 'id="pb-toggle"', 'id="pb-seek"', 'id="pb-speed"',
                 'id="sh-cell-pw"', 'id="sh-pw-lb"', "ICON_REPLAY",
                 # 播放条是轨迹页底一行玻璃胶囊 (不占地图, 2026-09-22 用户
                 # 点名「播放按钮不要放在地图里面」): 不播时整行收掉不占位
                 # (页面吃满), 播放中数字带下方展开; 投影撤掉 (深底上那圈
                 # 黑影就是「周围黑边」); 统计格两行网格 (不横滑, 用户点名
                 # 四向不可滚), 弹层溢出全裁
                 "flex: none; margin: 8px 0 0;",
                 "gap: 8px;\n  margin: 8px 0 0;",
                 "backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);",
                 "grid-template-columns: repeat(3, 1fr);",
                 "display: flex; flex-direction: column; overflow: hidden;",
                 "height: 82vh; height: calc(var(--shell-h, 100dvh) * .82);",
                 "background: var(--surface); border-radius: 12px; padding: 6px 10px;",
                 # 视角基线: 加减按钮浮在地图右下角 (用户点名从播放条挪出),
                 # 显隐随播放条 (loop 开 / bar 停各同步一行); 播放条搬出地图
                 # 后回贴地图右下角
                 'id="pb-zoom"', 'id="pb-zout"', 'id="pb-zin"', 'id="pb-zval"',
                 "position: absolute; right: 10px; bottom: 10px; z-index: 12;",
                 '$("#pb-zoom").hidden = false;', '$("#pb-zoom").hidden = true;',
                 "bumpZoomBias", "trip-zoom-bias",
                 # 开场视角直接到位 (不缓动), 档位取整避开 AMap 小数吸附
                 "zoom = Math.round(zoom);", "tripMap.setZoom(zoom, true)",
                 'id="list"', "最高车速", "function refreshList("]:
        assert frag in html, f"行程视图缺少 {frag}"
    assert "spd-legend" not in html   # 速度图例已按需求移除
    # 刷新: 抽屉按钮 + 滚动器在顶下拉 (test_shell_wiring 钉); 瀑布流列容器已删
    assert "m-col" not in html


def test_trips_view_consumption_and_driver_filter(auth):
    """卡片显示总电耗 (均速/平均电耗子行已删, 用户点名); 弹层保留
    总电耗/平均电耗格; 驾驶员 chip 选项来自设置视图驾驶员表,
    列表请求带驾驶员参数。"""
    html = served_page(auth, "/tesla")
    for frag in [
        'id="sh-cell-kwh"', 'id="sh-cell-avg"',       # 弹层: 总电耗/平均电耗格
        'class="ct-cells"',                            # 卡片统计瓷砖 (量): 里程/时长/总电耗
        "总电耗",
        "buildDrvPop", "drvLabel",                     # 驾驶员筛选 chip
        "function fillSheetHeader(",                   # 弹层填充电耗格
    ]:
        assert frag in html, f"行程视图缺少 {frag}"
    # 电耗两格常驻 (用户点名「没数据的就显示占位」): 换算系数缺失/里程
    # 不足 1km 时显示 —, 不再整格藏掉忽隐忽现
    assert 'id="sh-cell-kwh" hidden' not in html
    assert 'id="sh-cell-avg" hidden' not in html
    # 卡片子行已删 (均速/平均电耗), 精确模板不许回潮 (播放内核注释里有"均速"字样)
    assert "ct-sub" not in html
    assert "均速 ${avg}" not in html
    assert "平均电耗 ${num(it.wh_per_km, 0)}" not in html


def test_trips_card_place_line_marquee_and_driver_pick(auth):
    """行程卡片起终点 (用户点名): 最小两段「区 · 地名」并成一行 (绿点起 →
    橙点终), 放不下挂 .marquee 来回滚 (音乐迷你条同款, 两端各停一拍);
    点右上角驾驶员 pill 直接弹底部小选单标注, 不用进详情 (写库就地更新
    与弹层下拉框共用一途, 换出的新卡要重量跑马灯)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        "function shortPlace(",
        # 起终点只看省市区链, 取「城市 + 最小行政级」([省,市,区]→后两段 /
        # [省,市]→市), 地名 (POI) 不再混进来 —— 充电列表 fmtPlaceShort 另一套
        "seg.length >= 3 ? seg.slice(-2) : seg.slice(-1)",
        "shortPlace(it.from_region, it.from)",
        'class="ct-addr mq-line"', '<span class="mq-run"><i class="dot f"></i>',
        '<span class="arr">→</span><i class="dot t"></i>',
        "function marqueeCards(", 'run.classList.add("marquee")',
        "setProperty(\"--mq-dx\"",
        "animation: mq-scroll var(--mq-dur, 12s) linear "
        "infinite alternate;",
        # 视图藏着量不出宽 (clientWidth 0) 不挂, 转屏防抖重量
        "if (!line.clientWidth) continue;",
        'id="drv-pop"', "function openDrvPick(", "async function assignDriver(",
        'e.target.closest(".ct-drv")', 'id="drv-pop-x"',
        "还没添加驾驶员",
    ]:
        assert frag in html, f"行程卡片缺少 {frag}"
    # 两行旧地址写法已删 (整链 from/to 仍下发, 播放会话在用)
    assert "${esc(it.from)}" not in html


def test_trips_view_live_energy_and_standalone(auth):
    """播放中电耗/平均电耗按能耗模型动态累积; 桌面图标全屏 meta。"""
    html = served_page(auth, "/tesla")
    for frag in [
        # 能耗模型: 每公里 = 滚阻 + 风阻·v², 全程定标到整体 kWh
        "const energyWeightKm = v => 1 + 3 * Math.pow(v / 100, 2);",
        "function energyStep(pts, cum, i) {",
        "ecum.push(ecum[i - 1] + TripPlayback.energyStep(pts, cum, i));",
        # setLive: 两格都随模型走 (流式追加段也延伸权重); 追加期定标分母
        # 只盖已载段, 全组总电耗按已载里程占官方总里程折算 (2026-09-23
        # 用户实报十一云南游首段五位数 Wh/km), 载齐 more=false 比例恒 1
        "const scale = more && it.km > cum[N - 1] ? cum[N - 1] / it.km : 1;",
        "const kwhNow = it.kwh * scale * eNow / ecum[N - 1];",
        'kwhNow.toFixed(1) + "</span><small>kWh</small>"',
        'num(kwhNow / kmNow * 1000, 0) + "</span><small>Wh/km</small>"',
        # 收尾 setOfficial 定格回整体值 (恒一位小数, 与 setLive 同宽不跳格)
        'Number(it.kwh).toFixed(1) + "</span><small>kWh</small>"',
        '$("#sh-avg").innerHTML = \'<span class="n">\' + num(it.wh_per_km, 0)',
        # 桌面图标全屏: 3.0 壳是唯一页面, meta 必在 (全屏 App 不被弹回 Safari)
        'name="apple-mobile-web-app-capable" content="yes"',
        'name="apple-mobile-web-app-status-bar-style" content="black-translucent"',
    ]:
        assert frag in html, f"行程视图缺少 {frag}"


def test_trips_view_playback_pacing_and_nowrap(auth):
    """超长轨迹不再 12 秒放完: 时长含里程分量 + 0.5× 慢速档; 统计值不折行。"""
    html = served_page(auth, "/tesla")
    for frag in [   # 时长公式在 animDurMs (预载扫路共用, 口径一致)
                 "Math.min(Math.max(n / 300, 3 + km * 1.4), 300)",
                 "PB_SPEEDS = [0.5, 1, 2, 4, 8]",
                 "white-space: nowrap",
                 # 进度条是播放条里唯一可缩项: flex 项 <input> 默认 min-width:auto
                 # = 控件内在宽 (Chromium 129px / Safari 更宽), 不压 0 的话
                 # 窄屏会把 +/− 视角钮挤出屏幕右缘 (E2E repro54)
                 "flex: 1; min-width: 0;"]:
        assert frag in html, f"行程视图缺少 {frag}"
    # 时长紧凑格式 (两个页面统一)
    assert "`${h}时${m ? m + \"分\" : \"\"}`" in html
