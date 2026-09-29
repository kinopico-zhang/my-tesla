"""轨迹分组测试: 分组存取改名删除, 跨度, 校验; 行程视图分组入口 /
过路费工具 / 司机选择 / 导出视频。
拆自 test_trips.py (结构化重构; P7 起按 3.0 单壳改口径 —— 分组管理是
壳内分组视图, 打开分组走内存跳转, 不再有 referrer/back)。"""
from datetime import datetime, timedelta
from app.tesla.models import Drive
from tests.seed_factories import seed_addresses, seed_charging, seed_drive

from tests.tesla_static_files import served_page

# ---------------------------------------------------------------- 轨迹分组

def test_trip_group_save_list_rename_delete(auth, db):
    """存分组: ids 排序去重落库; 列表段数/里程/日期跨度按当前数据现算;
    改名只动名字; 删除只删自有库记录 (行程原数据不动)。"""
    t = datetime(2026, 5, 1, 0, 32)
    seed_drive(db, id=11, start_date=t, end_date=t + timedelta(hours=1),
               distance=42.5)
    seed_drive(db, id=12, start_date=t + timedelta(days=2),
               end_date=t + timedelta(days=2, hours=1), distance=10.04)
    seed_drive(db, id=13, start_date=t + timedelta(days=2, hours=3),
               end_date=t + timedelta(days=2, hours=4), distance=8.0)

    r = auth.post("/tesla/trips/api/groups",
                  json={"name": "五一小长途", "ids": [13, 11, 12, 11]})  # 乱序 + 重复
    assert r.status_code == 200
    g = r.json()
    assert g["ids"] == [11, 12, 13]           # 升序去重
    assert g["n"] == 3 and g["km"] == 60.5
    assert g["span"] == "2026/05/01~2026/05/03"   # 最早~最晚出发日 (紧凑斜杠, 2026-09-25)

    r = auth.get("/tesla/trips/api/groups")
    assert [x["name"] for x in r.json()] == ["五一小长途"]

    assert auth.patch(f"/tesla/trips/api/groups/{g['id']}",
                      json={"name": "改名了"}).json()["name"] == "改名了"
    # 行程原数据没被动过
    assert db.get(Drive, 11).distance == 42.5

    assert auth.delete(f"/tesla/trips/api/groups/{g['id']}").json() == {"ok": True}
    assert auth.get("/tesla/trips/api/groups").json() == []
    assert auth.delete(f"/tesla/trips/api/groups/{g['id']}").status_code == 404


def test_trip_group_span_single_date_and_km_rounding(auth, db):
    """同一天的分组 span 就是那一天; 里程按现算求和。"""
    t = datetime(2026, 5, 1, 8, 0)
    seed_drive(db, id=21, start_date=t, end_date=t + timedelta(hours=1),
               distance=1.11)
    seed_drive(db, id=22, start_date=t + timedelta(hours=2),
               end_date=t + timedelta(hours=3), distance=2.22)
    r = auth.post("/tesla/trips/api/groups", json={"name": "同城", "ids": [21, 22]})
    assert r.json()["span"] == "2026/05/01"
    assert r.json()["km"] == 3.3


def test_trip_group_open_aggregates(auth, db):
    """分组条目带汇总 (2026-09-23 用户点名弹层一开就显数, 不等地图):
    起止/时长/最高速/总电耗/平均电耗与合并汇总头同口径 —— Σ(续航差×
    充电换算系数) ÷ 总里程; 没充电定标的老车电耗留 None (前端显 —)。"""
    seed_addresses(db)
    # 充电记录定标: 30 kWh 换 200km 额定续航 → 0.15 kWh/km
    seed_charging(db, id=1, charge_energy_added=30.0,
                  start_rated_range_km=100.0, end_rated_range_km=300.0)
    t = datetime(2026, 5, 1, 0, 32)
    seed_drive(db, id=41, distance=80.0, duration_min=60, speed_max=118,
               start_date=t, end_date=t + timedelta(hours=1),
               start_rated_range_km=200.0, end_rated_range_km=100.0)   # 15 kWh
    seed_drive(db, id=42, distance=30.0, duration_min=45, speed_max=96,
               start_date=t + timedelta(hours=3),
               end_date=t + timedelta(hours=3, minutes=45),
               start_rated_range_km=100.0, end_rated_range_km=80.0)    # 3 kWh
    g = auth.post("/tesla/trips/api/groups",
                  json={"name": "五一", "ids": [41, 42]}).json()
    assert g["start"] == "2026-05-01 08:32"     # 本地时间 (UTC+8), 首段出发
    assert g["end"] == "2026-05-01 12:17"       # 末段到达
    assert g["min"] == 105 and g["speed_max"] == 118
    assert g["kwh"] == 18.0                     # 15.0 + 3.0
    assert g["wh_per_km"] == round(18.0 / 110 * 1000)   # ≈164


def test_trip_group_validation(auth, db):
    """校验: 无效行程 (不存在/未结束) 404; 名字/段数越界 422;
    去重后不足 2 段 / 名字 strip 后为空 400。"""
    t = datetime(2026, 5, 1, 0, 32)
    seed_drive(db, id=31, start_date=t, end_date=t + timedelta(hours=1))
    seed_drive(db, id=32, start_date=t, end_date=None)          # 未结束行程
    post = "/tesla/trips/api/groups"

    assert auth.post(post, json={"name": "x", "ids": [31, 99]}).status_code == 404
    assert auth.post(post, json={"name": "x", "ids": [31, 32]}).status_code == 404
    assert auth.post(post, json={"name": "x", "ids": [31, 31]}).status_code == 400
    assert auth.post(post, json={"name": "   ", "ids": [31, 32]}).status_code == 400
    assert auth.post(post, json={"name": "x" * 31, "ids": [31, 99]}).status_code == 422
    assert auth.post(post, json={"name": "x", "ids": [31]}).status_code == 422

    # 改名: 未知分组 404
    assert auth.patch("/tesla/trips/api/groups/999",
                      json={"name": "y"}).status_code == 404


def test_trips_page_toll_ui_removed(auth):
    """高速费先撤掉 (用户点名): 打开行程不再自动估价 (顺手省高德驾车规划
    配额), 弹层 chip/估价链全下线; 已算过的和 /toll 接口留在库里, 要恢复
    随时接回 (后端读写照钉在 test_trips_consumption_and_tolls)。"""
    html = served_page(auth, "/tesla")
    for frag in ('id="sh-toll"', 'id="sh-drv"', "autoCalcToll", "calcTripToll",
                 "TOLL_WAYPOINTS", "无高速费"):
        assert frag not in html, f"高速费前端没撤净: {frag}"
    # 批量入口/面板也一直不许回潮
    assert 'id="toll-btn"' not in html
    assert 'id="tollpanel"' not in html


def test_trips_page_has_driver_picker(auth):
    """行程页驾驶员标注: 弹层选择行 + 卡片 pill + 标注接口都挂在页面上。"""
    html = served_page(auth, "/tesla")
    for frag in ['id="sh-drv-btn"', "setupDriverPicker", "syncDrvBtn",
                 'class="ct-drv${it.driver_id != null ? "" : " def"}"',
                 ".ct-drv.def", "/tesla/api/drivers",
                 "function postJSON(", "已标注为", "已清除标注"]:
        assert frag in html, f"行程页缺少驾驶员标注片段 {frag}"
    # 卡片 pill 默认驾驶员兜底也显示 (弱化 .def 与显式标注区分)
    # 没配驾驶员时选择器藏 (兜底, 不会闪一个空下拉)
    assert "driversCache.length > 0) {" in html
    # 查看轨迹按钮已撤 (用户点名): 整行点击就是查看轨迹, 驾驶员 pill 挪右上角
    assert "查看轨迹" not in html
    assert "ct-arrow" not in html
    assert "else openTrip(it)" in html


def test_trips_page_group_create_and_open(auth):
    """分组管理在壳内分组视图 (test_groups.py 钉), 行程视图只留创建入口:
    多选 → 存为分组; 旧分组面板 (入口按钮/CSS/DOM) 不许回来; 打开分组
    走内存跳转 navigate + openMerged, 逗号深链 (旧链接 ?ids=a,b) 也认。"""
    html = served_page(auth, "/tesla")
    for frag in ['id="gp-btn"', "存为分组", 'id="gp-name"', 'id="gp-save"',
                 "api/groups", 'id="toast"', "$(\"#sel-go\").addEventListener"]:
        assert frag in html, f"行程页缺少分组片段 {frag}"
    # 合并键两种形式: "首-尾" / 逗号 (旧链) —— openByKey 按含 - 或 , 判合并
    assert "/[-,]/.test(key)" in html
    # 旧分组面板的三件套 (头部按钮 / 面板样式 / 面板 DOM) 全删
    assert 'id="groups-btn"' not in html
    assert 'id="gpanel"' not in html and ".gpanel" not in html
    assert 'id="gp-close"' not in html and "closeGroups" not in html
    # 3.0 零历史条目: 没有 referrer 探测 / history.back 回分组页的旧路
    assert "document.referrer" not in html
    assert "history.back()" not in html

def test_trips_page_export_video(auth):
    """导出视频: 播放条录制钮 + 成片预览弹层 + 存相册链路都挂在页面上。"""
    html = served_page(auth, "/tesla")
    for frag in ['id="pb-rec"', 'aria-label="导出视频"', 'id="rec-modal"',
                 'id="rec-video"', 'id="rec-save"', 'id="rec-close"',
                 "playsinline", "存到相册", "function recMime(",
                 "function recCompose(", "function startRecExport(",
                 "function stopRecExport(", "function recShowResult(",
                 "function recCloseModal(", "out.captureStream(30)",
                 "new MediaRecorder(", "videoBitsPerSecond: 6e6",
                 "navigator.share({ files: [recFile]", "anim.restart();",
                 "preserveDrawingBuffer: true", "function patchGLKeepBuffer()",
                 "此浏览器不支持录制视频", "录制失败 (没有内容)"]:
        assert frag in html, f"行程页缺少导出视频片段 {frag}"
    # OSM 家族的 <img> 瓦片合成路已随「只留高德」退役, 不许回潮
    assert "img.leaflet-tile" not in html
    # 存储分平台: 苹果触屏没有直写相册的 API, 只能拉系统分享单点「存储
    # 视频」; 其余平台 (安卓/桌面) <a download> 直接落盘, 不弹面板
    # (安卓的下载视频进相册)。按钮按 share 存在性给文案。
    assert '$("#rec-save").hidden = false;' in html
    assert '$("#rec-save").textContent = shareOK ? "存到相册" : "保存视频";' in html
    assert 'const shareOK = typeof navigator.share === "function";' in html
    assert "const IS_APPLE_TOUCH" in html
    assert "navigator.maxTouchPoints > 1" in html   # iPadOS 13+ 装成 Mac
    assert '!IS_APPLE_TOUCH || typeof navigator.share !== "function"' in html
    assert 'toast(/android/i.test(navigator.userAgent) ? "已保存到相册" : "视频已保存")' in html
    assert 'function saveVideoFile()' in html
    assert "a.download = recFile.name;" in html
    assert "rec-hint" not in html   # 提示行已按用户要求撤掉, 别回潮
    # WebGL 缓冲补丁收进适配层顶层 (脚本一执行就装, 任何视图建图之前);
    # 适配层在引用序上必须先于视图脚本 (上下文属性建时即定, 晚了黑帧)
    assert html.index("function patchGLKeepBuffer()") < html.index("function ensureAMap()")
    assert "function loadAMapScript(" not in html   # 旧加载器已收编进适配层, 别回潮
    # 关弹层/换行程取消录制; 播完 1.2s (拉远定格入镜) 自动收片,
    # 且只收当次录制 (期间重开的不误杀)
    assert "if (rec) stopRecExport(true);" in html
    assert "if (rec === r) stopRecExport(false);" in html
    # 合成目的坐标先减可视区原点 (dbg90 裁切数学教训)
    assert "(sx0 - wx0) / (wr.width * kx) * out.width" in html
