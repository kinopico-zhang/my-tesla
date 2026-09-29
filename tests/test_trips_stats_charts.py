"""动态页三图画法测试: 速度/电耗双轴曲线 (百公里电耗滑窗真实积分), 海拔
缺采样前向补值不断线, 统计页直方图三卡 (服务端 /hist 口径) 与点图查值
三图联动; 轴名/刻度文字复原钉。2026-09-26 拆自 test_trips_stats_page.py
(那边满 200 行硬上限)。"""


def test_stats_charts_wiring(auth):
    """三图与直方图的画法断言 (拆自 test_stats_module_wiring 的 frag 清单
    后半 + 轴文字复原钉, 口径一字未动)。"""
    js = auth.get("/tesla/static/js/view/trips-sheet-stats.js").text
    for frag in [
        "TrackUtil.SPEED_COLORS[",                    # 速度图与轨迹线同款配色
        "ys: ecum.map(v => pure.kwhAt(v, eTotal, it.kwh)),",  # 累计定标到整趟
        "const stride = Math.max(1, Math.ceil(N / 1400));",   # 抽稀, 尾点必在
        "new Path2D()",                               # 按色分组一次描完
        # 双轴 (2026-09-22 用户点名「速度曲线加一个里程」+「电耗的曲线要
        # 加一个功率的曲线, 功率曲线坐标轴在右边」; 2026-09-23 三轮点名:
        # 「功率改成 kWh/km」→「停车也需要耗电, 算真实的」+「用 1km 滑窗,
        # 不到 1km 的行程用更小的」→「换成 kWh/100km」+「起步段动态窗」):
        # 速度图右轴蓝线 = 里程累计 (定格整趟 km); 电耗图主轴 = 总电耗累计
        # kWh (蓝线带面积, 原来的电耗曲线), 右轴橙线 = 百公里电耗
        # kWh/100km —— 能耗 = 功率×时间的真实积分 (停车时功率就是空调/
        # 电子件负载, 照积: 车不挪分子涨、分母冻住, 红灯处缓缓上抬), 总
        # 账定标到官方总电耗 (续航差×效率系数的电池口径); 滑窗按里程
        # (1km, 行程不足 1km 缩到 1/3), 双指针取最小满窗; 起步段没走满窗
        # 不铺平线 —— 从起步攒到当前的动态窗 (走过 50m 起, 不足 50m 才回
        # 铺首个有效值, 只剩一小截), 交汇处与满窗值无缝衔接; 轴定到全程
        # min..max (95 分位定轴把尖峰削了顶, 用户实报曲线显示不全, 改回
        # 全量盖住); 副轴与主轴同一像素区间的仿射映射, 副轴线细一号;
        # 没功耗数据的行程电耗卡退回单累计线
        "y2: kmTotal > 0 ? {",                        # 速度图右轴 = 里程
        "ys: cum, hi: pure.niceCeil(kmTotal), color: \"#3987e5\",",
        "const E = [0];",                    # 真实能耗积分 (kW·s→kWh, ts 相对秒)
        "E.push(E[i - 1] + pw * (ts[i] - ts[i - 1]) / 3600);",  # 段能耗=两端均值×时长秒
        # ts 单位修正 (2026-09-23 用户报「时间分布柱子都太短」牵出): ts 是
        # 相对秒, 当毫秒用少一千倍 —— 时间柱除 60000 全贴地; 旧客户端分桶
        # 随 2026-09-24 官方口径对账退役 (三卡分钟数改服务端算, 该坑不回潮)
        "const W = Math.min(1, Math.max((it.km || 0) / 3, .05));",  # 1km 滑窗, 短行程缩窗
        "while (j + 1 < i && cum[i] - cum[j + 1] >= W - 1e-9) j++;",  # 双指针最小满窗
        "pk[i] = (E[i] - E[j]) / d * 100 * it.kwh / E[N - 1];",  # 满窗: 能耗差÷里程差×100
        "else if (cum[i] >= .05)",           # 起步动态窗门槛: 走过 50m 才有值
        "pk[i] = E[i] / cum[i] * 100 * it.kwh / E[N - 1];",  # 动态窗: 从起步攒到当前
        # 海拔图缺采样前向补值不断线 (2026-09-25 用户点名「海拔不要出现断
        # 点, 如果没有数据, 沿用最近一次可用的值」): 断口来自补路点 (信号
        # 断档的贴路补点没海拔) 和零星缺采样 (全库实测 ~2% 散布全程, 首点
        # 都带海拔) —— 缺的点沿用最近一次可用值铺平, 曲线一笔回到底; 点查
        # 读数跟画出来的值走; 轴域只收真实采样 (补值是真值副本, 不改轴),
        # 开头还没见过海拔的点没值可沿用, 仍从首个有效值起笔
        "const alt = pts.map(p => p[4]);",
        "} else if (lastA != null) alt[i] = lastA;   // 沿用最近一次可用值",
        'cv: "tps-cv-alt", ys: alt, lo: aMin - pad, hi: aMax + pad,',
        "const e = alt[i];",   # 点查读补值后的序列, 不是原始载荷
        # 起步前位移不足 50m 的点 (动态窗也不够格) 回铺首个有效值 —— 只剩
        # 开头一小截; hold 一圈纯防御 (满窗/动态窗总有一款接住)
        "for (let k = 0; k < first; k++) pk[k] = pk[first];",   # 首段回铺
        "if (pk[i] != null) hold = pk[i];",
        "else pk[i] = hold;",                         # 防御性 hold
        "hi2 = pure.niceCeil(Math.max(x2, 10));",   # 百公里口径整刻度, 全量盖住
        "lo2 = m2 < 0 ? -pure.niceCeil(Math.max(-m2, 2)) : 0;",  # 回收侧同法
        "Math.max(pMax, -pMin) > 0.5",               # kW 量级门槛 (session 同口径)
        "y2: hasPk ? {",                             # 电耗图右轴 = 百公里电耗
        "color: \"#e08a2e\",",
        '(v == null ? "—" : v.toFixed(1)) + " kWh/100km",',    # 点查读数跟新口径
        "const yOf2 = v => TOP + (1 - (v - lo2) / (hi2 - lo2)) * (h - TOP - BOT);",  # 副轴同款仿射 (无夹平)
        # 右轴定负 (回收为负): lo..hi 区间
        "const lo2 = y2 && y2.lo != null ? y2.lo : 0;",
        # 轴名/刻度文字 2026-09-25 曾随「只要柱状图」点名整批撤过一轮, 同日
        # 用户澄清原意 (「我让你把柱状图曲线图保留, 图下面的 3x2 的数据和播
        # 放控制不需要了。不是让你把图的坐标轴说明文字都去掉」) —— 全部
        # 复原: 顶带两行 (轴名/点查读数 + 顶格刻度) + x 刻度行, 轴名成对
        # (左 o.tag 右 y2.tag)/刻度带单位 (unit/fmtY/labColor)/轴名渐变
        # (tagGrad)/两端时刻都在 (正面钉在文末, 这里钉版式常量)
        "const TOP = 30, BOT = 14;",
        'ctx.font = "12px -apple-system, sans-serif";',   # 刻度字号 (2026-09-23 用户点名放大)
        "const pathOf = (vals, mapY, colorAt, runs) => {",  # 主/副轴共用全量画
        "const byColor2 = y2 ? pathOf(y2.ys, yOf2, () => y2.color) : null;",
        "fill: \"rgba(224,138,46,.16)\"",             # 累计曲线铺面积 (主轴)
        # 第三页「行驶统计」(2026-09-23 用户点名, 同日拆两张卡; 2026-09-24 对
        # 账官方口径重构): 三张卡的数据改服务端在原始 positions 上 SQL 聚合
        # (tests/test_trip_hist.py 直测), 客户端 speedHist 分桶退役 —— 旧算
        # 法四条口径差 (下采样载荷 / floor 档沿 / 混地形 / 模型定标), 单条
        # 38km 实测 80 档 129 vs 官方 86 Wh/km。载荷带 hist 直接用; 没带就
        # 兜底取数 (主路: openTrip 开弹层即调 tripHistKick, 2026-09-27 三页
        # 独立 —— 直方图只要行程身份, 与轨迹下载/地图预载全程无关), it.hist
        # 落在行程条目上 = 重开秒出; 数据到了 tick 自会画 (会话没起也画),
        # 失败 null 落定不留永久「读取中」, 全局在途闸 (令牌/在途位) 退役
        "if (it.hist) hist = it.hist;",
        "else if (!it.histTried) fetchTrackHist(it);",
        "function fetchTrackHist(it) {",
        "it.histTried = true;",
        "getJSON(`/tesla/trips/api/hist?ids=${key}`)",
        ".then(d => { it.hist = d; })",
        ".catch(() => { it.hist = null; });",
        # 档沿自然十进整除 0-9/10-19 (2026-09-24 用户点名; 面板原式是
        # numeric 真除四舍五入, 档值 80 = 75-84 —— 上午两版逐字对齐面板后
        # 按点名改自然档, 有意差半档): 点柱读数照实写档区间 (0 档 = 0-9);
        # 柱色按档中值 (档值+4.5) 归轨迹线五档配色 (色阶语义不变, 慢红快绿)
        'const lbBin = k => k * hist.step + "-" + (k * hist.step + 9);',
        "const binColor = k => TrackUtil.SPEED_COLORS[",
        "TrackUtil.speedBucket(k * hist.step + 4.5)];",
        "color: binColor,",
        "const K = vals.length;",
        # 左侧刻度槽 (2026-09-23 窄屏「坐标轴和数字偏移了」修的): 槽里只住
        # y 刻度与轴名, 柱区从槽右沿起 —— 2026-09-25「只要柱状图」撤文字
        # 那轮曾连槽一起退役, 同日用户澄清后随轴文字一并复原
        "const HIST_GUT = 34;",
        "const px0 = HIST_GUT, pw = w - px0;   // 柱区: 让出左侧刻度槽",
        "const slot = pw / K, bw = Math.min(slot * .58, 64);",
        "const TOP = 30, BOT = 28;",
        "const K = hist.t.length;",               # 点柱分档随档数走
        "Math.floor((e.clientX - box.left - HIST_GUT)",
                   "/ (box.width - HIST_GUT) * K)",
        # 2026-09-23 事故回归 (用户报「行驶数据和行驶统计都没有图」): trackutil
        # 漏导出 SPEED_STOPS, binColor/speedBucket 拿 undefined 当档位数组,
        # build() 一抛带死整条 rAF 循环 → 两页图全空。三道钉子: 工具库真导
        # 出 (node 侧另有真值直测) / tick 里 build 包 try-catch 保循环 /
        # 版本号跟上
        "} catch (err) { console.error(err); }",
        # 三卡: 时间 (分钟) / 里程 (km, 2026-09-24 用户点名第三张卡; 相邻
        # 采样里程差累加, 真实路面里程非弦距) / 平地电耗 (Wh/km, 官方
        # Grafana「不同速度下的能耗」面板逐条同口径 —— Σ(power·speed)/
        # Σ(speed)×10, 只收 ≥1km 行程, 0 档不报, 2026-09-24 二次对账把
        # 首版误写的 ÷平地均速×1000 修掉); 点柱读数带该档平地平均功率
        # (面板 avg_power 同口径); 没功耗/没平地段/全 <1km 的行程第三张
        # 整卡收起 (同海拔卡; 全 None 的 pk 数组也算没数据) —— 亮卡只看
        # 真有数据, 在途空框那套随 2026-09-27 三页独立退役 (空态盖整页,
        # 撤掉与三卡首亮同一拍, 没有卡蹦出来挤别人的时机)
        'doc.getElementById("tps-card-hist2").hidden =',
        "!(hist && hist.pk && hist.pk.some(v => v != null));",
        "function drawBars(cvId, vals, o)",     # 三卡共用的柱状图画法
        'drawBars("tps-cv-hist", hist ? hist.t : null, {',
        'hiMin: 1,',
        'drawBars("tps-cv-histkm", hist ? hist.km : null, {',
        'color: () => "#3987e5",',
        'if (hist && hist.pk) drawBars("tps-cv-hist2", hist.pk, {',
        'hiMin: 10,',
        'color: () => "#e08a2e",',
        '{ t: (hist.pw[k] == null ? "—" : hist.pw[k].toFixed(1)) + " kW",',
        'for (const cv of doc.querySelectorAll("#tp-hist canvas"))',
        "histSel = histSel === k ? null : k;",
        "function drawHist()",
        "drawHist();",                        # renderAll 全量画带上直方图
        # 点图查值 (2026-09-22 用户点名「点击坐标轴, 要给出具体点的值」,
        # 2026-09-23 点名三图联动): 模块级 inspIdx 一份共享 —— 三张图共
        # 用同一条时间轴, 点任意一张, 三张同时落虚线竖线各自读值 (每段色
        # 跟各自轴), 点回原处撤
        'for (const cv of doc.querySelectorAll("#tp-stats canvas"))',
        "cv.addEventListener(\"click\"",              # 点查接线 (canvas 静态, 绑一次)
        "inspIdx = inspIdx != null && Math.abs(px(i) - px(inspIdx)) < 12 ? null : i;",
        "if (inspIdx != null && o.tip) {",           # 三图同帧各画各的竖线
        "ctx.setLineDash([3, 3]);",                   # 点查虚线
        "const segs = o.tip(inspIdx);",               # 读数分段, 各自轴色
        "tip: i => {",                                # 三张卡都配 (点哪张读哪张)
        "module.exports = api",                       # UMD: node 直测纯函数
    ]:
        assert frag in js, f"动态页模块缺 {frag}"
    # 轴名/刻度文字全数复原 (2026-09-25「只要柱状图」撤文字一轮后, 用户澄
    # 清「我让你把柱状图曲线图保留, 图下面的 3x2 的数据和播放控制不需要
    # 了。不是让你把图的坐标轴说明文字都去掉」): 轴名 (o.tag/y2.tag)/刻度
    # 值与单位 (fmtY/unit/labColor)/轴名渐变 (tagGrad)/左刻度槽 (HIST_GUT)/
    # 末角 km-h/两端时刻 (fmtDurLive) 都在场 —— 那轮真该撤掉的只有带子
    assert 'tag: "速度"' in js and 'tag: "里程"' in js and 'tag: "海拔"' in js
    assert 'tag: "电耗"' in js and 'tag: "kWh/100km"' in js and 'tag: "时间"' in js
    assert 'tagGrad: TrackUtil.SPEED_COLORS,' in js
    assert 'unit: "km/h"' in js and 'unit: "km"' in js and 'unit: "分钟"' in js \
        and 'unit: "Wh/km"' in js and 'unit: "m"' in js
    assert "labColor" in js and "fmtY" in js and "HIST_GUT" in js
    assert 'ctx.fillText("km/h"' in js and 'ctx.fillText("0"' in js
    assert "FormatUtil.fmtDurLive" in js   # 两端时刻 (x 轴 0 与总时长)
