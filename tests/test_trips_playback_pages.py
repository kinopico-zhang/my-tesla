"""行程视图播放画法测试: 历史速度色 span / 断档步蓝实线 / 车头连线,
合并播放副标题随段切换并实时跟播。拆自 test_trips.py (结构化重构;
P7 起按 3.0 单壳改口径); 流式加载/节拍/播放条 2026-09-26 拆去
test_trips_playback_stream.py, 播放统计格 (定宽/恒一位/功率口径) 拆去
test_trips_playback_cells.py (这边满 200 行硬上限)。"""

from tests.tesla_static_files import page_asset_paths, served_page


def _trips_view_js(auth):
    """行程视图自有脚本拼起来 (整壳断言分不清视图时用)。"""
    return "".join(auth.get(ref).text for ref in page_asset_paths(auth, "/tesla")
                   if "/js/view/trips-" in ref)


def test_trips_page_playback_history_only(auth):
    """播放画法 (用户点名「未来的轨迹不用显示, 历史的红绿标速度, 不要
    白色」): 未来的整段不上图, 历史速度色 span 走到哪截到哪 (与定格视图
    同一批对象, 收尾铺回全量零跳变); 白色进程线/白描边车头退场; 断档步
    蓝实线跟头生长, 迈过对岸虚线转正; 拖回退/重播全清重走。"""
    html = served_page(auth, "/tesla")
    for frag in [
        "function speedSpans(slice, base)",
        "function buildTrackOverlays(",
        "function histStep(s, idx)", "function histClear(s)",
        "function gapGrow(", "function gapSettle(g)",
        # span = 折线对象 + pts 下标区间; 播放期截短, 收尾铺回全量
        "full, start: at, end: at + run.pts.length - 1, drawn: -1, on: false,",
        "sp.line.setPath(sp.full.slice(0, upto - sp.start + 1));",
        "if (sp.on && sp.drawn < sp.end) sp.line.setPath(sp.full);",
        # 未走到的断档不上图; 迈过对岸才转正。did 随对归档 (合并流断档
        # 带所属段 id); wire 是规划闭包, sess 挂会话 (队列给活会话让路)
        "s.gaps.push(rec);",
        "did: g.did != null ? g.did : it.id, sess: s,",
        "line, solid: null, settled: false, wired: false, wire: null };",
        "if (!g.settled && idx >= g.bIdx) gapSettle(g);",
        "const g = s.gaps.find(x => x.aIdx <= idx && idx < x.bIdx);",
        # 断档登记即入队 (350ms 匀速发, 队列在 trips-gap-routing): 懒规划
        # 的提前量按行驶秒算, 分组把几十小时压进 300s 后只剩几十毫秒墙钟,
        # 规划永远赶不上车头, 分组断档全程直线 (2026-09-22 用户实报撤懒)
        "queueWireGap(rec);   // 登记即入队 (350ms 匀速发, 限流见 trips-gap-routing)",
        "for (const g of s.gaps) if (g.wire && !g.wired) queueWireGap(g);",
        # 弹层关了/换了: 图不动但照样回传归档 —— 关弹层不等上百个断档的
        # 队列滴完, 没归档的下次打开还是直线
        "if (!s.alive) { postGapFill(it, g, route); return; }",
        # 断档蓝实线沿道路生长: 前缀裁剪在 TrackAnimation.routePrefix (纯函数,
        # node 单测直测)。2026-09-22 补定义 —— 3.0 拆 trips.js 时名字进了
        # overlays 的导出清单、函数体没搬, 首播带断档的行程一进断档步当场
        # ReferenceError 掐死帧循环 (2233 实报: 播到六成停住, 补路存档后断档
        # 消失才像"自愈"); 调用点必须走它, 不许回悬空裸名
        # 调用点必须走它, 不许回悬空裸名; 弧长进度先过 accelArc (匀加速)
        "TrackAnimation.routePrefix(sp, arc, pos)",
        # 历史线时间节流 ~8fps (断档蓝实线同款): 白线时代按点数攒块的步长在
        # 合并轨迹里随总点数涨到几百, 线尾追不上车头、回拨/重播后空窗几百点
        # (2026-09-22 用户实报); 每次只 setPath 车头所在的分色短段, 不必攒块;
        # 落后 25 点以上强制起拍 —— 连线只是两点弦, 高速下落后太多会拉成
        # 穿街长直线。hist.color 是线尾当前色 (车头连线跟它取色)
        "hist: { spans, done: 0, drawAt: 0,",
        "if (idx !== s.N - 1 && idx - h.done < 25 && Date.now() - h.drawAt < 120) return;",
        "h.drawAt = 0;",
        # 车头连线 (用户设计): 线尾 (最后画到的点) → 车头插值位, 每帧两点
        # setPath; 断档步内尾端收到岸边 (蓝实线沿道路长, 不叠弦线); 颜色
        # 跟轨迹最后一段同色
        "const tail = mapLib.polyline({",
        "tail.setPath([path[s.hist.done], gIn ? path[idx] : pos]);",
        "tail.setOptions({ strokeColor: tailColor });",
        "tripMap.remove(tail);",
        # 收尾: 撤播放态 + 全集上图 + 拉远; 重播: 全集撤下 (未来重新藏起)
        "tripMap.add(allLines);", "tripMap.remove(allLines);",
        # 播放期加粗一号 (用户点名「动态的轨迹线条粗一点, 明显一点」): 速度色
        # span + 断档步蓝实线都钉 6 (不钉的话引擎默认只 2); 收尾定格收回
        # 4 (打开弹层的默认观感), 重播再加粗
        "strokeWeight: 6,",
        "sp.line.setOptions({ strokeWeight: 4 });",
        "for (const sp of s.hist.spans) sp.line.setOptions({ strokeWeight: 6 });",
        # 划过的线不透明 (用户点名「不要半透明效果」): 不钉的话高德默认
        # strokeOpacity 0.9, 地图道路/地名从线底下透出来
        "strokeOpacity: 1,",
        # 车头描边不用白 (深色光晕), 进度圆钮同蓝 (css 侧)
        'strokeColor: "rgba(10,10,12,.55)", strokeWeight: 2.5,',
    ]:
        assert frag in html, f"播放画法缺少 {frag}"
    # 白色退场: 进程线/车头白描边不许回潮 (行程视图脚本里)
    vjs = _trips_view_js(auth)
    assert "#f5f5f7" not in vjs, "白色进程线回潮了"
    assert 'strokeColor: "#fff"' not in vjs, "车头白描边回潮了"
    assert "splicePath" not in vjs, "白线时代的 splicePath 接线回潮了"
    assert "routePrefix({ splices" not in vjs, "悬空裸名 routePrefix 回潮了"
    # 定义真身与版本号: routePrefix 落在纯模块 (UMD), overlays 换调用点一起 bump
    anim_js = auth.get("/tesla/static/js/track-animation.js").text
    assert "function routePrefix(sp, frac, head)" in anim_js
    assert "routePrefix: routePrefix" in anim_js
    assert "js/track-animation.js?v=3" in html
    assert "view/trips-playback-overlays.js?v=8" in html
    assert "view/trips-playback-session.js?v=14" in html   # defer 起播: 数据会话先挂, begin 才进播放态
    # 断档步匀加速 (用户点名: 初速度终止速度都知道, 就匀加速播放过去):
    # 弧长进度不随时间线性 —— x/s = τ(2v0+τ(v1-v0))/(v0+v1) (纯函数, node
    # 直测); headPos 有路/弦线两处 + gapGrow 前缀一处共三处同口径
    assert "function accelArc(tau, v0, v1)" in anim_js
    assert "accelArc: accelArc" in anim_js
    assert vjs.count("TrackAnimation.accelArc(frac, v0, v1)") == 3
    # 按点数攒块的旧节流不许回潮 (合并轨迹步长随总点数涨, 线追不上车头);
    # hist.step 旧名只钉播放两脚本 —— 统计页 (trips-sheet-stats) 自己的
    # hist.step 是直方图档宽 km/h (2026-09-23 均匀分档引进), 同名不同物,
    # 全拼串禁词会误伤
    assert "growStep" not in vjs, "按点数攒块回潮了"
    for name in ("js/view/trips-playback-loop.js",
                 "js/view/trips-playback-overlays.js"):
        assert "hist.step" not in auth.get(f"/tesla/static/{name}").text, \
            f"{name} 按点数攒块回潮了"
    # 加粗四处: 速度色 span + 断档步蓝实线 + 车头连线 (创建时) + 重播恢复;
    # 4.5 旧值退场
    assert vjs.count("strokeWeight: 6") == 4, "播放加粗钉丢了"
    assert "strokeWeight: 4.5" not in vjs, "断档步旧线宽回潮了"
    # 不透明四处: 速度色 span + 断档步蓝实线 + 断档虚线 + 车头连线
    assert vjs.count("strokeOpacity: 1") == 4, "轨迹线不透明钉丢了"
    # 进度条圆钮: 蓝色无黑影 (css 在整壳页里)
    assert "box-shadow: 0 1px 4px rgba(0,0,0,.55)" not in html, "圆钮黑影回潮了"
    assert html.count("border-radius: 50%;\n  background: var(--blue); margin-top: -5.5px;") == 1


def test_trips_page_merged_seg_title_dynamic(auth):
    """合并播放副标题随段切换并实时跟播 (2026-09-25 用户点名「随着播放动态
    的变化, 显示第 x 段行程, 年月日」+「拖动滚动条, 标题也要跟着变」+「星期
    改成具体的小时和分钟」+「时间要实时变, 跟着轨迹的运动」): 分组名/日期
    区间当主标题不动, 副标题播放中显「第 x/N 段行程 · 该段年月日+几点几分」,
    时刻每帧跟播放头走 —— 段内墙钟 = 段首 t0 + 段首起行驶秒 (ts 段内是原始
    时间戳差, 停驶剔除只发生在段间; 服务端侧 test_trips_merged_ranges 直
    测); 段界在播放会话里判 (apply, 播放/拖进度/重播统一过它), 写前与 DOM
    现值比对, 分钟/段序没滚不重排; 收尾定格换回静态整组口径, 重播从头再
    亮段序; ts 是累计行驶秒推不出墙钟, 各段时刻服务端随载荷发 (t0/seg_t0s,
    服务端侧 test_trips_tracks / test_trips_merged_ranges 直测)。"""
    html = served_page(auth, "/tesla")
    drv = auth.get("/tesla/static/js/view/trips-sheet-driver.js").text
    sess = auth.get("/tesla/static/js/view/trips-playback-session.js").text
    loop = auth.get("/tesla/static/js/view/trips-playback-loop.js").text
    opn = auth.get("/tesla/static/js/view/trips-sheet-open.js").text
    # 静态口径收进 mergedSub (打开时与收尾定格同一份), fillSheetHeader 两个
    # 合并分支都走它
    assert 'function mergedSub(it) {' in drv
    assert drv.count('$("#sh-time").textContent = mergedSub(it);') == 2
    # 动态口径: 第 x/N 段 + 当前点日期+时刻 —— 段首时刻平移段内行驶秒
    # (shiftStamp), t0 缺席 (旧载荷/老缓存) 回退整组 start
    assert 'function setSegTitle(it, k, t0, elapsed) {' in drv
    assert 'fmtFullStamp(shiftStamp(t0 || it.start, elapsed))' in drv
    assert '`第 ${k + 1}/${it.n} 段行程`' in drv
    assert 'if (el.textContent !== txt) el.textContent = txt;' in drv   # 同串不重排
    # 会话侧段界: 整包缓存随 it 到齐, 流式首段 [0] 起步 append 逐段登记;
    # 单条行程不启用 (null)
    assert "const segStarts = it.merged && Array.isArray(it.seg_starts)" in sess
    assert "? it.seg_starts.slice() : (it.merged ? [0] : null);" in sess
    assert "Array.isArray(it.seg_t0s) && it.seg_t0s.length" in sess
    assert ": [it.start])" in sess
    # 每帧跟播 (不在 idxNew 里, 段内时刻才滚得起来): 段界升序顺扫取段序,
    # 步内按 frac 插值同 setLive 口径, elapsed = 段首起行驶秒
    assert "if (segStarts && ts[idx] != null) {" in sess
    assert "for (let j = 1; j < segStarts.length; j++) if (idx >= segStarts[j]) k = j;" in sess
    assert "setSegTitle(it, k, segT0s[k] || it.start," in sess
    assert "ts[idx] + (tb - ts[idx]) * frac - ts[st]" in sess
    assert "segShown" not in sess   # 段序状态已撤: 去重改与 DOM 现值比对 (driver)
    # 流式追加: 段界与段首时刻一起登记 (append 先于播放头到, 未来段的界常驻)
    assert "append(segPts, segTs, gapPairs, t0) {" in sess
    assert "if (segStarts) { segStarts.push(startIdx); segT0s.push(t0); }" in sess
    # 收尾定格换回静态整组口径 (停在「第 N 段」半路收场观感突兀); 收尾后
    # 副标题被 mergedSub 改写, 重播首帧必不同串 → 无需复位状态
    assert 'if (it.merged) $("#sh-time").textContent = mergedSub(it);' in loop
    # 流式装载: 首段时刻开播前挂 it, 逐段收集进缓存 (重开整包播放同一套)
    assert "it.seg_t0s = [d.t0];" in opn
    assert "segT0s.push(d.t0);" in opn
    assert "seg_t0s: segT0s, gaps: allGaps });" in opn
    # 版本号 (改过的都带上, 老缓存不掺和; driver 2026-09-25 加功耗格常显;
    # session/loop 2026-09-25 流式节拍开播定死 —— 时间流逝不随加载变速;
    # sheet-open/preload-vector 2026-09-25 走廊去重 + common 交还缓存策略
    assert "view/trips-sheet-driver.js?v=13" in html
    assert "view/trips-playback-session.js?v=14" in html
    assert "view/trips-playback-loop.js?v=12" in html
    assert "view/trips-sheet-open.js?v=10" in html
