"""实时驾驶页面测试: 接口鉴权, 页面骨架, 布局加固。
拆自 test_live.py (结构化重构, 代码逐字节未动)。"""

from tests.tesla_static_files import page_asset_paths, page_js, served_page


# ---------------------------------------------------------------- 鉴权 / 页面

def test_live_api_requires_login(client):
    r = client.get("/tesla/live/api/status")
    assert r.status_code == 401
    assert r.json() == {"detail": "未登录"}


def test_live_page_skeleton(auth):
    """页面骨架: 车速/时长/电量格, 状态轮询 + 轨迹刷新 (复用行程接口),
    常显化 (2026-09-26 用户点名: 空态/结束态占位屏退役, 任何车辆态都显
    面板+地图) / 结束浮钮直达 / 信号中断提示 / 高德失败降级。"""
    html = served_page(auth, "/tesla")
    js = page_js(auth, "/tesla")
    assert 'registerView("live"' in html   # 驾驶视图注册 (壳内无独立页)
    for sel in ("lv-speed", "lv-elapsed", "lv-soc", "lv-range", "lv-km",
                "lv-kwh"):
        assert f'id="{sel}"' in html, sel
    # 车速仪表盘 (2026-09-28 点名「当前车速改成仪表盘样式, 旁边是电池电
    # 量, 剩下的数据放在下面」+ 五连追点, 原话全文见 app.html 同段注释):
    # 顶卡左右两区 —— 左区半圆表盘带指针 + 车速一行读在正下; 右区大号电
    # 池 (百分比住图标里) + 剩余续航; 已行驶窄条 + 里程/已耗电两格 (另
    # 两格 09-29 用户点名删掉); 两列文字行贴卡底同高
    assert 'class="gauge-card"' in html
    # viewBox 底带裁到 103 (v19 底边对齐): 表心下的空白带砍掉, 元素底边≈
    # 墨迹底; 指针尾缩回毂内 (y1=99, 尾长 3 < 毂半径 6), 任何角度不出毂
    assert 'viewBox="0 0 220 103"' in html \
        and 'id="lv-gauge-arc"' in html and 'id="lv-gauge-ticks"' in html
    assert 'id="lv-gauge-labels"' in html and 'class="gauge-readout"' in html \
        and 'class="gauge-batt"' in html
    assert '<g id="lv-gauge-needle">' in html and 'y1="99"' in html
    assert 'class="lv-strip"' in html
    assert '<span class="lb">当前车速</span><b id="lv-speed">' in html  # 一行式读数
    assert "display: flex; align-items: baseline; justify-content: center; gap: 6px;" in html
    assert "lvBuildGauge" in js and "lvSetGauge" in js
    assert "GAUGE_MAX = 180" in js     # 表盘上限 180 (追点「设置成 180 吧」)
    assert "s * 180 / GAUGE_MAX" in js   # 刻度角度随上限算, 不再钉死 240 口径
    assert "f * 180 - 90" in js   # 指针随车速转 (半圆两端 ±90°), 过渡交 CSS
    # 指针表心: CSS transform-origin 与 js 的 GAUGE_CX/GAUGE_CY 两处同源
    assert "transform-box: view-box; transform-origin: 110px 96px;" in html
    assert "剩余续航" in html     # 续航标签改口用户原话, 额定续航退役
    # 车速数字与续航数字同规格 (16px/650); 电池放大 + 贴续航行上方, 两列文字行贴底
    assert ".gauge-readout b { font-size: 16px; color: var(--ink-1);" in html
    # 电池几何 + 填充满格收口 (用户报「充满之后绿色都溢出来了」): soc% 按
    # 含边框内盒算再叠 left:2px, ≥97% 右缘越内壁从圆角戳出 —— max-width
    # 按内轨收口, 满格右缘离内壁 2px 与左边距对称
    assert "width: 112px; height: 54px; flex: none;" in html \
        and "max-width: 165px;" in html \
        and "max-width: calc(100% - 4px);" in html
    # 两区五五开 + 电池下移取平衡 (追点「车速和续航宽度五五开, 电池再往下一点」):
    # flex 对半, 电池 margin-top auto 贴着续航行 (空当全让到顶上)
    assert ".gauge { flex: 1; min-width: 0;" in html \
        and "margin-top: auto;" in html and "justify-content: flex-end;" in html
    # 两图形底边对齐 (两轮追点 —— v18 的 -2px 把电池 gap 方向搞反, 电池比
    # 表盘墨迹低 ~18px): svg 底带裁到 103 后车速行离表盘 10px 与电池离续航
    # 行 10px (gap) 镜像, 两侧图形元素底边同一水平线 (墨迹再高 ≤2px 随宽
    # 度缩放, 矮屏同口径)
    assert "gap: 6px; margin-top: 10px;" in html
    assert ".tile .val .n { display: inline-block; text-align: center; }" in html
    assert 'return m + " 分钟";' in js and '" 小时 " + r + " 分"' in js
    # 旧版式禁词 (钉 live 自己的文件 —— 拼串口径下 tesla-base 注释里有别家
    # 的 hero-bar, 全份禁会误伤); 平均电耗/最高车速两格 2026-09-29 用户点
    # 名删除, id 与后端字段 (只 live 消费) 一并禁回潮
    live_assets = "".join(auth.get(ref).text
                          for ref in page_asset_paths(auth, "/tesla")
                          if "/css/tesla-live-driving" in ref or "/js/view/live-" in ref)
    assert "hero" not in live_assets and "batt-card" not in live_assets \
        and "lv-avg" not in html and "lv-vmax" not in html \
        and "wh_per_km" not in live_assets and "speed_max" not in live_assets
    # 底边对齐的旧口径不许回潮 (-8 / 矮屏 -5 / v18 错向 -2 都不对齐)
    assert "margin-top: -8px" not in live_assets \
        and "margin-top: -5px" not in live_assets \
        and "margin-top: -2px" not in live_assets
    # 盒内右对齐是「数据格不居中」的根子, 续航标签旧口径一并退役
    assert "text-align: right" not in live_assets
    assert "额定续航" not in live_assets
    assert '"/tesla/live/api/status"' in html
    assert "POLL_MS = 5000" in html
    assert '"/tesla/trips/api/" + driveId + "/track"' in html
    # 占位屏退役: 不在开车也常显面板 (最后已知电量/续航/车速 0) + 地图位置
    assert "lvRenderParked" in html
    assert 'id="idle"' not in html and 'id="ended"' not in html
    assert "state-view" not in html
    # 刚结束: 面板定格末帧 (endedFreeze 分支照旧); 地图顶中的直达钮
    # (2026-09-27 两上两撤, 用户点名「状态页面上最后一段行程按钮，去掉」)
    # 整链退役 —— 元素/样式/接线/内存跳转键一并拆净, 禁词钉拼串全份
    assert "endedFreeze" in html
    assert "ended-pill" not in html
    assert "本次行程已记录" not in html
    # 驻车显示最后一段行程 (2026-09-27 用户点名): 面板填最后一程时长/两格;
    # 同日再点名「状态是直接显示最后一段行程的轨迹, 以及车的当前位置」——
    # 地图画最后一程速度色轨迹 + 车位点并收进视野 (按行程 id 记账, 5s 轮询
    # 不重拉); 副行只留日期 (起止时刻同日点名撤掉)
    assert "const d = s.last_drive;" in html
    assert '"最后行程 " + d.date;' in js
    assert "d.end.slice(11)" not in js
    assert "lvDrawLastTrack" in html and "parkedTrackKey" in html
    assert '"/tesla/trips/api/" + id + "/track"' in js
    assert "lvMap.setFitView([...routeLine, carMarker]" in js
    assert "lvSetCar(s.lng, s.lat, !d)" in js       # 有轨迹不追焦车位
    assert "lvEndedKey" not in html                 # 内存跳转键随直达钮退役
    assert "最后一段行程 · 查看行程" not in html
    assert "信号可能中断" in html
    assert "地图暂不可用" in html
    assert "car-dot" in html
    # 实时数字定宽盒: 位数变化 (59 分钟→1 小时 / 9%→100%) 不推动布局; 车速
    # 2026-09-28 改表盘后数字居中读 (对称晃动天然成立); 电量百分比 v14 起住
    # 进定宽的电池图标里天然不晃, 定宽盒只剩时长/续航与数据格
    assert "min-width: 3ch" in html and "min-width: 7ch" in html
    assert "#lv-speed { display: inline-block;" not in html
    assert '<span class="n">' in html
    # 车图 (2026-09-27 曾上又撤, 用户点名「车的图片还是删除吧」): 抠好的图
    # 挪去 my-home 仓根 PNG 供自取, 页面不再引用 (css 同批 v10)。禁词钉
    # 具体类名/图路径 —— 裸 "tesla-car" 会误伤 tesla-car-switcher (选车模块)
    assert "lv-car" not in html
    assert "/tesla/static/img/tesla-car.webp" not in html
    assert "cur && cur.driving" in html   # 地图异步就位后补画车点/轨迹
    # 地图引擎经适配层 (服务商可切, 设置页定), 样式兜底幻影黑在适配层
    assert 'mapLib.createMap("lv-map"' in html
    # "©…auto navi" 版权与高德 logo 都按需求去掉
    assert ('#map .amap-copyright, #lv-map .amap-copyright,\n'
            '#map .amap-logo, #lv-map .amap-logo { display: none !important; }') in html
    # 地名首帧竞态: 样式数据异步加载, complete 后延时补重渲染才有地名
    # (getFeatures 是高德方言 → 有这方法才补画; lvMap 判空 → 出视图销毁后
    #  1.5s/5s/12s 的补拍不再撞 null, 2026-10-01 实报 window_error)
    assert 'if (lvMap && lvMap.getFeatures) lvMap.setFeatures(lvMap.getFeatures());' in html
    assert "s.soc > 50" in html and "#32d74b" in html


def test_live_page_layout_bombproof(auth):
    """真机排版修复 (2026-09-13 用户报告): 速度+单位 flex 不换行 / 右列可收缩 /
    数据格 2×2 防溢出; 历史轨迹速度着色 + 末端连线接车点。
    2026-09-26 手机重排 (用户报「页面歪七扭八, 要适配手机界面」+「地图显示出
    来不了」): 地图白板根子 = 建图抢在驾驶态亮出来之前, 高德在 display:none
    的 0×0 容器里建图, 之后掀开也不重排 —— 只许 enterDriving 一处建; 舞台
    底距吃 --bar-clear (悬浮筛选条不再压地图一角); 地图保底高度 + 矮屏收密度。"""
    html = served_page(auth, "/tesla")
    js = page_js(auth, "/tesla")
    # 车速一行读数: 标签+数字+单位 基线一行永不换行 (窄屏/页缩放挤压时单位
    # 曾掉到第二行, 用户真机踩坑)
    assert "display: flex; align-items: baseline; white-space: nowrap;" in html
    # 窄条副行 (出发时刻/最后行程日期) 推到右端, 超宽省略号 (原 hero 右列
    # 2026-09-28 下放成窄条)
    assert ".lv-strip .sub { margin-left: auto;" in html
    assert "text-overflow: ellipsis" in html
    # 数据格 flex 撑半宽 + 换行兜底 (原 2×2 网格, 剩两格恰一行)
    assert "flex-wrap: wrap" in html and "flex: 1 1 calc(50% - 5px);" in html
    # 已行驶按服务器时钟走 (now_utc 校偏差), 手机时钟不准不再是 0:00
    assert "let serverSkew = 0;" in js
    assert "if (s.now_utc != null) serverSkew = s.now_utc - Date.now() / 1000;" in js
    assert "Date.now() / 1000 + serverSkew - s.started_utc" in js
    # 地图白板修复 (2026-09-26): 建图只许 #live 亮出来之后 —— 进视图抢建
    # 会落在隐藏容器里 (引擎缓存住时配置一个来回快过首轮状态)。常显化后
    # 两个调用点 (驾驶态 enterDriving / 停车态 poll), 都在 showState("live")
    # 之后; initMap 只许一处定义
    assert 'if (!lvMap) initMap();' in js
    assert js.count("initMap()") == 3, "initMap 一处定义两处调用 (都等 #live 亮)"
    # 副行只报出发时刻 (最高车速格 2026-09-29 删掉, 不在这补)
    assert '"出发 " + (s.start ? s.start.slice(11) : "–")' in js
    # 舞台底部让位屏底悬浮筛选条 (各视图 .view-scroll 同款 --bar-clear):
    # 原来只让 safe+10, 地图卡底下 ~50px 被悬浮条压着像缺了个角
    assert "padding: var(--content-top) 14px var(--bar-clear);" in html
    # 地图保底高度 (面板再挤也不许把地图挤成缝) + 矮屏 (横屏手机) 收一档密度
    assert "flex: 1; min-height: 200px;" in html
    assert "@media (max-height: 560px)" in html
    # 历史轨迹: 速度着色 (行程回放同套色阶) + 末端连线接到车当前位置
    # (trackutil v5 = 2026-09-29 原始轨迹层退役, 扁平版函数; 版本钉子跟着换)
    assert '<script src="/tesla/static/js/trackutil.js?v=5"></script>' in html
    assert "TrackUtil.speedLines(t.pts)" in js
    assert "TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(" in js
    assert "tailLine.setPath([trackEnd, p])" in js
    # 纯蓝轨迹不许回来 —— 只查驾驶视图自己的脚本 (整壳口径下别的视图
    # 合法用这抹蓝: 充电功率曲线/热力图梯度/足迹图选中线)
    live_js = "".join(auth.get(ref).text
                      for ref in page_asset_paths(auth, "/tesla")
                      if "/js/view/live-" in ref)
    assert 'strokeColor: "#3987e5"' not in live_js


def test_live_page_title(auth):
    """状态页一级标题 (2026-09-27 用户点名「状态页面没有标题, 跟其他页面一样。
    标题两种 状态：行驶, 状态：驻车」): sec-head h2 与其他页同款 26px, 住
    .live-stage 顶 (侧距/顶距由舞台的 padding 出, 只补底距); 文案由 poll
    三个分支换字 (行驶/刚结束落停车/常态停车), 离开视图归中性「状态」等首轮
    状态。同日各页 sec-head 顶距统一 0 —— 全 app 标题同一水平线
    (--content-top, 见 test_shell_wiring 的 top_clear_band)。"""
    html = served_page(auth, "/tesla")
    js = page_js(auth, "/tesla")
    assert '<div class="sec-head"><h2 id="lv-title">状态</h2></div>' in html
    assert '.live-stage .sec-head { display: flex; align-items: baseline;' \
        ' gap: 8px; padding: 0 0 4px; }' in html
    assert js.count('$("#lv-title").textContent = "状态：行驶";') == 1
    assert js.count('$("#lv-title").textContent = "状态：驻车";') == 2   # 刚结束/常态停车
    assert '$("#lv-title").textContent = "状态";' in js                 # 离开归中性
