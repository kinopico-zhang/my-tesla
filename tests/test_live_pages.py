"""实时驾驶页面测试: 接口鉴权, 页面骨架, 布局加固。
拆自 test_live.py (结构化重构, 代码逐字节未动)。"""


# ---------------------------------------------------------------- 鉴权 / 页面

def test_live_api_requires_login(client):
    r = client.get("/tesla/live/api/status")
    assert r.status_code == 401
    assert r.json() == {"detail": "未登录"}


def test_live_page_skeleton(auth):
    """页面骨架: 车速/时长/电量格, 状态轮询 + 轨迹刷新 (复用行程接口),
    空态 / 结束态深链 / 信号中断提示 / 高德失败降级。"""
    html = auth.get("/tesla/live").text
    # 脚本/样式拆去了 js/ 与 css/ (结构化重构): 断言用的片段全拼接进来查
    html += auth.get("/tesla/static/css/tesla-live-page.css?v=1").text
    html += auth.get("/tesla/static/css/tesla-live-driving.css?v=1").text
    html += auth.get("/tesla/static/js/live-page.js?v=1").text
    html += auth.get("/tesla/static/js/live-driving.js?v=1").text
    assert "当前驾驶 · My Tesla" in html
    for sel in ("lv-speed", "lv-elapsed", "lv-soc", "lv-range", "lv-km",
                "lv-kwh", "lv-avg", "lv-vmax"):
        assert f'id="{sel}"' in html, sel
    assert '"/tesla/live/api/status"' in html
    assert "POLL_MS = 5000" in html
    assert '"/tesla/trips/api/" + driveId + "/track"' in html
    assert "当前没有进行中的驾驶" in html
    assert "本次驾驶已结束" in html
    assert '"/tesla/trips?id=" + doneId' in html
    assert "信号可能中断" in html
    assert "地图暂不可用" in html
    assert "car-dot" in html
    # 实时数字定宽盒: 位数变化 (9→105 / 59:59→1:00:00) 不推动布局
    assert "min-width: 3ch" in html and "min-width: 7ch" in html
    assert '<span class="n">' in html
    assert "cur && cur.driving" in html   # 地图异步就位后补画车点/轨迹
    # 地图样式走 config (设置页可换), 不再写死幻影黑
    assert 'mapStyle: cfg.style || "amap://styles/dark"' in html
    # "©…auto navi" 版权文字按需求去掉
    assert '#map .amap-copyright { display: none !important; }' in html
    # 地名首帧竞态: 样式数据异步加载, complete 后延时补重渲染才有地名
    assert 'map.setFeatures(map.getFeatures())' in html
    assert "s.soc > 50" in html and "#32d74b" in html


def test_live_page_layout_bombproof(auth):
    """真机排版修复 (2026-09-13 用户报告): 速度+单位 flex 不换行 / 右列可收缩 /
    数据格 2×2 防溢出; 历史轨迹速度着色 + 末端连线接车点。"""
    html = auth.get("/tesla/live").text
    html += auth.get("/tesla/static/css/tesla-live-page.css?v=1").text
    html += auth.get("/tesla/static/css/tesla-live-driving.css?v=1").text
    js = "".join(auth.get(f"/tesla/static/js/{name}").text for name in
                 ("live-page.js", "live-driving.js"))
    # 速度大数字与单位: flex 行内永不换行 (窄屏/页缩放挤压时单位曾掉到第二行)
    assert "display: flex; align-items: baseline; white-space: nowrap;" in html
    # 右列可收缩, 出发行超宽省略号, 不再死宽抢速度区
    assert "flex-shrink: 1; min-width: 0; text-align: right; display: grid;" in html
    assert "text-overflow: ellipsis" in html
    # 数据格 2×2: 四格一行窄屏放不下会溢出圆角框
    assert "flex-wrap: wrap" in html and "flex: 1 1 calc(50% - 5px);" in html
    # 已行驶按服务器时钟走 (now_utc 校偏差), 手机时钟不准不再是 0:00
    assert "let serverSkew = 0;" in js
    assert "if (s.now_utc != null) serverSkew = s.now_utc - Date.now() / 1000;" in js
    assert "Date.now() / 1000 + serverSkew - s.started_utc" in js
    # 历史轨迹: 速度着色 (行程回放同套色阶) + 末端连线接到车当前位置
    assert '<script src="/tesla/static/js/trackutil.js?v=1"></script>' in html
    assert "TrackUtil.speedLines(t.pts)" in js
    assert "TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(" in js
    assert "tailLine.setPath([trackEnd, p])" in js
    assert 'strokeColor: "#3987e5"' not in js   # 纯蓝轨迹不许回来
