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
    for ref, v in (("js/tesla-viewport.js", 4), ("js/tesla-sheet-drag.js", 5),
                   ("js/view/charging-detail.js", 16),  # v16: Esc 一层一关 (v15 统计区三格)
                   ("css/tesla-charging-sheet.css", 12),  # v11: 总价一格 + 充电时间格; v10: pill 最右
                   ("css/tesla-trips-sheet.css", 40),    # v39: 曲线令牌采用 (ios, #sheet);
                                                 #   v38: 顶置 toast 副本拆净 (base 单源);
                                                 #   v37: 宽度查询折叠 (选中信息独占一行恒生效);
                                                 #   v36: 大屏手机一列 (顶置 toast 列内口径
                                                 #   + 驾驶员钮 40vw 封顶 192px);
                                                 #   v35: 弹层批整批破缓存 +1 (车机 immutable
                                                         # 吃住 2a2533f 开发中间态, 强制重下; 内容
                                                         # 零改动); v34: 底行还原单页标竖排 + 第四枚页标
                                                         # (3.10.0); v33: 弹层底行横排「详细行程」
                                                         # 并排 (已出批, 随第四页方案撤回); v31: 三页独立
                   ("css/tesla-trips-playback.css", 9),  # 播放条住回轨迹页 (翻页不收不还)
                   ("css/tesla-chargemap-map.css", 11),  # v10: 曲线令牌采用 (ios, #cm-sheet);
                                                         #   v9: 共享状态件收编 (.spin 副本拆);
                                                         #   v8: 图例挪画布右上 (左下让位恒定菜单键);
                                                         #   v7: sh-grid margin 显式钉住 (足迹
                                                         # css 裸规则拆净, 泄漏值收编); v6: 图例
                                                         # 搬画布内左下角 (极值随视野算)
                   ("css/tesla-map-canvas.css", 25),    # v24: 共享状态件收编 (.spin 副本拆);
                                                         #   v23: 图例/日期浮标挪画布右上 (左下让位恒定菜单键);
                                                         #   v22: 首回构造蒙版 (#fp-build z40 + 进度条);
                                                         #   v21: 驾驶员筛选并播放条行 + 进度条封顶
                                                         #   220px + 日期浮标去磨砂 (性能);
                                                         #   v20: 播放条挪地图卡外脚下
                   ("js/tesla-map-adapter.js", 14),       # v14: 探针手机端二修
                                                         # —— 出图一步整段退役
                                                         # (iOS 离屏 iframe 掐渲染,
                                                         # complete 永远等不来, 且
                                                         # 出图本就不验 Key) +
                                                         # onload 轮询双保险;
                                                         # v13: 类型错配人话
                                                         # (USERKEY_PLAT_NOMATCH →
                                                         # 「要 Web端 JS API 类型」);
                                                         # v12: 探针改两步验 (出图只证
                                                         # 渲染链, 坏 Key 也照样 complete ——
                                                         # 真伪在逆地理服务接口上验,
                                                         # INVALID_USER_KEY/SCODE 直译
                                                         # 给人看; 限流/配额算 Key 有效);
                                                         # v11: Safari 裸 iframe onload
                                                         # 不保证 → 显式 src; v10: 探针
                                                         # 声明序 (lint); v9: 坏 Key 探针
                                                         # 报人话
                                                         # (引擎没起来, 裸 TypeError
                                                         # 不见人); v8: probeKey 候选
                                                         # Key 探针 (设置页「测试」钮,
                                                         # 独立 iframe 建小图);
                                                         # 只留高德; v7: 样式固定幻影黑
                                                         # (v6: bounds 工厂 回放镜头跟框)
                   ("js/view/trips-preload-tiles.js", 3), # 只留高德: 拆 OSM 直接合成瓦片模板路
                   ("js/view/trips-preload-vector.js", 3),  # 走廊一页一会话只扫一遍 (sweptCorridors)
                   ("js/view/trips-export-video.js", 4),  # v4: Esc 收预览 (v3 只留高德)
                   ("js/view/trips-playback-loop.js", 13),       # v13: 单条收尾定格回
                                                               #   出发口径 (时刻跟播);
                                                               #   v12 恒一位小数防抖
                                                               #   + 流式节拍开播定死
                   ("js/view/trips-sheet-open.js", 12),          # v12: 破缓存批
                                                               #   (见 tesla-trips-sheet.css 行);
                                                               #   v11: openTrip 挂第四页 (gtrPageSync);
                                                               # v10: 三页独立: 直方图开弹层即取 +
                                                               # playTrack(defer) 先于地图预载
                   ("js/view/trips-playback-overlays.js", 8),
                   ("js/view/trips-playback-session.js", 15),    # v15: 单条 apply 走 setPlayClock
                                                                  # (时刻跟播); v14: defer 起播: 数据会话先挂
                                                                  # (curSess), begin 才进播放态
                   ("js/view/trips-gap-routing.js", 3),
                   ("js/view/trips-sheet-close.js", 14),  # v14: 破缓存批 (见上);
                                                           # v13: hideSheet 摘第四页 (gtrDetach);
                                                           # v12: Esc 收层 (v11 不刷新宿主列表)
                                                           # + 统计页 tp-hist 入下拉关闭区
                   ("js/view/trips-sheet-stats.js", 43),  # v43: 破缓存批 (见上); v42: 第四页挂/摘
                                                         # (nPages 现算 + 第四枚页标
                                                         # + ptr 提示字换字); v41: 三页独立: build 读
                                                         # curSess (不等地图) + 直方图开弹层即取
                                                         # (tripHistKick) + 翻页静默窗 + 整带收放/在途空框退役
                   ("js/view/trips-sheet-page.js", 10),   # v10: 破缓存批 (见上);
                                                         # v9: 合并载荷带 gid (第四页「详细行程」随它挂);
                                                         # v8: 解构接线 shiftStamp (时刻跟播平移)
                   ("js/view/trips-list-select.js", 3),   # 多选撤 100 段上限 (MERGE_MAX 退役)
                   ("js/trackutil.js", 5),   # v5: 扁平版 splitGapsFlat/decimateFlat 随原始轨迹层退役
                   ("js/track-animation.js", 3),
                   ("js/format.js", 6),      # 新增 shiftStamp (段首时刻平移段内行驶秒, 时刻跟播)
                   ("css/tesla-charging-cards.css", 13),  # v13: 共享状态件收编;
                                                          #   (.tail/.spin/.err-box/.retry 副本拆);
                                                          #   v12: 侧距统一 16 (gap 10 + 卡内衬 14);
                                                          #   v10: sec-head 顶距 0 (全 app 标题统一
                                                          # --content-top 一条线, 2026-09-27)
                                                          # v11: 快慢充 pill 常驻卡右上角,
                                                          # Tesla 字标立到它左边
                   # ⑤ 视图 css 撤 body 尺寸 + 菜单封顶吃 --shell-h 的 9 份
                   ("css/tesla-charging-page.css", 5),    # v4: 宽度查询折叠; 独立页死块 (header/菜单/日历/筛选行) 退役;
                                                          #   v3: 大屏手机一列 (.fl 标签列内封顶)
                   ("css/tesla-stats.css", 14),          # v14: 共享状态件收编;
                                                         #   (.tail/.spin/.err-box/.retry 副本拆);
                                                         #   v13: 侧距统一 16;
                                                         #   v12: 720 多栏退役 (统计卡恒两列/图卡恒单列); 独立页死块退役;
                                                         #   v11: 常去地点 12 根 (注释对齐)
                                                         # + 电池健康页复用统计卡/图卡 (共用底座)
                                                         # + .bh-note 口径脚注 + 表格退役 + id 规则改类
                                                         #   (行程统计复用) + 月度降高/滑块轨道/网格 dim
                                                         # + v9: 名字图加高; v10: ts-loc 340 (全量出柱)
                   ("css/tesla-groups.css", 14),  # v14: 共享状态件收编 (.spin/.err-box/.retry/#toast 副本拆);
                                                 #   v13: 侧距统一 16; v12: 宽度查询折叠 (列表 12px 恒生效);
                                                 #   独立页死块退役;
                                                 #   v11: 大屏手机一列 (顶置 toast 列内口径);
                                                 # v10: 破缓存批 (见上); v9: sec-head 顶距 0 + 跨度格字号特异性真收一档
                                                 # + 斜杠断行保底
                   ("css/tesla-group-trips.css", 6),  # v5: 进页即多选 (右上选圈, 未选降透明;
                                                         # 页头/说明/行内按钮撤净, 底条常驻取消/确定);
                                                         # v4: 破缓存批; v3: 整行可点反馈 (v2 第四页版;
                                                         # v1 二级页版已出批)
                   ("css/tesla-trips-cards.css", 5),       # v5: 共享状态件收编;
                                                         #   (.tail/.spin/.err-box/.retry 副本拆);
                                                         #   v4: 侧距统一 16 (#list 12→16, 卡内衬 13→14);
                                                         #   v1-3 历史漏钉, 本批补上
                   ("css/tesla-changelog.css", 5),  # v4: 共享状态件收编 (.spin 副本拆); v3: 宽度查询折叠;
                                                    #   独立页死块 (header/菜单/日历) 退役;
                   ("css/tesla-trips-page.css", 8),      # v8: 宽度查询折叠; 独立页死块 (header/菜单/日历/筛选行) 退役;
                                                 #   v7: 大屏手机一列 (.fl 标签列内封顶);
                                                 # v6: sec-head 顶距 0 (标题统一一条线)
                   ("css/tesla-map-page.css", 6),        # v5: 宽度查询折叠; 独立页死块 (header/菜单/日历/筛选行) 退役;
                                                         #   v4: sec-head 顶距 0 (标题统一一条线)
                   ("css/tesla-chargemap-page.css", 6),  # v5: 宽度查询折叠; 独立页死块 (header/菜单/日历) 退役;
                                                         #   v4: sec-head 顶距 0 (标题统一一条线)
                   ("css/tesla-live-page.css", 4),  # v4: 共享状态件收编 (.spin 副本拆); v3: 宽度查询折叠;
                                                    #   独立页死块 (header/菜单/日历) 退役;
                   ("css/tesla-live-driving.css", 20),  # v20: 平均电耗/最高车速两格退役 (剩
                                                         #   里程/已耗电); v19: 真底边对齐 +
                                                         #   填充条满格收口防溢
                   ("js/view/live-page.js", 9),         # v9: 平均电耗/最高车速两格接线拆净;
                                                         #   v8: 表盘上限 180 (刻度角度随
                                                         #   GAUGE_MAX 算); v7: 指针 + 已行驶
                   ("js/view/trips-sheet-driver.js", 17),  # v17: setPlayClock 单条
                                                          #   时刻跟播 (2026-10-17);
                                                          #   v16: 破缓存批 (见上);
                                                          #   v15: 头部「详细行程」钮撤 (改第四页, 3.10.0);
                                                          # v14: 头部按钮版 (已出批, 随第四页方案撤回)
                                                          # v13: Esc 收选单 (v12 电耗一位/段标题)
                   # 3.3.0 定稿: 左抽屉纯导航回归 (tab-dock 草稿整链撤); 车辆
                   # 选择住抽屉顶, 时间筛选整个下线 (全局 chips 退役), 账号
                   # 卡进设置页
                   ("css/tesla-base.css", 18),          # v18: #task-list 进
                                                         #   rise 容器清单 (任务卡
                                                         #   够不着 .view-scroll >
                                                         #   .card 那条);
                                                         #   v16: 共享状态件收编单源;
                                                         #   (.spin/.tail/.err-box/.retry);
                                                         #   v15: 列表入场错峰 (rise,;
                                                         #   头 6 项递进 45ms, 容器
                                                         #   = 全 app 内容列表/统计格/
                                                         #   图卡/changelog/状态面板/
                                                         #   地图统计行/设置卡);
                                                         #   v14: UI 重构基座 —— 动效令牌 —— 动效令牌
                                                         #   (--ease-ios/--ease-swipe) + 视图入场
                                                         #   动画 (view-in 淡入上浮, backwards 不
                                                         #   留 transform) + prefers-reduced-motion
                                                         #   全局收口;
                                                         #   v13: 宽度查询全折叠 + 悬浮菜单键恒定锚
                                                         #   (bottom 恒 bar-h+32, 地图让位块退役);
                                                         #   v12: 列上收口 overflow:hidden —— 屏外层
                                                         #   (placed-sheet/抽屉) 宽屏只出列不出
                                                         #   视口, 桌面每页右侧漏地点详情/改名;
                                                         #   v11: 大屏手机一列 (#shell 480px 居中
                                                         #   + transform 造包含块 + toast 列内口径);
                                                         #   v10: 菜单键挪左下角 + 开抽屉藏键;
                                                         #   v9: 全局悬浮菜单键 #menu-fab (Safari
                                                         #   左缘右划=系统后退, 边缘呼出失效);
                                                         #   v8: --content-top 落全局上边界 --top-clear
                                                         # (状态页顶进模糊地带修掉, 全 app 标题
                                                         # 同一水平线, music 同款)
                                                         # + 菜单圆键退役后无 chips 视图底部让位收起
                                                         #   (body.no-bar, --bar-clear 只剩安全区)
                   ("css/tesla-drawer.css", 11),        # v11: 曲线令牌采用 (ios);
                                                         #   v10: 足迹地图闸灰行 (.drw-leaf.off,;
                                                         #   拟合 Key 没填菜单不可点);
                                                         #   v9: 二级叶行缩进 45→28 (用户点名
                                                         #   嫌深); v8: 车辆选择卡住抽屉顶
                   ("css/tesla-pull-refresh.css", 3),   # v3: 曲线令牌采用 (ios); v1-2 历史漏钉, 本批补上
                   ("css/tesla-filter-bar.css", 6),     # 菜单圆键退役 (#menu-key 拆净,
                                                         # #bar-row.no-chips 整条收起)
                   ("css/tesla-settings.css", 30),      # v30: 后台任务卡 (进度条/状态行/重启钮);
                                                         #   v28: 曲线令牌采用 (ios + swipe);
                                                         #   v27: 顶置 toast 副本拆净 (base 单源);
                                                         #   v26: 宽度查询折叠; 独立页死块退役;
                                                         #   v25: 大屏手机一列 (顶置 toast 列内口径);
                                                         #   v24: 「获取方式」折叠块
                                                         #   撤下 (说明集中 README);
                                                         #   v23: 折叠块
                                                         #   (markdown 条目 + 可点链接);
                                                         #   v22: 「测试」次钮
                                                         #   (.btn-row 并排 +
                                                         #   .plain 描边蓝字);
                                                         #   v21: 行卡 wrap 加
                                                         #   flex: none (flex 容
                                                         #   器默认 shrink 把卡
                                                         #   压成 21px 半截, 左
                                                         #   滑起手也落空);
                                                         #   v20: 详情页地点列表改
                                                         #   圆角小卡 (次数右缘
                                                         #   单行); v19: 详情层
                                                         #   改全屏右滑页
                                                         #   (translateX(100%)/左
                                                         #   缘条/返回钮, 蒙版与
                                                         #   把手退役); v18: 地点
                                                         #   左滑退役 (#plc-list 摘
                                                         #   .swipe-list) + .plc-sum
                                                         #   汇总行 + 红钮; v17:
                                                         #   账号三卡
                   ("css/tesla-shell-floor.css", 13),   # v13: 后台任务页补进设置族
                                                         #   规则 (贴屏缘+零纵距);
                                                         #   v12: toast 重申块拆 (base 单源);
                                                         #   v11: 侧距统一 16;
                                                         #   v10: 大屏手机一列 (屏底 toast 列内口径);
                                                         #   v9: 设置族卡间纵距 + 账号/地点视图
                                                         #   补进族规则 (v8: 左缘边条 40px)
                   ("js/tesla-navigation.js", 4),       # v4: 足迹地图闸 (navigate 拦旁路);
                                                         #   v3: 视图直挂 hidden + 冷启首跳藏净
                   ("js/tesla-drawer.js", 14),          # v14: 设置组加后台任务行;
                                                         #   v13: 大屏手机一列 (左缘呼出带
                                                         #   drawerEdgeX 列内换算);
                                                         #   v12: 悬浮菜单键 #menu-fab 接线;
                                                         #   v11: 左缘右划统一呼出
                                                         #   (bindDrawerEdge 壳级
                                                         #   document 捕获段,
                                                         #   所有页面通用);
                                                         #   v10: 足迹地图闸
                                                         #   (setMapGate/mapGateOpen/
                                                         #   initMapGate, 拟合 Key 没填
                                                         #   菜单灰 + 不可导航);
                                                         #   v9: 设置组加常用地点行
                                                         # + 树状导航 + Lucide 图标表 (DRW_ICONS)
                                                         # + 账号设置独立页入组 (首位)
                                                         # + 行程统计入行程组 (trips 后)
                                                         # + 电池健康入充电组 (统计后)
                                                         # + 菜单圆键退役 (bootDrawer 只剩蒙版点击)
                   ("js/tesla-gesture.js", 10),         # v10: 大屏手机一列 (让位判定改
                                                         #   drawerEdgeX 列内口径);
                                                         #   v9: drawer 支线让出左缘带
                                                         #   (≤40px 归壳级, 边条例外);
                                                         #   v8: ptrMove 透传 (下拉位移挂载); v7: 被吞收尾自愈
                                                         # + ptr 判定收紧 (明确向下 dy > 2|dx|,
                                                         #   45° 斜角不再算下拉)
                                                         # + range 起手不仲裁 (月度时间窗滑块)
                   ("js/tesla-car-switcher.js", 6),     # pills 全局 setCar (currentCarLabel 退役);
                                                         # v5: 车图功能撤掉 (用户点名, v4 曾上相机钮)
                   ("js/tesla-filter-bar.js", 8),       # v8: 大屏手机一列 (anchorPop
                                                         #   弹层锚定换算列内); v7: 点外收 pointerdown
                                                         #   (v6 anchorPop #fp-drv
                                                         # 借弹层借锚定); v5: 菜单圆键退役 + no-chips
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
                   ("js/view/stats-chart-dimensions.js", 8),  # 开始时段 2 小时分组
                                                              # + 单价/时长分布 (表格/环形图退役)
                                                              # + renderDimBins 导出共用 (行程统计)
                                                              #   且改问 echarts 本尊 (跨视图旗号独立)
                                                              # + v7: 城市分布改竖排; v8: nameX/nameY
                   ("js/tesla-common.js", 6),      # v6: loadEcharts 版本钉 ?v=1 (echarts 从
                                                    #   no-cache 改 immutable 长缓存 —— 弱网
                                                    #   手机不再每次进统计页重下 1MB)
                   ("js/view/trips-stats-page.js", 4),   # 行程统计视图底座; v2: 五路数据
                                                              #   加司机里程分布 (tDrvData); v3: 注释
                                                              #   口径跟速度·电耗图更新; v4: locations
                                                              #   只带前 12 行全字段 (弱网减重)
                   ("js/view/trips-place-dialog.js", 8),  # v8: 名单拉取 top=0 瘦身
                                                              #   (弹层只要显示名)
                   ("js/view/trips-stats-charts.js", 12), # 行程统计图表; v12 = 气泡
                                                         #   改口「次停车」; v11 = 柱顶
                                                         #   次数标签退役; v10 = 柱名点击
                                                         #   补轴级 triggerEvent; v9/v8 =
                                                         #   柱身点击收回/放开; v6 = 全量
                                                         #   出柱+驾驶员横向+轴名; v5/v3 =
                                                         #   竖排柱状+气泡按下标/真速度
                   ("js/view/battery-page.js", 2),      # v2: 两峰值卡退役 (四卡) + 页名/卡名
                                                         # 改口电池健康 + 只采满充 (100%) 口径
                                                         # (首版 2026-09-27 新增)
                   ("js/view/trips-list-url.js", 2),    # 时间参数退役 (全时段)
                   ("js/view/map-page.js", 16),         # v16: fpViewOn 前台旗; v15: 回放联动统计
                                                         # (writeStats+收场还原); v14: fpPlaying 旗
                   ("js/view/map-tracks-render.js", 17), # v17: 暗铺模式 (回放收场
                                                         #   兜底重画不可见化); v16: 收尾视野; v14: 在途旗+回放藏层
                   ("js/view/map-boot.js", 13),         # v13: 换驾驶员点名重播; v12: 换筛选收播; v11: 自动
                                                         #   开播提前; v10: 收尾自动开播; v9: nudge 守卫
                   ("js/view/map-build-mask.js", 1),    # v1: 首回构造蒙版 (新建, roads/status 轮询)
                   ("js/view/chargemap-heatmap.js", 5), # v5: 图例极值/汇总三数/热力归一随视野算
                                                         # (视野内最大恒红端) + 图例搬画布内左下角
                   ("js/view/charging-cards.js", 12),   # v11: Tesla 字标改附加标 (快/慢充 pill 旁并排)
                                                          # v12: pill 换回最右 (卡右上角), 字标居其左
                                                          # + tesla-common v5: TESLA_MARK 字标常量在此
                   ("js/view/groups-page.js", 9),       # v9: 破缓存批 (见上);
                                                          #   v8: 每次进都重拉 (明细页会改分组;
                                                          #   v7 bindGestures 回 drawer)
                   ("js/view/group-trips-stream.js", 4),  # v4: 钩集住这 (gtrSel/gtrResetSel, 组内全钩起步)
                                                          # + 行渲染选圈 (页头/加移按钮撤); v3: 破缓存批;
                                                          # v2: 第四页版 (gtrStart/gtrLoad 复位标记);
                                                          # v1: 二级页版 (已出批, 与 page.js 一起退役)
                   ("js/view/group-trips-marks.js", 4),   # v4: 打/撤钩多选落定 (钩集与原组差整批提交);
                                                          # v3: 破缓存批; v2: 整行可点
                                                          #   (v1 只有钮可点, 用户报「item 点不了」)
                   ("js/view/changelog-view.js", 4),    # bindGestures 回 drawer
                   ("js/view/trips-list-page.js", 7),   # bindGestures 回 drawer
                   ("js/view/chargemap-time-filters.js", 10),  # v10: 屏缘缝条 (v9: ptrMove 整视图;
                                                               # v8: 度量档搬页内 pills mini-seg,
                                                               # 屏底 chip 退役 + bindGestures 回 drawer)
                   ("js/view/map-filters.js", 18),      # v18: 构造蒙版三挂点 (show/hide/refresh);
                                                         # v17: ptrMove 挂整视图; v16: 左缘缝条取证
                                                         # 播放条行尾; v13: 前台旗 + 自动开播
                   ("js/view/live-driving.js", 13),     # v13: 左缘缝条 + ptrMove 整舞台; v12: nudge 守卫
                                                         # v10: 最后一段行程直达钮退役 (用户点名, 整链拆净);
                                                         # v9: 驻车画最后一程轨迹+车位点收进视野
                                                         # (lvDrawLastTrack 按 id 记账不重拉)
                                                         # + v8: 驻车直达最后一程 + 标题两态 + 常显化
                   ("js/view/settings-db.js", 5),       # v5: 「留空保持」后缀退役;
                                                         #   v4: bindGestures 回 drawer
                   ("js/view/settings-drivers.js", 6),  # v6: 加载失败 toast (别装空列表);
                                                         # v5: 左滑三钮 + 行内改名 (v4: bindGestures)
                   ("js/view/settings-map.js", 20),     # v20: 构造进度文案 (蒙版接管进度显示);
                                                         # v19: 折叠块整链退役
                                                         # (HOWTO_*/mdItems 下岗);
                                                         # v18: markdown 一条一行
                                                         # (折行被当第二条);
                                                         # v17: 获取方式折叠块
                                                         # (markdown 条目渲染 +
                                                         # 链接可点) + 三框掩码
                                                         # placeholder (安全码
                                                         # 也头尾) + 「留空保持」
                                                         # 退役 + 存完回灰 (通行
                                                         # 一次性) + 足迹地图闸
                                                         # 同步;
                                                         # v16: 探针结论转述
                                                         # (v15: toast(verdict));
                                                         # v14: 闸状态声明序 (lint);
                                                         # v13: 测试改测框里的候
                                                         # 选 + 通过才解锁保存
                                                         # (Web端独立 iframe 建
                                                         # 小图 / Web服务 POST
                                                         # 候选); v12: 两把 Key
                                                         # 各添「测试」钮
                   ("js/view/settings-account.js", 6),   # v6: 三卡 + 名字行内
                                                         # 编辑 (Enter 存 Esc 弃)
                                                         # (v5: 弹层退役; v4:
                                                         # 独立页生命周期+手势)
                   ("js/view/settings-tasks.js", 1)):    # v1: 后台任务页 (新建:
                                                         # 任务卡现铺 + 5s 轮询 +
                                                         # 重启 confirm/飞行锁)
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
