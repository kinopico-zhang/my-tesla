"""浏览器缓存测试 (2026-09-25 用户点名「每次打开轨迹都要加载轨迹加载地图,
很慢, 要充分利用浏览器的缓存」): 已结束行程的 positions 在 TeslaMate 里
不可变, 轨迹类接口 (单条/合并整包/轻量汇总/NDJSON 流/直方图) 挂 ETag +
private, no-cache —— 每次打开都重校验 (校验只是一次 SELECT max(id)),
If-None-Match 命中 304, 几百 KB 的轨迹不再每次重下; 变更分量只有补路
(fills_version = track_fills 最大行号) 和载荷算法 (_ETAG_SALT)。

配套: 账号中间件对 API 默认 no-store、静态默认 no-cache —— 接口自带的
Cache-Control 豁免不被盖掉; 带 ?v=N 的静态资源 (HTML 版本串, 门禁钉死)
改发 immutable 长缓存; 客户端 getJSON 不再强制 no-store (策略交给服务端);
矢量扫路同一走廊一个页面会话只扫一遍 (tripMap 与瓦片缓存跨弹层存续)。"""
from datetime import datetime, timedelta

from app.tesla.models import Drive, TrackFill
from tests.seed_factories import seed_addresses, seed_drive, seed_positions


def _seed_two_drives(db):
    """两条带采样的已结束行程: 单条/合并/流式/汇总/直方图五个接口全吃得下
    (直方图要有速度/功耗采样才有数)。"""
    seed_addresses(db)
    t0 = datetime(2026, 9, 10, 0, 32)
    for did, hour in ((11, 0), (12, 3)):
        seed_drive(db, id=did, distance=1.2, duration_min=1,
                   start_date=t0 + timedelta(hours=hour),
                   end_date=t0 + timedelta(hours=hour, minutes=1))
        seed_positions(db, did, [
            {"date": t0 + timedelta(hours=hour, seconds=i * 10),
             "longitude": 114.05 + i * 1e-4, "latitude": 22.55,
             "speed": 82.0, "power": 15.0, "elevation": 100.0}
            for i in range(5)])


def test_track_endpoints_serve_etag_and_304(auth, db):
    """五个轨迹接口首回 200 带 ETag, 同一 ETag 重校验 304 空体 —— 不重算
    轨迹 (merged_stream 连头部查询都省), Cache-Control 是接口自己的
    private, no-cache (没被中间件的 API no-store 盖掉)。"""
    _seed_two_drives(db)
    for url in (
        "/tesla/trips/api/11/track",
        "/tesla/trips/api/merged?ids=11,12",
        "/tesla/trips/api/merged_summary?ids=11,12",
        "/tesla/trips/api/merged_stream?ids=11,12",
        "/tesla/trips/api/hist?ids=11,12",
    ):
        r = auth.get(url)
        assert r.status_code == 200, url
        assert r.headers["cache-control"] == "private, no-cache", url
        etag = r.headers["etag"]
        assert etag.startswith('"t1-'), url
        again = auth.get(url, headers={"If-None-Match": etag})
        assert again.status_code == 304, url
        assert again.headers["etag"] == etag
        assert again.headers["cache-control"] == "private, no-cache", url
        assert not again.content, url          # 304 不带响应体


def test_track_etag_bumps_with_fills_but_hist_does_not(auth, db, owndb):
    """补路落库 = 轨迹载荷真的会变 → fills_version 涨, 旧 ETag 不再命中
    (全量重下一次); 直方图在原始采样上聚合、补点不是采样, ETag 不带
    fills 分量 → 补路后照旧 304。path 空折线不进载荷, 隔离出版本号本身。"""
    _seed_two_drives(db)
    e_track = auth.get("/tesla/trips/api/11/track").headers["etag"]
    e_hist = auth.get("/tesla/trips/api/hist?ids=11,12").headers["etag"]
    owndb.add(TrackFill(drive_id=11, a_pos_id=1, b_pos_id=2, path="[]",
                        km=0.1, source="amap"))
    owndb.commit()
    r = auth.get("/tesla/trips/api/11/track", headers={"If-None-Match": e_track})
    assert r.status_code == 200                # 版本变了: 旧的不再命中
    assert r.headers["etag"] != e_track
    assert auth.get("/tesla/trips/api/hist?ids=11,12",
                    headers={"If-None-Match": e_hist}).status_code == 304


def test_open_drive_track_served_fresh_not_304(auth, db):
    """进行中的行程不走协商缓存 (2026-09-27 用户实报: 状态页驾驶态轨迹追
    不上车 —— ETag 分量只有 盐值/id/补路版本, 开放行程 positions 一直在长
    ETag 却冻着不变, 20s 重拉全被 304 成打开时刻的旧缓存, 轨迹终点与车位
    之间被尾巴线拉成一条直线)。开放行程不带 ETag (API 默认 no-store, 每
    拉全量); 行程一关闭 positions 不可变, ETag 照常生效。"""
    seed_addresses(db)
    t0 = datetime(2026, 9, 10, 8, 0)
    seed_drive(db, id=31, distance=None, duration_min=None,
               start_date=t0, end_date=None)
    seed_positions(db, 31, [
        {"date": t0 + timedelta(seconds=i * 10), "longitude": 114.05 + i * 1e-4,
         "latitude": 22.55, "speed": 30.0} for i in range(3)])
    url = "/tesla/trips/api/31/track"
    r = auth.get(url)
    assert r.status_code == 200
    assert "etag" not in r.headers            # 没有协商缓存的把手
    assert r.headers["cache-control"] == "no-store"
    # 行程继续采样: 再拉必须带上新点 (带着 If-None-Match 也不许 304)
    seed_positions(db, 31, [{"date": t0 + timedelta(seconds=35),
                             "longitude": 114.0531, "latitude": 22.55,
                             "speed": 30.0}])
    r2 = auth.get(url, headers={"If-None-Match": '"t1-d-anything"'})
    assert r2.status_code == 200 and len(r2.json()["pts"]) == 4
    # 行程关闭: 轨迹不可变, ETag 恢复 (重开页面命中 304)
    drive = db.get(Drive, 31)
    drive.end_date = t0 + timedelta(minutes=2)
    db.commit()
    r3 = auth.get(url)
    assert r3.status_code == 200 and r3.headers["etag"].startswith('"t1-')
    assert auth.get(url, headers={"If-None-Match": r3.headers["etag"]}) \
        .status_code == 304


def test_api_without_own_cache_control_still_no_store(auth, db):
    """没自带 Cache-Control 的 API 照旧 no-store (map config 等配置类):
    豁免只放行接口自己发了策略的 (上面五个轨迹接口)。"""
    assert auth.get("/api/me").headers["cache-control"] == "no-store"


def test_static_versioned_assets_immutable(auth):
    """静态资源带 ?v=N (HTML 里的版本串, 门禁钉死 → 同 URL 内容永不回头)
    改发 immutable 长缓存: 重开页面不再整排 304 重校验; 不带版本参数的
    照旧 no-cache 重校验。参数名要精确是 v —— ?view=1 里没有名为 v 的参数。"""
    r = auth.get("/tesla/static/js/tesla-common.js?v=5")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert auth.get("/tesla/static/js/tesla-common.js") \
        .headers["cache-control"] == "no-cache"
    assert auth.get("/tesla/static/js/tesla-common.js?view=1") \
        .headers["cache-control"] == "no-cache"


def test_getjson_leaves_caching_to_server(auth):
    """客户端 getJSON 撤掉强制的 cache: no-store —— 缓存策略听服务端的
    (轨迹接口 ETag 重校验才有的聊); 写操作 sendJSON 照旧 no-store
    (POST/PUT 的响应不该被缓存)。"""
    js = auth.get("/tesla/static/js/tesla-common.js").text
    assert "const r = await fetch(url);" in js
    assert 'Object.assign({ cache: "no-store" }, opts)' in js


def test_preload_vector_sweeps_corridor_once_per_session(auth):
    """矢量扫路同一走廊一个页面会话只扫一遍: tripMap 和它的瓦片缓存跨
    弹层存续 (closeTrip 不销毁图), 重开同一条还要再等一遍扫路 (最长 4s)
    纯属浪费 —— key (单条 = curKey, 合并流首段 = mergeKey) 记在模块里,
    命中直接跳过; 被更新的打开顶掉的扫路不算扫完 (走廊只扫了一半),
    走完主扫才记。"""
    pv = auth.get("/tesla/static/js/view/trips-preload-vector.js").text
    opn = auth.get("/tesla/static/js/view/trips-sheet-open.js").text
    assert "async function preloadVectorTrack(pts, ts, openZoom, onProgress," \
           " seq, key) {" in pv
    assert "const sweptCorridors = new Set();" in pv
    assert "if (key && sweptCorridors.has(key)) return;" in pv
    # 先有「顶掉不记」的出口, add 在它之后 (活到主扫走完才会执行到)
    assert pv.index("if (!alive()) return;   // 被更新的打开顶掉") \
        < pv.index("if (key) sweptCorridors.add(key);")
    # 两处调用都把 key 递进来 (openTrip 传 curKey, 流式首段传 mergeKey)
    assert "true), seq, curKey);" in opn
    assert "true), seq, key);" in opn
    # 版本号随改动翻新 (老缓存不掺和)
    html = auth.get("/tesla").text
    assert "js/tesla-common.js?v=5" in html
    assert "view/trips-preload-vector.js?v=3" in html
