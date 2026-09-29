"""行程弹层播放统计格测试: 海拔格撤除 (反向钉孤儿接线) / 功率千瓦口径 /
总电耗与功耗恒一位小数 / 数字定宽盒。2026-09-26 拆自
test_trips_playback_pages.py (那边满 200 行硬上限)。"""

from tests.tesla_static_files import page_asset_paths, served_page


def _trips_view_js(auth):
    """行程视图自有脚本拼起来 (整壳断言分不清视图时用)。"""
    return "".join(auth.get(ref).text for ref in page_asset_paths(auth, "/tesla")
                   if "/js/view/trips-" in ref)


def test_trips_page_playback_altitude_cell_removed(auth):
    """海拔格撤除 (2026-09-23 用户点名「海拔这个数据块去掉」): 播放期实时
    海拔 / 收尾定格爬升 / 开格占位三套写法 (fillSheetHeader / setLive /
    setOfficial / 开播 / 重播共 5 处接线) 连 markup 一起退场 —— 弹层撤元
    素的 JS 孤儿接线会当场崩 (老案见撤格不撤接线的事故档), 反向钉死一根
    不许回潮。载荷第 5 位海拔米照发 (动态页海拔曲线还吃它);
    trackutil.elevClimbM 留在工具库 (纯函数, node 直测, 不为撤格陪葬)。"""
    html = served_page(auth, "/tesla")
    assert "sh-alt" not in html, "海拔格 markup 残留"
    # (served_page 拼进了 trackutil 的注释「总爬升」, 全页禁词会误伤工具库,
    # 接线键是 sh-alt: markup+脚本一根不许剩)
    for name in ("js/view/trips-sheet-driver.js", "js/view/trips-playback-loop.js",
                 "js/view/trips-playback-session.js"):
        js = auth.get(f"/tesla/static/{name}").text
        assert "sh-alt" not in js, f"{name} 海拔格孤儿接线残留"
        assert "爬升" not in js, f"{name} 海拔格收尾口径残留"
    loop = auth.get("/tesla/static/js/view/trips-playback-loop.js").text
    assert "elevClimbM" not in loop, "收尾爬升接线残留"


def test_trips_page_playback_power_native_kw(auth):
    """功率全链路按 kW 读 (2026-09-22 动态页功率右轴挂不上牵出的老案):
    载荷 pts 每点第 4 位是功率, TeslaMate positions.power 原生就是
    千瓦 (smallint, 实测全库 -176~+254) —— 当年按瓦读, 「有功耗数据」
    的门槛写成 >500W, 千瓦量级的真实数据永远够不着, 轨迹页功耗格从上
    线起就没亮过。门槛改 0.5kW (初始判 + 流式追加段点亮两处同口径),
    显示不再除 1000, 时间加权平均改名 meanPowerKw 直读。
    2026-09-25 用户点名「数字你可以没有, 但是那个灰色的块要提前出现」:
    功耗格开弹层就常显 (开格/占位两路都亮格显 —, 数字播放开始才有),
    与总电耗/平均电耗格「数据缺席显占位」同一条规矩 —— 原先整格藏着,
    点播放那一刻才蹦出来还挤得邻居格挪位; hidden = !hasPower 那道闸
    照旧保留, 只作用在真没功耗数据的行程 (开播时收格)。"""
    sess = auth.get("/tesla/static/js/view/trips-playback-session.js").text
    drv = auth.get("/tesla/static/js/view/trips-sheet-driver.js").text
    loop = auth.get("/tesla/static/js/view/trips-playback-loop.js").text
    trackutil = auth.get("/tesla/static/js/trackutil.js").text
    # 开格门槛: 初始判 + 追加段点亮, 两处同口径 (漏一处流式行程格子亮不出)
    assert sess.count("Math.abs(p[3] || 0) > 0.5") == 2, "功耗门槛不是 kW 口径"
    assert '$("#sh-cell-pw").hidden = !hasPower;' in sess
    # 开弹层两路填格 (数据到/占位) 都把功耗格亮出来, 标签同步回「平均功耗」
    # (播放期 session 会改写「功耗」, 收尾 setOfficial 换回; 中途关弹层重开
    # 也不能带着播放期的旧标签)
    assert drv.count('$("#sh-cell-pw").hidden = false;') == 2, "开弹层没亮功耗格"
    assert drv.count('$("#sh-pw-lb").textContent = "平均功耗";') == 2, "占位路没回「平均功耗」标签"
    # 直读不折算: 实时格与收尾平均都是恒一位小数 kW (2026-09-25 起不再剪
    # .0 —— 播放中 12↔12.3 字宽抖, 总电耗恒一位同款, 见专门钉它的测试)
    assert 'pw.toFixed(1)) + "</span><small>kW</small>"' in loop
    assert 'mp.toFixed(1)) + "</span><small>kW</small>"' in loop
    assert "TrackUtil.meanPowerKw(pts, ts)" in loop
    assert "/ 1000" not in loop, "还有 W→kW 折算残留"
    # trackutil: 时间加权平均改名直读千瓦 (W 旧名不许回来)
    assert "function meanPowerKw(pts, ts)" in trackutil
    assert "meanPowerW" not in trackutil
    assert "meanPowerKw: meanPowerKw," in trackutil


def test_trips_page_playback_kwh_one_decimal_no_jitter(auth):
    """总电耗恒带一位小数 (2026-09-25 用户点名「总电耗这个动态数字一直加
    一个.0吧, 这样就不会抖动了」): num() 会把 12.0 剪成 12, 播放中数值在
    12↔12.3 间跳, 定宽盒里居中的数字串宽一变、数字就左右挪; 三处写法
    (setLive 每帧/setOfficial 定格/fillSheetHeader 开弹层) 全走 toFixed(1)
    恒宽 —— 漏一处会在开弹层或收尾时跳一次宽度。功耗格同一条规矩,
    .0 剪尾整个退役。"""
    loop = auth.get("/tesla/static/js/view/trips-playback-loop.js").text
    drv = auth.get("/tesla/static/js/view/trips-sheet-driver.js").text
    assert 'kwhNow.toFixed(1) + "</span><small>kWh</small>"' in loop
    assert 'Number(it.kwh).toFixed(1) + "</span><small>kWh</small>"' in loop
    assert 'Number(it.kwh).toFixed(1) + "</span><small>kWh</small>"' in drv
    # num() 的 .0 剪尾不许再回到这两个格子的数字上 (剪了就抖)
    assert '.replace(/\\.0$/, "")' not in loop


def test_trips_page_playback_fixed_width_cells(auth):
    """播放统计格数字定宽: 位数变化 (0.0→12.3 / 0:00→1:02:45 / 回收 -12.3)
    不许在网格里挤动邻居格 —— 数字进 ch 定宽盒, 盒内居中 (用户点名数据居中),
    setLive 每帧重写、setOfficial/fillSheetHeader 定格共三处写法都要带盒
    (漏一处会在开弹层或收尾时跳一次宽度)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        # #sheet 收口: .sh-cell 与充电地图/足迹明细共用, 裸规则被后加载的
        # 同名表盖掉 (字体撞名, 见 test_trips_sheet_dom 同族守卫)
        "#sheet .sh-cell .val .n { display: inline-block; text-align: center; }",
        "#sheet .sh-cell .lb { font-size: 11px; color: var(--ink-2); text-align: center; }",
        "#sh-km .n, #sh-kwh .n { min-width: 4.5ch; }",
        "#sh-dur .n { min-width: 7ch; }",
        "#sh-pw .n { min-width: 5ch; }",          # 可负 (动能回收)
        '#sh-km").innerHTML = \'<span class="n">\' + (cum[idx] + stepKm * frac).toFixed(1)',
        '#sh-dur").innerHTML = \'<span class="n">\' + fmtDurLive(',
        '#sh-spd").innerHTML = \'<span class="n">\' + Math.round(v)',
        '#sh-pw").innerHTML = \'<span class="n">\' + (pw == null',
    ]:
        assert frag in html, f"行程页缺少定宽盒片段 {frag}"
    # 每帧重写的六格无一漏网 (含 kWh/Wh-per-km 模型两格); 统计格写法
    # 全在行程视图脚本里, 按视图口径数
    assert _trips_view_js(auth).count("</span><small>") >= 10, "统计格写法有未进定宽盒的"
