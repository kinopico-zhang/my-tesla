"""行程页播放接线测试: 流式播放 / 速度缩放 / 补路 POST / 播放
节奏 / 定宽单元格。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""

from tests.trips_page_assets import _trips_scripts

def test_trips_page_streams_speed_zoom_and_gap_fill_post(auth):
    """页面片段: 流式边下边播 / 随速变焦 / 断档回传一应俱全。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ["function loadMergedStream(", "sess.append(d.pts, d.ts)",
                 "sess.more = false", "正在下载轨迹", "等待后续轨迹",
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
                 "const zt = speedZoom(TripPlayback.windowMeanSpeed(vt, pts, s.playT, dur));",
                 "Math.min(15.3, 15.3 - v / 46)", "Math.max(12.5,",
                 "(km < 20 ? 14 : km < 80 ? 13 : km < 200 ? 12 : 11)",
                 # 速度色分段线/断档虚线圆头端帽: 换色处两段共享端点, butt 端帽
                 # 在转角各留楔形缺口 (定格后一节节断开), 圆头补上段间无缝
                 'lineJoin: "round", lineCap: "round", zIndex: 50,',
                 # 地图样式走 config (设置页可换), 兜底幻影黑 (配深色 App)
                 "mapStyle: amapStyle",
                 'let amapStyle = "amap://styles/dark"',
                 # 地名首帧竞态: 矢量样式数据异步加载, 首帧不画地名 (同一轨迹
                 # 第二次进入才有地名的原因); 开弹层后延时补重渲染
                 "tripMap.setFeatures(tripMap.getFeatures())",
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
    # 圆头端帽三处: 速度色分段线 + 断档虚线 + 白色进度线 (播放线本就有)
    assert html.count('lineCap: "round"') == 3


def test_trips_page_playback_fixed_width_cells(auth):
    """播放统计格数字定宽: 位数变化 (0.0→12.3 / 0:00→1:02:45 / 回收 -12.3)
    不许在横滑条里挤动邻居格 —— 数字进 ch 定宽盒右对齐, setLive 每帧重写、
    setOfficial/fillSheetHeader 定格共三处写法都要带盒 (漏一处会在开弹层或
    收尾时跳一次宽度)。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in [
        ".sh-cell .val .n { display: inline-block; text-align: right; }",
        "#sh-km .n, #sh-kwh .n { min-width: 4.5ch; }",
        "#sh-dur .n { min-width: 7ch; }",
        "#sh-pw .n { min-width: 5ch; }",          # 可负 (动能回收)
        '#sh-km").innerHTML = \'<span class="n">\' + (cum[idx] + stepKm * frac).toFixed(1)',
        '#sh-dur").innerHTML = \'<span class="n">\' + fmtDurLive(',
        '#sh-spd").innerHTML = \'<span class="n">\' + Math.round(v)',
        '#sh-pw").innerHTML = \'<span class="n">\' + (pw == null',
    ]:
        assert frag in html, f"行程页缺少定宽盒片段 {frag}"
    # 每帧重写的六格无一漏网 (含 kWh/Wh-per-km 模型两格)
    assert html.count("</span><small>") >= 8, "统计格写法有未进定宽盒的"
