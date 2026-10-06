"""动态页接线测试: 头部/数字带横滑转发切页 (页签撤了), 底行页标区点击
循环切页, rAF 弹层开着就跑 (三页数据各画各的); 退役禁词 (客户端 speedHist
分桶 / avgAxis / 动画时代截画 / 页签 / 整带收放) 与藏带/版本钉。2026-09-26
拆自 test_trips_stats_page.py (那边满 200 行硬上限)。"""
from tests.tesla_static_files import served_page


def test_stats_module_wiring(auth):
    """接线: 头部/数字带横滑转发切页 (页签撤了), 底行页标区可点 —— 点一
    下切下一页, 末页绕回第一页循环 (2026-09-24 用户点名; 2026-09-22 起
    该行为挂在右上角页标题上, 同日让位给驾驶员); 关弹层复位
    回地图页, rAF 弹层开着就跑 (2026-09-27 三页独立: 三页数据各画各的,
    不看人在哪页; 关了自停, 静态图平时零重绘, 只盯换会话/流式追加重建)。
    动态 = 一开就画全程 (2026-09-23 用户点名撤动画: 不跟播放头截画, 播放
    侧只在会话对象上多挂一行数据)。"""
    html = served_page(auth, "/tesla")
    js = auth.get("/tesla/static/js/view/trips-sheet-stats.js").text
    sess = auth.get("/tesla/static/js/view/trips-playback-session.js").text
    assert "pts, ts, it, cum, ecum, N, dur, vt," in sess, "会话没挂 ts/it/cum/ecum"
    for frag in [
        # 转发保底 scrollTo 强制切页 (手势没被原生认出来的那次); 三页通用
        # (2026-09-23 加统计页): 左滑下一页/右滑上一页, 到头不滚
        'pager.scrollTo({ left: Math.min(N_PAGES - 1, Math.max(0, page + (dx < 0 ? 1 : -1)))',
        # 弹层底一行 (2026-09-23 用户点名: 页标题 + iOS 桌面同款白点页标)
        # 切页换字 + 亮当前页的点; 页位唯一回显 (右上角页标题 2026-09-24
        # 退役让位给驾驶员)
        'const FOOT_LB = ["行驶轨迹", "行驶数据", "行驶统计"];',
        'footLb.textContent = FOOT_LB[page] || FOOT_LB[0];',
        'footDots.forEach((el, k) => el.classList.toggle("on", k === page));',
        # 点底行页标区 (圆点+标题整块) 循环切页: 下一页, 末页绕回第一页
        # (2026-09-24 用户点名; 2026-09-22 点名的是右上角页标题, 该位
        # 同日让给驾驶员)
        'const foot = doc.getElementById("tp-foot");',
        'foot.addEventListener("click"',
        'const next = (page + 1) % N_PAGES;',
        'pager.scrollTo({ left: next * pager.clientWidth, behavior: "smooth" });',
        # 横滑转发: 头部 (一直没主) + 数字带/播放条 (2026-09-25 挪出分页到
        # 公共带, 原生滚页没了, 转发是主路 —— 更早裹在分页里时它就是 iOS
        # snap 橡皮筋/斜起手死手势的保底, 2026-09-22 用户实报「有时候左滑
        # 滑不动」); 进度条起手不算 (拖进度横移是常态, closest 排除)
        'for (const sel of ["#sheet .sh-head", "#sheet .sh-cells", "#sheet .playbar"])',
        '!e.target.closest(".pb-seek")',
        "Math.abs(dx) < 56",                          # 转发门槛: 够横才切
        # 图表页 (动态/统计) 转发保底 (2026-09-27 用户实报「左滑不动, 要滑
        # 好几遍才行」→ 修后又报「还是不灵敏, 卡卡的」): 主路是原生滚页
        # (两页手势已收纯横轴), 转发只兜纹丝未动的死手势; 起手页快照定目标
        # (原生已切走时用 page 会连跳两页), touchcancel 也算 (iOS 认领原生
        # 滚动后发 cancel 不发 end); 原生已滚就不掺和 (≥4px —— 动量/snap
        # 自己收尾, 补一刀 smooth scrollTo 会二次起步打架)
        'for (const sel of ["#sheet .tp-stats", "#sheet .tp-hist"])',
        'Math.max(0, startPage + (dx < 0 ? 1 : -1))',
        'Math.abs(pager.scrollLeft - startPage * pager.clientWidth) > 4',
        'zone.addEventListener("touchcancel", fwd, { passive: true });',
        'if (!sheet.classList.contains("show"))',     # 弹层关了 rAF 就停
        # 静态全量 (2026-09-23 用户点名「不需要动画, 直接展示全貌」): rAF
        # 只盯换会话/流式追加 (N 变了) 重建一遍, 不逐帧追播放头
        "(s !== builtFor || (s.N || s.pts.length) !== builtN)",
        # rAF 弹层开着就跑 (2026-09-27 三页独立): 开弹层 MutationObserver
        # 起, 三页数据各画各的不看人在哪页 (会话/直方图先于用户滑过去就
        # 已画好); 关弹层顺手复位回轨迹页 (下一次打开从轨迹页起)
        'if (sheet.classList.contains("show")) startRaf();',
        'else if (page !== 0) pager.scrollLeft = 0;',
        # 翻页静默窗 (同日用户报「卡卡的」主线程元凶: 飞行途中全量重画):
        # scroll 每帧续期, 滚停 200ms 后重活恢复
        'quietUntil = Date.now() + 200;',
        'const busy = Date.now() < quietUntil;',
        # 两页空态各跟各的数据 (三页独立): 动态页等数据会话 (curSess ——
        # openTrip 里 playTrack(defer) 先于地图预载, 预载没完早已就绪),
        # 统计页等服务端直方图 (curIt.hist, 开弹层即取, 与轨迹/地图无关)
        "EMPTY.hidden = !!s;",
        'EMPTYH.hidden = !!(curIt && curIt.hist !== undefined);',
        # 统计页独立成画: 直方图到货即画 (会话没起也画 —— 柱状图不等地
        # 图); 会话先起 (build 画过) 也走这补第三卡, 不等下一轮重建
        'if (!busy && curIt && curIt.hist != null && hist !== curIt.hist) {',
        'hist = curIt.hist;',
        'doc.getElementById("tps-card-hist2").hidden =',
    ]:
        assert frag in js, f"动态页模块缺 {frag}"
    # trackutil 真导出 SPEED_STOPS (2026-09-23 事故根因: 漏导出 → speedBucket
    # 拿 undefined, build 一抛带死 rAF 循环, 两页图全空; node 侧另钉真值)
    tu = auth.get("/tesla/static/js/trackutil.js").text
    assert "SPEED_STOPS: SPEED_STOPS," in tu
    # 页签接线整块撤掉 (markup 撤了, JS 的 tabs 引用也一根不留)
    assert "tp-tabs" not in js and "syncTabs" not in js
    # 平均电耗曲线已撤 (2026-09-22 用户点名换成功率口径, 功率本就是主轴)
    assert "avgAxis" not in js and "yOf3" not in js and "#b48cf2" not in js
    # 速度/电耗卡副行撤了 (最高·平均/总·平均): 平均车速纯函数与副行写法
    # 一并退场 (vAvgKmh 只服务过它)
    assert "vAvgKmh" not in js and '"最高 "' not in js and '"总 "' not in js
    # 动画时代退役 (2026-09-23 用户点名「不需要动画」): 播放头横轴插值 /
    # 截画 / 副行前缀函数一根不留, renderLive 换 renderAll
    assert "cursorT" not in js and "tCut" not in js and "prefixMax" not in js \
        and "prefixClimb" not in js and "renderLive" not in js \
        and 'tag: "功率"' not in js and "p[3] / p[2]" not in js \
        # 右轴口径已换 kWh/100km; 功率÷车速的瞬时口径 (停车不耗电) 不回潮
    assert "function renderAll()" in js
    # speedHist 客户端分桶退役 (2026-09-24 对账官方口径): 纯函数/模型定标
    # 定标门槛/旧 floor 档沿一根不留 —— 三卡数据全走服务端 /hist 接口
    # (tests/test_trip_hist.py 直测), 模型只剩 kwhAt 定标播放格; 旧 floor
    # 档沿标签的禁词 k*step+"-" 与新整除区间标签 (80-89) 前缀同形
    # (2026-09-24 二次对账撞过车), 新标签整行已正面钉在上面的 frag 里
    assert "speedHist" not in js and "const canE" not in js \
        and "hb.e[k] / dk" not in js
    # 三页独立 (2026-09-27 用户点名「三个页面不需要联动…地图大小不要变来
    # 变去, 柱状图大小也不要变来变去」): 数字带/播放条住回轨迹页, 翻页不
    # 收不还 —— 整带收放/落定防抖/翻面重画整套退役, JS 与 CSS 一根不留
    assert "no-band" not in js and "settleBand" not in js \
        and "syncBand" not in js and "bandHid" not in js and "settleT" not in js
    assert "if (builtFor) renderAll();" not in js
    # 在途空框那套退役 (在途位/请求令牌/直方图读取中画字): 空态盖整页,
    # 撤掉与三卡首亮同一拍 —— 空态文案钉在 test_trips_stats_page
    assert "histPending" not in js and "histReq" not in js \
        and "drawHistPending" not in js and "直方图读取中" not in js
    # build 读数据会话 (curSess) 不是播放会话 (anim): openTrip 里
    # playTrack(defer) 先于地图预载, 预载没完 curSess 早已就绪 —— 动态页
    # 不等地图就能定轴成画 (anim 要到 sess.begin() 才非空)
    assert "const s = curSess;" in js and "const s = anim;" not in js
    # 电耗卡亮卡只看真有数据 (在途亮空框撤了, 同空态一拍)
    assert "!(hist && hist.pk && hist.pk.some(v => v != null));" in js
    # 统计页数据入口: openTrip 开弹层即调 (直方图服务端只要行程身份, 与
    # 轨迹下载/地图预载全程无关); 状态全落在 it 上 (it.hist/it.histTried,
    # 列表对象复用 = 天然缓存), 快速连开两个行程互不干扰; 失败 null 落定
    # 不留永久「读取中」
    assert "root.tripHistKick = it => {" in js
    assert "curIt = it;" in js
    assert "if (it.hist === undefined) fetchTrackHist(it);" in js
    assert ".then(d => { it.hist = d; })" in js
    assert ".catch(() => { it.hist = null; });" in js
    open_js = auth.get("/tesla/static/js/view/trips-sheet-open.js").text
    assert "tripHistKick(it);" in open_js
    assert open_js.index("tripHistKick(it);") \
        < open_js.index('$("#sheet").classList.add("show")'), \
        "直方图开弹层就发起, 不排在轨迹下载后面"
    # 播放编排放行 (三页独立主路): playTrack(defer) 先于地图预载 —— 数据
    # 会话即刻可读 (另两页照画), 帧循环/视角/断档登记 sess.begin() 预载
    # 收尾才起; 停止动画顺手收掉的播放条预载期照旧亮着
    assert 'const sess = playTrack(c.pts, c.ts || [], it, zoom, false, true);' in open_js
    assert "sess.begin();" in open_js
    assert "begun: false," in sess and "s.begin = () => {" in sess
    assert "curSess = s;" in sess
    sheet_css = auth.get("/tesla/static/css/tesla-trips-sheet.css").text
    assert "no-band" not in sheet_css
    # 版本号 (改过的都带上, 老缓存不掺和; 2026-09-27 三页独立批)
    assert "view/trips-sheet-stats.js?v=41" in html    # v41: 三页独立 (curSess 直读/直方图开弹层即取/静默窗/整带收放退役)
    assert "js/trackutil.js?v=5" in html   # v5: 原始轨迹层退役 (扁平版函数)
    assert "view/trips-playback-session.js?v=14" in html    # defer 起播: 数据会话先挂, begin 才进播放态
    assert "view/trips-sheet-close.js?v=12" in html    # 统计页 tp-hist 入下拉关闭区
    assert "view/trips-sheet-open.js?v=10" in html    # 编排重排: 直方图开弹层即取, playTrack(defer) 先于预载
    assert "css/tesla-trips-sheet.css?v=31" in html    # 整带收放规则撤掉 (布局恒定)
    assert "css/tesla-trips-playback.css?v=9" in html
