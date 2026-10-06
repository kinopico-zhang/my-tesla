"""行程视图流式播放测试: 边下边播 / 随速变焦 / 补路 POST / 流式节拍开播
定死 / 弹层一开播放条先亮。2026-09-26 拆自 test_trips_playback_pages.py
(那边满 200 行硬上限)。"""

from tests.tesla_static_files import page_asset_paths, served_page


def _trips_view_js(auth):
    """行程视图自有脚本拼起来 (整壳断言分不清视图时用)。"""
    return "".join(auth.get(ref).text for ref in page_asset_paths(auth, "/tesla")
                   if "/js/view/trips-" in ref)


def test_trips_page_streams_speed_zoom_and_gap_fill_post(auth):
    """视图片段: 流式边下边播 / 随速变焦 / 断档回传一应俱全。"""
    html = served_page(auth, "/tesla")
    for frag in ["function loadMergedStream(", "sess.append(d.pts, d.ts, d.gaps, d.t0)",
                 "sess.more = false", "正在下载轨迹", "等待后续轨迹",
                 # 服务端断档对穿线: 首段给 it (偏移 0), 后续段随 append,
                 # 整包缓存存全量下标 (gapPairs 下标口径见 trip-playback 单测)
                 "it.gaps = d.gaps;",
                 "allGaps.push(...(d.gaps || []));",
                 "gaps: allGaps });",
                 # 电耗两格随整包缓存走 (2026-09-22 用户实报: 重开缓存命中,
                 # it.kwh 没进缓存 → setLive/setOfficial 双双跳过, 格子卡 —)
                 "kwh: it.kwh, wh_per_km: it.wh_per_km,",
                 # 流式播放电耗定标 (2026-09-23 用户实报十一云南游首段五位数
                 # Wh/km): 分母 ecum[N-1] 只盖已载段而 it.kwh 是全组总电耗,
                 # 追加期按已载里程占官方总里程折算, 全载完 (more=false)
                 # 或整包缓存比例恒 1 收尾落回整体值
                 "setLive({ pts, ts, cum, ecum, it, N, more: s.more }, idx, frac);",
                 "const scale = more && it.km > cum[N - 1] ? cum[N - 1] / it.km : 1;",
                 "it.kwh * scale * eNow / ecum[N - 1];",
                 # 首段开播前也扫路预取 (矢量), 后续段靠环形前瞻容器边播边覆盖
                 "await preloadVectorTrack(d.pts, d.ts, followZoom(it.km || 0),",
                 "const speedZoom =", "followZoomOn", "zoomEaseStart(zoom)",
                 "tripMap.setZoom(zoomShown, true)",
                 'addEventListener("wheel", zoomTakeover,',
                 # 手动视角锁定跨行程保持: 接管即锁定 (zoomUserLock), 换行程/
                 # 重播保持用户档位只跟位置不再自动变焦; 播放条 +/- 基线按钮
                 # 恢复自动 (锁定解除)
                 "let zoomUserLock = false, zoomUserZoom = 0;",
                 "zoomUserLock = true;                 // 手动接管 = 视角锁定, 换行程也保持",
                 'tripMap.on("zoomend", () => {',
                 "if (zoomUserLock && anim && !anim.finished)"
                 " zoomUserZoom = tripMap.getZoom();",
                 "if (zoomUserLock) {\n    const z = "
                 "Math.round(zoomUserZoom || tripMap.getZoom());",
                 "zoomUserLock = false;                    // 手动锁定解除, 恢复随速变焦",
                 # 堵车平滑 + 提前量: 滑窗开在播放时间轴上 (过去 2s + 预看 5s,
                 # 均匀 8 采样插值车速取均值) —— 领先当前车速 ~1.5s, 减速刚起势
                 # 就开始拉近 (不等停稳才动); 窗口随播放位置现算无状态, 开播/
                 # 拖进度天然干净; 曲线基线 12.5~15.3 (原 13.5~16.3 过近, 拉远一档)
                 "ZOOM_PAST_MS = 2000", "ZOOM_FUT_MS = 5000",
                 "TrackAnimation.animAt(vt, tw, dur)",
                 "const zt = speedZoom(TripPlayback.windowMeanSpeed(vt, pts, s.playT, mapDur));",
                 "Math.min(15.3, 15.3 - v / 46)", "Math.max(12.5,",
                 "(km < 20 ? 14 : km < 80 ? 13 : km < 200 ? 12 : 11)",
                 # 速度色分段线/断档虚线圆头端帽: 换色处两段共享端点, butt 端帽
                 # 在转角各留楔形缺口 (定格后一节节断开), 圆头补上段间无缝
                 'lineJoin: "round", lineCap: "round", zIndex: 50,',
                 # 地图引擎经适配层 (高德单服务商), 样式固定幻影黑 (2026-10-05
                 # 样式选择退役, 常量住适配层, 不再从配置端点拿)
                 'mapLib.createMap("trip-map"',
                 'const styleV = "amap://styles/dark";',
                 # 地名首帧竞态: 矢量样式数据异步加载, 首帧不画地名 (同一轨迹
                 # 第二次进入才有地名的原因); 开弹层后延时补重渲染
                 # (getFeatures 是高德方言 → 有这方法才补画)
                 "if (tripMap && tripMap.getFeatures) tripMap.setFeatures(tripMap.getFeatures());",
                 "setTimeout(nudgeLabels, 1500)",
                 # 播放动画期间禁止熄屏: 双保险 —— Wake Lock (standalone iOS
                 # 申请成功也可能不生效) + 1px 循环静音视频 (NoSleep.js 同款,
                 # 正在播放的媒体 iOS 一定不熄屏); 必须静音 —— 不静音就抢
                 # 音频会话, 掐断别的 app 的声音; 暂停/播完/关弹层释放,
                 # 切后台自动释放回前台重启用
                 'if (!("wakeLock" in navigator)) return;',
                 "holdScreenAwake()", "releaseScreenAwake()",
                 'v.setAttribute("playsinline", "")', "v.muted = true",
                 "awakeVideo.play()",
                 "AWAKE_VIDEO_WEBM", '["video/webm", AWAKE_VIDEO_WEBM]',

                 "postGapFill(it, g, route)", "gcj02ToWgs84"]:
        assert frag in html, f"行程页缺少片段 {frag}"
    # 滑窗已无状态化: 旧 zoomWin 残留任何一处引用都会让整页 JS 抛
    # ReferenceError (严格模式), 播放直接挂
    assert "zoomWin" not in html and "ZOOM_WIN" not in html
    # 圆头端帽四处 (都在行程视图): 速度色分段线 + 断档虚线 + 断档步蓝实线
    # + 车头连线; 驾驶视图也用圆头线 (live-driving), 整壳口径数不清,
    # 按视图脚本数
    assert _trips_view_js(auth).count('lineCap: "round"') == 4


def test_trips_page_stream_pace_pinned_at_open(auth):
    """流式播放节拍开播定死 (2026-09-25 用户点名「随着行程分组轨迹的动态
    加载, 时间的流逝是逐渐变快的, 播放过程中流逝速度要一样」): 原先 append
    每次按已载入的 N/km 重算 dur、再按 vt 比例重锚 playT, 播放头推进速率 =
    已载行驶秒/dur 随追加一路漂移 (首段短被 3s 底数拖慢, 211km 后 300s 封顶
    又随加载线性加快) —— 分组边下边播时时间越走越快。现在开播一次定死:
    dur 冻结在全程里程档 (汇总头 it.km 先于首段到达), pace = 全程行驶秒
    (it.min, Σ 行程时长, ts 同口径)/全程播放时长; 播放头位置是绝对行驶秒,
    animAt 经 mapDur (= 已载行驶秒/pace, append 只延长它) 映射下标 ——
    追加只在未来侧延长 vt, 头原地不动, 速率从头到尾一个值。"""
    html = served_page(auth, "/tesla")
    sess = auth.get("/tesla/static/js/view/trips-playback-session.js").text
    loop = auth.get("/tesla/static/js/view/trips-playback-loop.js").text
    # 开播锚: 全程量一次定死 (dur 冻结、pace 恒定; 汇总缺时长按里程比推)
    assert "const kmFull = it.km > cum[N - 1] ? it.km : cum[N - 1];" in sess
    assert "dur = TripPlayback.animDurMs(N, kmFull);" in sess
    assert "const vtFull = it.min > 0 ? it.min * 60" in sess
    assert "pace = vtFull / dur;" in sess
    # append 不重算 dur、不重锚 playT —— 只延长映射上限 (头原地、速率不变)
    assert "mapDur = pace > 0 && vt[N - 1] > 0 ? vt[N - 1] / pace : mapDur;" in sess
    assert "dur * vt[s.lastIdx] / vt[N - 1]" not in sess, \
        "按已载比例重锚回潮 (dur 随已载量变, 速率会漂移)"
    assert sess.count("TripPlayback.animDurMs(") == 2, \
        "开播档 + 全程档共两处, append 里按已载量重算那次应已退役"
    # 帧循环: 流式顶在已载末尾等追加; 流收尾把 dur 校准到真实末点 (pace 不动)
    assert "if (!s.more && s.mapDur !== s.dur) s.dur = s.mapDur;" in loop
    assert "const cap = s.more ? Math.min(s.dur, s.mapDur) : s.dur;" in loop
    assert "Math.min(s.playT + dt * s.speed, cap)" in loop
    assert "TrackAnimation.animAt(s.vt, s.playT, s.mapDur)" in loop
    # 拖进度拖不进没下的段 (顶到已载末尾); 拖回已载区间撤「等待后续轨迹」
    assert "if (s.more && s.playT > mapDur) s.playT = mapDur;" in sess
    assert "if (s.waiting && s.playT < cap) {" in loop
    assert "view/trips-playback-session.js?v=14" in html
    assert "view/trips-playback-loop.js?v=12" in html


def test_trips_page_playbar_shown_while_map_loads(auth):
    """打开弹层控制条先亮 (用户点名: 加载地图时底下按钮别跟着等): 播放条
    原本要等预载完成 startSession 才露面, 矢量扫路/瓦片预载最长好几秒;
    现在弹层一开就摆待播态 (会话没起来前按钮监听本就 if (!anim) return
    空转), 视角基线仍随起播亮 —— 加载期地图还没影子, 提前按了反而误清
    手动档位锁 (bumpZoomBias 会把 zoomUserLock 掰回自动)。2026-09-27 三页
    独立: playTrack(defer) 只备数据与图层 (数据会话 curSess 即刻可读, 另
    两页照画), 帧循环/视角 sess.begin() 预载收尾才起 —— stopAnim 顺手收
    掉的播放条预载期照旧亮着。"""
    open_js = auth.get("/tesla/static/js/view/trips-sheet-open.js").text
    loop_js = auth.get("/tesla/static/js/view/trips-playback-loop.js").text
    # 亮条卡在加载提示与建图之间 (弹层一开就有, 不等预载)
    i = open_js.index('tripMsg("正在加载轨迹…", true);')
    j = open_js.index("playbarPending();")
    assert i < j < open_js.index("await ensureAMap()"), "控制条没在加载期亮出来"
    # 待播态 (进度归零 + 暂停钮) 从 resetPlaybar 拆出共用: 起播/重播/加载期
    # 同一套复位, 上一条的残留 (重播钮/拖过的进度) 不闪旧画面
    assert "function playbarPending()" in loop_js
    assert "function resetPlaybar() {\n  playbarPending();" in loop_js
    # 关弹层/换行程仍走 stopAnim 收条 (hideSheet 全路径经此)
    assert '$("#playbar").hidden = true;' in _trips_view_js(auth)
    # 三页独立 (2026-09-27 用户点名「三个页面不需要联动」): playTrack 先于
    # 地图预载 (defer) —— 数据会话即刻可读, 预载完 sess.begin() 才进播放
    # 态; 单条/流式首段两条路径同款
    assert 'const sess = playTrack(c.pts, c.ts || [], it, zoom, false, true);' in open_js
    assert open_js.index("playTrack(c.pts") < open_js.index("await tileTemplate()"), \
        "会话要先于预载起 (另两页读 curSess, 预载不拖着它们)"
    assert open_js.count("sess.begin();") == 2, "单条 + 流式首段, 两条路径都要点火"
    assert 'sess = playTrack(d.pts, d.ts, it, followZoom(it.km || 0), true, true);' in open_js
