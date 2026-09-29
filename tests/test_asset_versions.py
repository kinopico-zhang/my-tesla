"""壳级资产版本号与跨页样式锁步测试: 改过的 js/css 必须在 app.html 里带
新版本号 (老缓存不掺和); 同一份样式的多份视图副本 (页面标题 26px / 条数
副题 16px) 必须一起改, 落一份就是页面之间大小不一。2026-09-26 拆自
test_viewport_sheet_layer_guard (版本钉/条数锁步) 与 test_shell_wiring
(页面标题锁步 —— 那边满 200 行硬上限)。"""
from tests.tesla_static_files import served_page

SHELL = "/tesla"


def test_guard_assets_versioned_on_shell(auth):
    """改过的壳级资产在 app.html 里都带新版本号 (老缓存不掺和);
    bindSheetSettle 单点定义, 命名普查 (test_js_namespace) 自会盯撞名。"""
    html = auth.get("/tesla").text
    # v5: 轴向仲裁 (横滑交还原生, 明确向下才接管); 横滑分支不碰样式 ——
    #     仲裁窗口内改祖先样式会掐死原生滚动起手 (左滑不动实报)
    for ref, v in (("js/tesla-viewport.js", 3), ("js/tesla-sheet-drag.js", 5),
                   ("js/view/charging-detail.js", 15),  # v15: 统计区第二行三格, 充电时间格 (时长点名要回)
                   ("css/tesla-charging-sheet.css", 11),  # v11: 总价一格 + 充电时间格; v10: pill 最右
                   ("css/tesla-trips-sheet.css", 31),    # 三页独立: 整带收放规则撤掉
                                                         # (布局恒定, 地图/图卡大小不变)
                   ("css/tesla-trips-playback.css", 9),  # 播放条住回轨迹页 (翻页不收不还)
                   ("css/tesla-chargemap-map.css", 7),  # v7: sh-grid margin 显式钉住 (足迹
                                                         # css 裸规则拆净, 泄漏值收编); v6: 图例
                                                         # 搬画布内左下角 (极值随视野算)
                   ("css/tesla-map-canvas.css", 14),    # 足迹地图同款圆角卡 + zoom-ctl 收口
                                                         # #view-map; v14: 详情弹层整段撤 (点路
                                                         # 不弹窗); v13: 图例只留少—多渐变条
                   ("js/tesla-map-adapter.js", 4),        # 只留高德: 拆 Leaflet 垫片/瓦片 URL/坐标原样路
                   ("js/view/trips-preload-tiles.js", 3), # 只留高德: 拆 OSM 直接合成瓦片模板路
                   ("js/view/trips-preload-vector.js", 3),  # 走廊一页一会话只扫一遍 (sweptCorridors)
                   ("js/view/trips-export-video.js", 3),  # 只留高德: 拆 Leaflet <img> 瓦片合成路
                   ("js/view/trips-playback-loop.js", 12),       # 恒一位小数防抖 + 流式节拍开播定死
                   ("js/view/trips-sheet-open.js", 10),          # 三页独立: 直方图开弹层即取 +
                                                                  # playTrack(defer) 先于地图预载
                   ("js/view/trips-playback-overlays.js", 8),
                   ("js/view/trips-playback-session.js", 14),    # defer 起播: 数据会话先挂
                                                                  # (curSess), begin 才进播放态
                   ("js/view/trips-gap-routing.js", 3),
                   ("js/view/trips-sheet-close.js", 11),  # 关弹层不再原地刷新宿主列表
                                                           # + 统计页 tp-hist 入下拉关闭区
                   ("js/view/trips-sheet-stats.js", 41),  # 三页独立: build 读 curSess (不等地图)
                                                         # + 直方图开弹层即取 (tripHistKick)
                                                         # + 翻页静默窗 + 整带收放/在途空框退役
                   ("js/view/trips-sheet-page.js", 8),    # 解构接线 shiftStamp (时刻跟播平移)
                   ("js/view/trips-list-select.js", 3),   # 多选撤 100 段上限 (MERGE_MAX 退役)
                   ("js/trackutil.js", 5),   # v5: 扁平版 splitGapsFlat/decimateFlat 随原始轨迹层退役
                   ("js/track-animation.js", 3),
                   ("js/format.js", 6),      # 新增 shiftStamp (段首时刻平移段内行驶秒, 时刻跟播)
                   ("css/tesla-charging-cards.css", 11),  # v10: sec-head 顶距 0 (全 app 标题统一
                                                          # --content-top 一条线, 2026-09-27)
                                                          # v11: 快慢充 pill 常驻卡右上角,
                                                          # Tesla 字标立到它左边
                   # ⑤ 视图 css 撤 body 尺寸 + 菜单封顶吃 --shell-h 的 9 份
                   ("css/tesla-charging-page.css", 2),
                   ("css/tesla-stats.css", 9),           # v8: sec-head 顶距 0 (标题统一一条线)
                                                         # + 电池健康页复用统计卡/图卡 (共用底座)
                                                         # + .bh-note 口径脚注
                                                         # + 时间窗滑块改窗口本体宽块 (半透明蓝)
                                                         # + 表格视图退役 + 月度双柱
                                                         # + id 规则改类 (行程统计视图复用:
                                                         #   月度两幅降高/滑块轨道/网格 dim)
                                                         # + v9: .chart-vlabel 名字图加高
                                                         #   (竖排名每字一行要占高度)
                   ("css/tesla-groups.css", 9),   # v9: sec-head 顶距 0 + 跨度格字号特异性真收一档
                                                 # + 斜杠断行保底
                   ("css/tesla-changelog.css", 2),
                   ("css/tesla-trips-page.css", 6),      # v6: sec-head 顶距 0 (标题统一一条线)
                   ("css/tesla-map-page.css", 4),        # v4: sec-head 顶距 0 (标题统一一条线)
                   ("css/tesla-chargemap-page.css", 4),  # v4: sec-head 顶距 0 (标题统一一条线)
                   ("css/tesla-live-page.css", 2),
                   ("css/tesla-live-driving.css", 20),  # v20: 平均电耗/最高车速两格退役 (剩
                                                         #   里程/已耗电); v19: 真底边对齐 +
                                                         #   填充条满格收口防溢
                   ("js/view/live-page.js", 9),         # v9: 平均电耗/最高车速两格接线拆净;
                                                         #   v8: 表盘上限 180 (刻度角度随
                                                         #   GAUGE_MAX 算); v7: 指针 + 已行驶
                   ("js/view/trips-sheet-driver.js", 12),  # 总电耗恒一位 + 功耗格常显 + 段标题跟播
                   # 3.3.0 定稿: 左抽屉纯导航回归 (tab-dock 草稿整链撤); 车辆
                   # 选择住抽屉顶, 时间筛选整个下线 (全局 chips 退役), 账号
                   # 卡进设置页
                   ("css/tesla-base.css", 8),           # v8: --content-top 落全局上边界 --top-clear
                                                         # (状态页顶进模糊地带修掉, 全 app 标题
                                                         # 同一水平线, music 同款)
                                                         # + 菜单圆键退役后无 chips 视图底部让位收起
                                                         #   (body.no-bar, --bar-clear 只剩安全区)
                   ("css/tesla-drawer.css", 9),         # v9: 二级叶行缩进 45→28 (用户点名
                                                         #   嫌深); v8: 车辆选择卡住抽屉顶
                   ("css/tesla-filter-bar.css", 5),     # 菜单圆键退役 (#menu-key 拆净,
                                                         # #bar-row.no-chips 整条收起)
                   ("css/tesla-settings.css", 5),       # 账号卡 (从抽屉底部搬数据来源页)
                   ("css/tesla-shell-floor.css", 7),    # 内容起点换 --content-top + 地图头侧距 16px
                                                         # + 行程统计视图滚动器 920 宽
                   ("js/tesla-navigation.js", 3),       # 视图直挂 hidden + 冷启首跳藏净
                   ("js/tesla-drawer.js", 8),           # v8: 电池健康度改口「电池健康」
                                                         # + 树状导航 + Lucide 图标表 (DRW_ICONS)
                                                         # + 账号设置独立页入组 (首位)
                                                         # + 行程统计入行程组 (trips 后)
                                                         # + 电池健康入充电组 (统计后)
                                                         # + 菜单圆键退役 (bootDrawer 只剩蒙版点击)
                   ("js/tesla-gesture.js", 6),          # drawer 支线回归 (右划开抽屉)
                                                         # + ptr 判定收紧 (明确向下 dy > 2|dx|,
                                                         #   45° 斜角不再算下拉)
                                                         # + range 起手不仲裁 (月度时间窗滑块)
                   ("js/tesla-car-switcher.js", 6),     # pills 全局 setCar (currentCarLabel 退役);
                                                         # v5: 车图功能撤掉 (用户点名, v4 曾上相机钮)
                   ("js/tesla-filter-bar.js", 5),       # 菜单圆键退役 + no-chips/no-bar 几何接线
                                                         # (全局 chips 退役: 时间下线, 车辆回抽屉)
                   ("js/tesla-app-boot.js", 4),         # bootDrawer 回归 + 默认落地状态页 (时间订阅退役)
                   ("js/view/charging-page.js", 2),     # 时间参数退役 (全时段)
                   ("js/view/stats-page.js", 8),        # bindGestures 回 drawer + 时间参数退役
                                                         # + echarts 失败亮错误盒 (落表格退役)
                                                         # + 快慢充环形图退役 (渲染链瘦身)
                                                         # + 单价/时长分布渲染器接线
                   ("js/view/stats-chart-trend.js", 11),  # 月度双柱 + 12 个月时间窗滑块 (表格切换退役)
                                                         # + 月份轴年头带年份防重叠
                                                         # + 滑块改窗口本体 (自管指针拖拽)
                                                         # + 图位注册表添单价/时长两图
                                                         # + 注册表共用化: 行程统计 8 图登记 (ts- 键)
                                                         # + 电池健康曲线入注册表 (bhCurve)
                                                         # + v9: 司机里程图补登注册表 (tsDrv 漏登,
                                                         #   echarts 在 null 上炸成整页报错)
                                                         # + v11: 常去充电点改竖排柱状,
                                                         #   stackLabel (名字竖排) 导出共用
                   ("js/view/stats-chart-dimensions.js", 7),  # 开始时段 2 小时分组
                                                              # + 单价/时长分布 (表格/环形图退役)
                                                              # + renderDimBins 导出共用 (行程统计)
                                                              #   且改问 echarts 本尊 (跨视图旗号独立)
                                                              # + v7: 城市分布/区县下钻层改竖排柱状
                   ("js/view/trips-stats-page.js", 2),   # 行程统计视图底座; v2: 五路数据
                                                              #   加司机里程分布 (tDrvData)
                   ("js/view/trips-stats-charts.js", 5), # 行程统计图表; v5 = 常去地点/司机
                                                         #   两图改竖排柱状, 气泡按下标取行
                                                         #   (旧版按名字 find, 截断名对不上炸);
                                                         #   v4 = 司机里程分布 (竖排柱状, 前 8 + 其他);
                                                         #   v3 = 车速图
                                                         #   改真速度分布 (各速度段
                                                         #   行驶里程, positions 积分)
                   ("js/view/battery-page.js", 2),      # v2: 两峰值卡退役 (四卡) + 页名/卡名
                                                         # 改口电池健康 + 只采满充 (100%) 口径
                                                         # (首版 2026-09-27 新增)
                   ("js/view/trips-list-url.js", 2),    # 时间参数退役 (全时段)
                   ("js/view/map-page.js", 12),         # v12: 统计两格 + 选中态退役; v10: 汇总
                                                         # 拆视野联动 (summary 筛选口径); v9: ROAD_FMT_V=3
                   ("js/view/map-tracks-render.js", 10), # v10: 弹窗/选中态退役; v8: 汇总拆
                                                         # 视野联动; v7: 高倍只画视野内; v6: 走过的路
                   ("js/view/map-boot.js", 6),          # v6: 汇总拆联动; v5: 收尾视野增删; v4: 走过的路+换画
                   ("js/view/chargemap-heatmap.js", 5), # v5: 图例极值/汇总三数/热力归一随视野算
                                                         # (视野内最大恒红端) + 图例搬画布内左下角
                   ("js/view/charging-cards.js", 12),   # v11: Tesla 字标改附加标 (快/慢充 pill 旁并排)
                                                          # v12: pill 换回最右 (卡右上角), 字标居其左
                                                          # + tesla-common v5: TESLA_MARK 字标常量在此
                   ("js/view/groups-page.js", 7),       # bindGestures 回 drawer
                   ("js/view/changelog-view.js", 4),    # bindGestures 回 drawer
                   ("js/view/trips-list-page.js", 7),   # bindGestures 回 drawer
                   ("js/view/chargemap-time-filters.js", 8),  # 度量档搬页内 pills (地图脚下
                                                              # mini-seg, 屏底 chip 退役)
                                                              # + bindGestures 回 drawer + 左缘条绑定回归
                   ("js/view/map-filters.js", 9),       # v9: 弹层收尾退役 (点路不弹窗);
                                                         # v8: 细化防抖收尾退役 (原始轨迹层拆净)
                   ("js/view/live-driving.js", 11),     # v10: 最后一段行程直达钮退役 (用户点名, 整链拆净);
                                                         # v9: 驻车画最后一程轨迹+车位点收进视野
                                                         # (lvDrawLastTrack 按 id 记账不重拉)
                                                         # + v8: 驻车直达最后一程 + 标题两态 + 常显化
                   ("js/view/settings-db.js", 4),       # bindGestures 回 drawer
                   ("js/view/settings-drivers.js", 4),  # bindGestures 回 drawer
                   ("js/view/settings-map.js", 10),     # v10: 两把高德 Key 分卡各配各的保存
                                                         # (v9: Web 服务 Key 字段 + 保存后踢 worker)
                   ("js/view/settings-account.js", 4)):  # 账号设置独立页: 生命周期
                                                          # + 手势 + acctCardLoad 重拉
        assert f"{ref}?v={v}" in html, f"{ref} 版本号没跟上 (期望 v={v})"
    # tab-dock / 时间档模块资产整个退役: include 不许回潮
    assert "tesla-tab-dock" not in html and "tesla-time-range" not in html


def test_count_badge_size_in_lockstep(auth):
    """三张列表页标题旁的条数副题 (共 N 次 / N 组) 是同一份样式的三处副本
    (charging-cards / groups / trips-page): 12px 用户点名字太小, 14px 还嫌
    小, 最终放大到 16px (比正文 14 还大一号; 2026-09-22) —— 与 sec-head h2
    同款「三份副本一起改」规矩, 落一份就是页面之间大小不一。"""
    css = {ref: auth.get(f"/tesla/static/css/{ref}").text for ref in
           ("tesla-charging-cards.css", "tesla-groups.css", "tesla-trips-page.css")}
    for name, body in css.items():
        assert ".count-badge { font-size: 16px; color: var(--ink-3); }" in body, \
            f"{name} 条数副题字号丢了"
    joined = "".join(css.values())
    assert ".count-badge { font-size: 12px" not in joined, "条数副题 12px 旧字号回潮了"
    assert ".count-badge { font-size: 14px" not in joined, "条数副题 14px 旧字号回潮了"


def test_page_titles_music_sized(auth):
    """页面标题加大到音乐 App 同款 (用户点名): sec-head h2 是页面级标题
    (充电记录/行程分组/行程轨迹/两张地图页/充电统计/状态页共用), 26px/700/
    -.5px 对齐 music 的 .pane-title; 规则在七份视图 CSS 里各有一副本 (充电卡/
    分组/行程/足迹地图/充电地图/统计/状态驾驶), 改一份漏六份就是大小不一 ——
    七份一起钉死。"""
    page = served_page(auth, SHELL)
    rule = ".sec-head h2 { font-size: 26px; font-weight: 700; letter-spacing: -.5px; }"
    assert page.count(rule) == 7, "页面标题 26px 规则应有七份副本"
    assert ".sec-head h2 { font-size: 17px" not in page   # 小字不许回潮
