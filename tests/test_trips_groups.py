"""轨迹分组测试: 分组存取改名删除, 跨度, 校验; 页面分组入口 /
过路费工具 / 司机选择 / 导出视频。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime, timedelta
from app.tesla.models import Drive
from tests.seed_factories import seed_drive

from tests.trips_page_assets import _trips_scripts

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
    assert g["span"] == "2026-05-01~2026-05-03"   # 最早~最晚出发日

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
    assert r.json()["span"] == "2026-05-01"
    assert r.json()["km"] == 3.3


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


def test_trips_page_has_toll_tools(auth):
    """高速费: 打开行程自动估价 + 弹层 chip (批量入口/面板已按需求撤掉)。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ['id="sh-toll"', "function calcTripToll(", "function autoCalcToll(",
                 "TOLL_WAYPOINTS", "/toll`", "无高速费"]:
        assert frag in html, f"行程页缺少高速费片段 {frag}"
    # 批量入口已撤: 按钮和面板不应再出现
    assert 'id="toll-btn"' not in html
    assert 'id="tollpanel"' not in html


def test_trips_page_has_driver_picker(auth):
    """行程页驾驶员标注: 弹层选择行 + 卡片 pill + 标注接口都挂在页面上。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ['id="sh-drv"', 'id="sh-drv-sel"', "setupDriverPicker",
                 'class="ct-drv${it.driver_id != null ? "" : " def"}"',
                 ".ct-drv.def", "/tesla/api/drivers",
                 "function postJSON(", "已标注为", "已清除标注"]:
        assert frag in html, f"行程页缺少驾驶员标注片段 {frag}"
    # 卡片 pill 默认驾驶员兜底也显示 (弱化 .def 与显式标注区分)
    # 没配驾驶员时选择器藏 (兜底, 不会闪一个空下拉); 选择器和高速费 chip 都藏才整行藏
    assert "driversCache.length > 0) {" in html
    assert "function metaRowSync()" in html


def test_trips_page_group_create_and_groups_page_link(auth):
    """分组管理已搬去独立分组页 (/tesla/groups), 行程页只留创建入口:
    多选 → 存为分组; 分组面板 (入口按钮/CSS/DOM) 不许回来。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ['id="gp-btn"', "存为分组", 'id="gp-name"', 'id="gp-save"',
                 "api/groups", "function toast(", 'id="toast"',
                 "$(\"#sel-go\").addEventListener"]:
        assert frag in html, f"行程页缺少分组片段 {frag}"
    # 分组页跳来 = ?ids= 逗号深链 → openMerged (openByKey 转发)
    assert "/[-,]/.test(key)" in html
    # 旧分组面板的三件套 (头部按钮 / 面板样式 / 面板 DOM) 全删
    assert 'id="groups-btn"' not in html
    assert 'id="gpanel"' not in html and ".gpanel" not in html
    assert 'id="gp-close"' not in html and "closeGroups" not in html
    # 关弹层: 分组页跳来的深链回分组页, 分享直开只抹行程参数
    assert 'document.referrer.endsWith("/tesla/groups")' in html
    assert "if (cameFromGroups) { history.back(); return; }" in html
def test_trips_page_export_video(auth):
    """导出视频: 播放条录制钮 + 成片预览弹层 + 存相册链路都挂在页面上。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ['id="pb-rec"', 'aria-label="导出视频"', 'id="rec-modal"',
                 'id="rec-video"', 'id="rec-save"', 'id="rec-close"',
                 "playsinline", "存到相册", "function recMime(",
                 "function recCompose(", "function startRecExport(",
                 "function stopRecExport(", "function recShowResult(",
                 "function recCloseModal(", "out.captureStream(30)",
                 "new MediaRecorder(", "videoBitsPerSecond: 6e6",
                 "navigator.share({ files: [recFile]", "anim.restart();",
                 "preserveDrawingBuffer: true", "patchGLKeepBuffer();",
                 "此浏览器不支持录制视频", "录制失败 (没有内容)"]:
        assert frag in html, f"行程页缺少导出视频片段 {frag}"
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
    # WebGL 缓冲补丁必须装在高德脚本加载之前 (上下文属性建时即定,
    # 晚了就是黑帧); 补丁本体定义在 loader 前面
    assert html.index("function patchGLKeepBuffer()") < html.index("function loadAMapScript(")
    # 关弹层/换行程取消录制; 播完 1.2s (拉远定格入镜) 自动收片,
    # 且只收当次录制 (期间重开的不误杀)
    assert "if (rec) stopRecExport(true);" in html
    assert "if (rec === r) stopRecExport(false);" in html
    # 合成目的坐标先减可视区原点 (dbg90 裁切数学教训)
    assert "(sx0 - wx0) / (wr.width * kx) * out.width" in html
