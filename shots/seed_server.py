"""起一个「种子假数据」的 my-tesla 实例给 README 截图用 (shots/ 管线)。

uvicorn 线程起来后, 把 TeslaMate 引擎换成灌好假数据的 SQLite: 充电 ~290 条
跨 15 个月 (月度柱状图铺满 12 个月滑窗; 家充满充带额定续航采样, 331→322km
缓降当电池健康衰减曲线) + ~1000 程 / ~两万公里「一笔画」路网 (17 锚点驾车
链, 段段首尾相接, 近/中/远三档频次分层喂 log 色阶; 行程带额定续航差、
点位带电量/续航 —— 行程统计的电耗与状态页的电量续航有数据) + 双驾驶员
+ 地址坐标
(充电地图圆标) + 演示用 app_settings 行 (设置页回显), 账号库种
admin/shot-pass-123。打印 READY 后存活。

用法: .venv/bin/python shots/seed_server.py [端口]   (默认 8901)
环境: SHOTLAB 工作目录 (默认 ~/shotlab; 种子库/缓存落 SHOTLAB/tesla/)
      MYHOME_ENV 根仓 .env 路径 (取高德 Key 种进演示设置行, 默认根仓 .env)
      MYHOME_PROD_DB 生产 mytesla.db (只读取 amap_web_key 拟合道路用)
注意: 首次跑要对高德做 ~34 段驾车规划 (真实 Web 服务 Key, 几分钟 + 要网);
种子库一次成型 —— teslamate.db 已在时整库复用, 免重规划免重播种直接起服
(重建: 删 SHOTLAB 库或 SHOT_RESEED=1)。绝不动子仓 data/ 下的生产缓存
(盘缓存重定向到 SHOTLAB/tesla/)。"""
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)

LAB = Path(os.environ.get("SHOTLAB",
                        os.path.expanduser("~/shotlab")))
TMP = LAB / "tesla"
TMP.mkdir(parents=True, exist_ok=True)

ROOT_ENV_PATH = Path(os.environ.get(
    "MYHOME_ENV", REPO.parent.parent / ".env"))   # 默认组合仓根的 .env
ROOT_ENV = {}
if ROOT_ENV_PATH.exists():
    for line in ROOT_ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            ROOT_ENV[k.strip()] = v.strip()

os.environ.update({
    "MYHOME_USERS_DB": str(TMP / "users.db"),
    "MYHOME_SECRET_FILE": str(TMP / "secret"),
    "MYTESLA_DB": f"sqlite:///{(TMP / 'mytesla.db').as_posix()}",
    # 盘缓存重定向到 /tmp: 绝不碰子仓 data/ 下的生产缓存
    "MAP_CACHE_FILE": str(TMP / "tracks_cache.json"),
    "SPEED_HIST_CACHE_FILE": str(TMP / "speed_hist_cache.json"),
    # TeslaMate 演示观感值 (引擎随后被换成种子 SQLite, 这几个只是设置页回显)
    "TMDB_HOST": "192.168.31.5", "TMDB_PORT": "5432",
    "TMDB_USER": "teslamate", "TMDB_PASS": "demo-pass-2026",
    "TMDB_NAME": "teslamate",
})

import uvicorn  # noqa: E402
from app import account_store, database, main as app_main  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8901

server = uvicorn.Server(uvicorn.Config(
    app_main.app, host="127.0.0.1", port=PORT, log_level="warning"))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
while not server.started:
    time.sleep(0.1)

# 账号库种 admin (lifespan 只建表不种账号 —— 引导归 /setup, 截图要现成登录;
# 高德 Key 同理不再走 env, 下面种进演示 app_settings 行)
with database.users_session_factory()() as users:  # pylint: disable=not-callable
    account_store.ensure_admin(users, "admin", "shot-pass-123")

# ---- 引擎换成种子 SQLite (lifespan 已按 env 建好库表, 这里只换镜像库) ----
from app.tesla.models.teslamate_tables import Base  # noqa: E402

DB_PATH = TMP / "teslamate.db"
DB = f"sqlite:///{DB_PATH.as_posix()}"
RESEED = bool(os.environ.get("SHOT_RESEED")) or not DB_PATH.exists()
database.init_engine(DB)
Base.metadata.create_all(database.engine())

if not RESEED:
    # 种子库一次成型, 整库复用 (2026-10-09 用户点名「搞一个虚假的
    # teslamate db, 每次都用这个截图」): 已在时免重规划免重播种直接起服;
    # 重建 = 删 $SHOTLAB/tesla/teslamate.db (连 mytesla/users 一起) 或
    # SHOT_RESEED=1 重来
    print(f"种子库已就位 {DB_PATH}, 免重播种直接起服 "
          "(重建: 删 SHOTLAB 库或 SHOT_RESEED=1)", flush=True)
    print("READY", flush=True)
    while thread.is_alive():
        time.sleep(1)
    raise SystemExit(0)

from tests.seed_factories import (  # noqa: E402
    seed_car, seed_charge, seed_charging, seed_drive, seed_positions)

# ---- 锚点: 名称 → (坐标, 地址 id) —— 城市级演示坐标, 非真实点位 ----
A = {
    "home":      ((113.9436, 22.5278), 1),   # 南山 家充桩
    "huawei":    ((114.0645, 22.6370), 2),   # 坂田 华为立体车库
    "qiaoxiang": ((114.0287, 22.5538), 3),   # 福田 侨香超充站
    "mixc":      ((114.1187, 22.5435), 4),   # 罗湖 万象城超充
    "changan":   ((113.8456, 22.5871), 5),   # 东莞 长安服务区
    "tianhe":    ((113.3235, 23.1354), 6),   # 广州 天河体育中心
    "sznorth":   ((114.0286, 22.6108), 7),   # 深圳北站
    "airport":   ((113.8110, 22.6390), 8),   # 宝安机场
    "qianhai":   ((113.8850, 22.5240), 9),   # 前海
    "longhua":   ((114.0364, 22.6560), 10),  # 龙华
    "xili":      ((113.9660, 22.5900), 11),  # 西丽
    "guangming": ((113.9350, 22.7600), 12),  # 光明
    "kouan":     ((114.0670, 22.5210), 13),  # 福田口岸
    "dameisha":  ((114.2652, 22.5946), 14),  # 大梅沙
    "pingshan":  ((114.3500, 22.6900), 15),  # 坪山
    "sshu":      ((113.8760, 22.9130), 16),  # 东莞 松山湖
    "humen":     ((113.6720, 22.8140), 17),  # 虎门
    "huizhou":   ((114.4126, 23.0896), 18),  # 惠州西湖
}

with database.session_factory()() as db:  # pylint: disable=not-callable
    seed_car(db)
    # 地址: 18 个走廊锚点 (名称/城市/display_name, 省市区供区域筛选解析;
    # 坐标 = 充电地图圆标定位, 无坐标的地址不上图)
    from app.tesla.models.teslamate_tables import Address
    db.add_all([
        Address(id=1, name="家充桩", city="深圳市",
                display_name="广东省深圳市南山区粤海街道",
                latitude=A["home"][0][1], longitude=A["home"][0][0]),
        Address(id=2, name="华为立体车库", city="深圳市",
                display_name="广东省深圳市龙岗区坂田街道",
                latitude=A["huawei"][0][1], longitude=A["huawei"][0][0]),
        Address(id=3, name="侨香超充站", city="深圳市",
                display_name="广东省深圳市福田区香蜜湖街道",
                latitude=A["qiaoxiang"][0][1], longitude=A["qiaoxiang"][0][0]),
        Address(id=4, name="万象城超充", city="深圳市",
                display_name="广东省深圳市罗湖区桂园街道",
                latitude=A["mixc"][0][1], longitude=A["mixc"][0][0]),
        Address(id=5, name="长安服务区充电", city="东莞市",
                display_name="广东省东莞市长安镇",
                latitude=A["changan"][0][1], longitude=A["changan"][0][0]),
        Address(id=6, name="天河体育中心超充", city="广州市",
                display_name="广东省广州市天河区天河路",
                latitude=A["tianhe"][0][1], longitude=A["tianhe"][0][0]),
        Address(id=7, name="深圳北站P1", city="深圳市",
                display_name="广东省深圳市龙华区民治街道",
                latitude=A["sznorth"][0][1], longitude=A["sznorth"][0][0]),
        Address(id=8, name="宝安机场枢纽", city="深圳市",
                display_name="广东省深圳市宝安区宝安机场",
                latitude=A["airport"][0][1], longitude=A["airport"][0][0]),
        Address(id=9, name="前海万象汇", city="深圳市",
                display_name="广东省深圳市南山区前湾",
                latitude=A["qianhai"][0][1], longitude=A["qianhai"][0][0]),
        Address(id=10, name="龙华壹方天地", city="深圳市",
                display_name="广东省深圳市龙华区人民路",
                latitude=A["longhua"][0][1], longitude=A["longhua"][0][0]),
        Address(id=11, name="西丽万象天地", city="深圳市",
                display_name="广东省深圳市南山区西丽街道",
                latitude=A["xili"][0][1], longitude=A["xili"][0][0]),
        Address(id=12, name="光明虹桥公园", city="深圳市",
                display_name="广东省深圳市光明区光明街道",
                latitude=A["guangming"][0][1], longitude=A["guangming"][0][0]),
        Address(id=13, name="福田口岸枢纽", city="深圳市",
                display_name="广东省深圳市福田区裕亨路",
                latitude=A["kouan"][0][1], longitude=A["kouan"][0][0]),
        Address(id=14, name="大梅沙海滨公园", city="深圳市",
                display_name="广东省深圳市盐田区梅沙街道",
                latitude=A["dameisha"][0][1], longitude=A["dameisha"][0][0]),
        Address(id=15, name="坪山燕子湖", city="深圳市",
                display_name="广东省深圳市坪山区坪山街道",
                latitude=A["pingshan"][0][1], longitude=A["pingshan"][0][0]),
        Address(id=16, name="松山湖总部", city="东莞市",
                display_name="广东省东莞市松山湖高新区",
                latitude=A["sshu"][0][1], longitude=A["sshu"][0][0]),
        Address(id=17, name="虎门高铁站", city="东莞市",
                display_name="广东省东莞市虎门镇",
                latitude=A["humen"][0][1], longitude=A["humen"][0][0]),
        Address(id=18, name="惠州西湖", city="惠州市",
                display_name="广东省惠州市惠城区西湖",
                latitude=A["huizhou"][0][1], longitude=A["huizhou"][0][0]),
    ])
    db.commit()

    # ---- 充电记录: 2025-08 起 15 个月 (近 4 周手排 22 条 + 历史段程序化) ----
    # 历史段 8 天一循环 5 充 (隔两循环加一充): 家充满充 + 超充 + 家充部分充
    # + 第三方快充 + 家充部分充 —— 月度柱状图铺满前端 12 个月滑窗
    # (2026-10-09 用户点名「最起码要 12 个」)。家充满充是电池健康页的唯一
    # 数据源 (只采结尾 100% 的过程, 同日用户点名「电池健康度截图没有数据」):
    # 每 10% 一个采样带额定续航, 满充额定 331.5km 线性缓降 ~3%/14 个月当
    # 衰减曲线; 近 4 周保持手排 (列表页观感不动), 其中两条家充同样升满
    # 100% 把曲线接到「现在」。
    now = datetime(2026, 10, 7, 6, 0)   # UTC 口径 (库里是 UTC)
    plan = [  # (天前, 小时, 分钟, addr, 快充, kWh, cost, 起止电量) —— 近 4 周
        (1, 1, 10, 1, False, 41.2, 14.8, (32, 88)),
        (2, 16, 40, 3, True, 32.5, 48.2, (18, 70)),
        (3, 22, 5, 1, False, 38.0, 13.7, (28, 84)),
        (4, 12, 30, 4, True, 45.6, 71.1, (12, 82)),
        (5, 19, 50, 1, False, 33.1, 11.9, (55, 100)),   # 满充 → 电池健康
        (7, 3, 15, 5, True, 28.3, 41.6, (25, 66)),
        (8, 21, 30, 1, False, 40.9, 14.7, (30, 87)),
        (9, 13, 45, 3, True, 36.8, 54.3, (15, 72)),
        (10, 20, 10, 1, False, 29.4, 10.6, (60, 100)),  # 满充 → 电池健康
        (12, 9, 25, 4, True, 48.2, 74.9, (8, 85)),
        (13, 17, 55, 1, False, 35.6, 12.8, (35, 86)),
        (14, 23, 40, 6, True, 30.1, 46.7, (22, 65)),
        (16, 2, 20, 1, False, 42.3, 15.2, (26, 89)),
        (17, 14, 5, 3, True, 25.9, 38.8, (30, 62)),
        (18, 18, 35, 1, False, 20.5, 7.4, (58, 90)),
        (20, 8, 50, 4, True, 44.7, 69.8, (10, 80)),
        (22, 4, 15, 5, True, 33.4, 49.2, (24, 71)),
        (23, 21, 5, 1, False, 39.8, 14.3, (29, 88)),
        (25, 11, 40, 3, True, 27.6, 40.9, (33, 64)),
        (27, 19, 25, 1, False, 36.2, 13.0, (32, 87)),
        (29, 15, 55, 6, True, 42.8, 66.4, (14, 83)),
        (31, 5, 45, 1, False, 31.5, 11.3, (40, 90)),
    ]

    def full_rated(day):
        """当天的满充额定续航 km (100% 表显): 331.5 线性缓降, 14 个月 ~3%。"""
        return 331.5 - (day - datetime(2025, 8, 12)).days * 0.0225

    def at(base, d, h, m):
        return base.replace(hour=h, minute=m) + timedelta(days=d)

    hist = []                     # (start, addr, 快充, b0, b1)
    day = datetime(2025, 8, 12)   # 与行程时间链同期起步; 止于手排版前一循环
    cyc = 0
    while day <= now - timedelta(days=39):
        cyc += 1
        hist += [
            (at(day, 0, 12 + cyc % 4, 25), 1, False, 34 + cyc % 5, 100),
            (at(day, 1, 2 + cyc % 7, 40), (3, 4, 6)[cyc % 3], True,
             18 + cyc % 5, 62 + cyc % 4),
            (at(day, 3, 14 + cyc % 5, 10), 1, False, 44 + cyc % 6, 82 + cyc % 5),
            (at(day, 5, 1 + cyc % 6, 5), 5 if cyc % 2 else 6, True,
             26 + cyc % 7, 70 + cyc % 6),
            (at(day, 7, 19 + cyc % 5, 30), 1, False, 52 + cyc % 4, 90),
        ]
        if cyc % 3 == 0:          # 隔两循环加一充, 月度柱状图高矮错落
            hist.append((at(day, 6, 11 + cyc % 3, 45), 4, True,
                         14 + cyc % 3, 58))
        day += timedelta(days=8)

    def fill(start, addr, fast, b0, b1):
        """历史条目补 kWh/费用: ~0.74 kWh/% + 家充 0.36 / 快充 1.45 ¥/kWh。"""
        kwh = round((b1 - b0) * 0.74, 1)
        return (start, addr, fast, kwh,
                round(kwh * (1.45 if fast else 0.36), 1), b0, b1)

    rows = [[(now - timedelta(days=d)).replace(hour=h, minute=m),
             addr, fast, kwh, cost, b0, b1]
            for d, h, m, addr, fast, kwh, cost, (b0, b1) in plan]
    rows += [fill(*h) for h in hist]

    pid = 0
    for start, addr, fast, kwh, cost, b0, b1 in rows:
        pid += 1
        dur = int(kwh / (90.0 if fast else 11.0) * 60) + 20
        k_pct = full_rated(start) / 100.0     # 当日额定续航系数 (km/1%)
        proc = seed_charging(
            db, id=pid, car_id=1, start_date=start,
            end_date=start + timedelta(minutes=dur), address_id=addr,
            start_battery_level=b0, end_battery_level=b1,
            charge_energy_added=kwh, charge_energy_used=round(kwh * 1.07, 1),
            duration_min=dur, cost=cost, outside_temp_avg=27.5,
            start_rated_range_km=round(b0 * k_pct, 1),
            end_rated_range_km=round(b1 * k_pct, 1))
        if b1 == 100:
            # 满充: 每 10% 一个采样, 额定续航 + 可用电量齐 (电池健康页的料);
            # 采样间 ±0.4% 抖动让曲线不那么机械
            levels = list(range(b0, 100, 10))
            levels.append(100)
            for j, lv in enumerate(levels):
                frac = j / (len(levels) - 1)
                seed_charge(
                    db, proc.id,
                    date=start + timedelta(minutes=5 + (dur - 10) * frac),
                    battery_level=lv, usable_battery_level=lv,
                    rated_battery_range_km=round(
                        lv * k_pct * (1 + 0.004 * (j % 3 - 1)), 1),
                    charger_power=11.0, charger_voltage=220.0,
                    charger_actual_current=50.0, conn_charge_cable="CCS",
                    fast_charger_brand="<invalid>", fast_charger_type="Gb",
                    fast_charger_present=False)
            continue
        seed_charge(db, proc.id, date=start + timedelta(minutes=5),
                    battery_level=b0, charger_power=95.0 if fast else 11.0,
                    charger_voltage=400.0 if fast else 220.0,
                    charger_actual_current=235.0 if fast else 50.0,
                    conn_charge_cable="CCS",
                    fast_charger_brand="Tesla" if addr in (3, 4, 5, 6) else "<invalid>",
                    fast_charger_type="Gb",
                    fast_charger_present=fast)

    # ---- 行程: ~2 万公里「一笔画」路网 (2026-10-08 用户点名「路径要能一
    # 笔画完, 车不能跳跃」+「常去/不常去用颜色区分」) ----
    # 每轮从家出发: 近点×6 + 中频点×1 各一趟往返 (家→X→家 链式相接),
    # 远途点每 4 轮附一个 —— 段段首尾相接 (上一段终点 = 下一段起点,
    # assert 兜底), 轮与轮之间停在家, 全部轨迹连成一张网, 车从未跳跃。
    # 趟数分层喂 log 色阶: 近点走廊 ~120 趟 (金/红)、中频 ~28 趟 (青)、
    # 远途 ~7 趟 (蓝) —— 常走与偶走在色阶上拉开。走廊几何来自驾车规划,
    # DriveRoad 直接落行 (status ok, v3), 不逐程 grasproad。
    import sqlite3  # noqa: E402  (S408: 只读生产库取 amap_web_key)
    prod_db = os.environ.get(
        "MYHOME_PROD_DB", str(REPO.parent.parent / "data" / "mytesla.db"))
    proot = sqlite3.connect(f"file:{prod_db}?mode=ro", uri=True)
    web_key = (proot.execute(
        "select amap_web_key from app_settings limit 1").fetchone() or [""])[0]
    proot.close()
    assert web_key, "生产 app_settings 无 amap_web_key (MYHOME_PROD_DB 指对了吗)"
    from app.tesla import roads_amap, roads_fit  # noqa: E402
    from app.tesla.repository import map_roads as roads_repo  # noqa: E402
    from app.tesla.roads_geom import wgs_km  # noqa: E402
    client = roads_amap.AmapClient(web_key, min_interval=0.4)

    def route_retry(a, b):
        """规划偶发 SSL 握手超时 —— 指数退避重试, 断点不丢整轮。"""
        for i in range(5):
            try:
                return client.route(a, b)
            except Exception as exc:           # pylint: disable=broad-except
                print(f"  route retry {i + 1} {a}->{b}: {exc}", flush=True)
                time.sleep(3 + i * 4)
        raise RuntimeError(f"驾车规划 5 次失败: {a}->{b}")

    def resample(route_pts, step_km=0.1):
        """路网折线 → 等距重采样 (~100m 一点, 20 万点规模的密度来源)。
        首尾点原样保留 —— 链式相接靠锚点坐标精确相等。"""
        out = [route_pts[0]]
        carry = 0.0                       # 距上一个已发点的弧长
        for i in range(1, len(route_pts)):
            a, b = route_pts[i - 1], route_pts[i]
            seg = wgs_km(a, b)
            pos = 0.0                     # 当前段内已走弧长
            while carry + (seg - pos) >= step_km:
                pos += step_km - carry
                f = pos / seg if seg else 0.0
                out.append((a[0] + (b[0] - a[0]) * f,
                            a[1] + (b[1] - a[1]) * f))
                carry = 0.0
            carry += seg - pos
        if wgs_km(out[-1], route_pts[-1]) > step_km / 2:
            out.append(route_pts[-1])
        else:
            out[-1] = route_pts[-1]
        return out

    near = ["xili", "qianhai", "qiaoxiang", "mixc",
            "kouan", "sznorth", "longhua"]
    mid = ["dameisha", "pingshan", "guangming", "airport", "huawei"]
    far = ["tianhe", "huizhou", "humen", "sshu", "changan"]

    def tier(x):
        return "near" if x in near else "mid" if x in mid else "far"

    legs = {}                        # (a, b) → (等距点, 累计弧长表, km)
    for x in near + mid + far:
        for ka, kb in (("home", x), (x, "home")):
            rts = route_retry(A[ka][0], A[kb][0])
            assert rts and len(rts) >= 2, f"驾车规划失败: {ka}->{kb}"
            rts[0], rts[-1] = A[ka][0], A[kb][0]   # 规划起终点是道路吸附
            # 点, 与锚点差几十米 —— 首尾强制回锚点, 链式相接 (相邻程
            # 坐标精确相等) 才成立; 锚点到路网的短直线语义也正确
            pts = resample(rts)
            cum = [0.0]
            for i in range(1, len(pts)):
                cum.append(cum[-1] + wgs_km(pts[i - 1], pts[i]))
            legs[(ka, kb)] = (pts, cum, cum[-1])
            print(f"leg {ka}->{kb}: {cum[-1]:.1f}km {len(pts)}pts", flush=True)

    def round_legs(r):
        """第 r 轮的段序列: 近点 6 个 (跳过 near[(r+6)%7], 轮转均衡)、
        中频 1 个 ((r*3)%5)、远途 (r%4==2) 1 个 ((r//4)%5)。"""
        seq = []
        for i in range(6):
            x = near[(r + i) % 7]
            seq += [("home", x), (x, "home")]
        x = mid[(r * 3) % 5]
        seq += [("home", x), (x, "home")]
        if r % 4 == 2:
            x = far[(r // 4) % 5]
            seq += [("home", x), (x, "home")]
        return seq

    # 轮数按里程目标定 (~19.5k km 落地): 预估/实际比 ~0.91 (轮转选点
    # 方差), 目标按 21500 抬一成。前 4 轮均值 (含一个远途轮)
    per = sum(sum(legs[s][2] for s in round_legs(r)) for r in range(4)) / 4
    R = max(24, round(21500 / per))
    print(f"rounds: {R} (~{per:.0f}km/轮)", flush=True)

    # 时间链: 段后停留按档 (近 1-3h / 中 3-6h / 远 5-9h, did 抖动); 轮间
    # gap 把 (t0..T_END) 余量均摊。速度按走廊长度分档 (远途快/市区慢)。
    t0 = datetime(2025, 8, 5, 0, 35)       # UTC 库口径
    T_END = datetime(2026, 10, 6, 20, 0)
    DWELL = {"near": (1.0, 3.0), "mid": (3.0, 6.0), "far": (5.0, 9.0)}

    def drive_hours(km):
        return km / (75.0 if km > 60 else 55.0 if km > 25 else 38.0)

    est = 0.0
    for r in range(4):
        for ka, kb in round_legs(r):
            est += drive_hours(legs[(ka, kb)][2]) + sum(DWELL[tier(kb)]) / 2
    gap_round = max(2 * 24.0, ((T_END - t0).total_seconds() / 3600
                               - est / 4 * R) / R)     # 小时

    roads_rows = []                        # DriveRoad 行攒批落库
    did = 0
    t = t0
    prev_last = None                       # 一笔画断言: 上一程末点
    for r in range(R):
        seq = round_legs(r)
        for si, (ka, kb) in enumerate(seq):
            did += 1
            pts, cum, km = legs[(ka, kb)]
            assert prev_last is None or \
                (pts[0][0], pts[0][1]) == prev_last, f"轨迹跳跃 @{did}"
            prev_last = (pts[-1][0], pts[-1][1])
            speed = 75.0 if km > 60 else 55.0 if km > 25 else \
                38.0 + (did % 4) * 2.0
            dur_min = max(1, round(km / speed * 60))
            start = t
            # 额定续航差 → 行程电耗 (额定续航差 × 桩端定标; 2026-10-09 用户
            # 点名「行程统计的平均电耗和总电耗是空的」): 续航掉得比里程略多
            # (±4% 抖动), 起续航 150–310km 轮转 —— 段间停留当补过电
            k_pct = full_rated(start) / 100.0
            drop = km * (1.0 + ((did % 5) - 2) * 0.02)
            rated0 = 150.0 + (did * 37) % 160
            rated1 = max(40.0, rated0 - drop)
            lv0, lv1 = rated0 / k_pct, rated1 / k_pct   # 对应电量 %
            rows = []
            tt = start
            for i, (lon, lat) in enumerate(pts):
                if i:
                    tt += timedelta(seconds=round(
                        wgs_km(pts[i - 1], pts[i]) / speed * 3600))
                f = cum[i] / km if km else 0.0     # 沿程进度 → 电量/续航内插
                rows.append({"date": tt, "longitude": lon, "latitude": lat,
                             "speed": speed + (i % 11) * 1.2,
                             "power": 25000.0 + (i % 7) * 3000.0,
                             "battery_level": round(lv0 + (lv1 - lv0) * f),
                             "rated_battery_range_km": round(
                                 rated0 + (rated1 - rated0) * f, 1)})
            seed_drive(db, id=did, car_id=1,
                       start_date=start,
                       end_date=start + timedelta(minutes=dur_min),
                       distance=round(km, 1), duration_min=dur_min,
                       speed_max=round(speed * 1.4),
                       start_address_id=A[ka][1], end_address_id=A[kb][1],
                       start_rated_range_km=round(rated0, 1),
                       end_rated_range_km=round(rated1, 1))
            seed_positions(db, did, rows)
            roads_rows.append(roads_repo.road_row(
                did, "ok", roads_fit.ROAD_FIT_V,
                [round(v, 5) for p in pts for v in p], len(pts),
                round(km, 2), "", []))
            d_lo, d_hi = DWELL[tier(kb)]
            dwell_h = d_lo + (d_hi - d_lo) * ((did * 7) % 11) / 10
            if si == len(seq) - 1:         # 轮末回家 → 轮间 gap (±10% 抖动)
                dwell_h = gap_round * (0.9 + 0.2 * ((did * 5) % 9) / 8)
            t = start + timedelta(minutes=dur_min) + timedelta(hours=dwell_h)
        if (r + 1) % 10 == 0:
            print(f"  round {r + 1}/{R} drive {did} ({t:%m-%d %H:%M})",
                  flush=True)
    print(f"drives: {did}, road pts: {sum(x.n for x in roads_rows)}, "
          f"total: {sum(x.km for x in roads_rows):.0f}km, "
          f"链尾 {t:%Y-%m-%d}, 一笔画校验通过", flush=True)

# ---- 足迹「走过的路」+ 驾驶员 + 演示设置行: 上面的走廊行直接落库; 自有库
# 另种两位驾驶员 (爸爸默认 + 妈妈), 三分之一行程标注给妈妈 —— 左下角筛选
# chip 与司机里程分布都有数据; 行程分组种两组 (按地址走廊现查最近的程,
# 分组统计展示时按当前行程数据现算); app_settings 单行给设置页一个
# 「已配置」的回显 (TeslaMate host/账号名 + 掩码 Key, 均为演示值)。----
from sqlalchemy import or_, select  # noqa: E402

from app.tesla.models.teslamate_tables import Drive  # noqa: E402


def corridor_ids(mir, addr, n=4):
    """某地址走廊最近的 n 程 id (升序) —— 分组的 ids 串用。"""
    rows = mir.execute(select(Drive.id).where(
        or_(Drive.start_address_id == addr, Drive.end_address_id == addr))
        .order_by(Drive.start_date.desc()).limit(n)).all()
    return sorted(r[0] for r in rows)


with database.session_factory()() as mir:  # pylint: disable=not-callable
    TRIP_GROUPS = [
        ("大梅沙看海周末", corridor_ids(mir, 14)),   # 大梅沙
        ("广州出差两趟", corridor_ids(mir, 6)),      # 天河体育中心
    ]

with database.own_session_factory()() as own:  # pylint: disable=not-callable
    from app.tesla.models import Driver, TripDriver  # noqa: E402
    from app.tesla.models.mytesla_tables import (  # noqa: E402
        AppSetting, TripGroup)
    own.add_all(roads_rows)
    own.add_all([Driver(id=1, name="爸爸", is_default=True),
                 Driver(id=2, name="妈妈")])
    own.add_all([TripDriver(drive_id=i, driver_id=2)
                 for i in range(1, did + 1) if i % 3 == 0])
    own.add_all([TripGroup(id=i, name=name, ids=",".join(map(str, ids)))
                 for i, (name, ids) in enumerate(TRIP_GROUPS, 1)])
    own.merge(AppSetting(
        id=1, tmdb_host="192.168.31.5", tmdb_port="5432",
        tmdb_user="teslamate", tmdb_password="demo-pass-2026",
        tmdb_name="teslamate", amap_web_key=web_key,
        amap_key=ROOT_ENV.get("AMAP_KEY", ""),
        amap_security_code=ROOT_ENV.get("AMAP_SECURITY_CODE", "")))
    own.commit()
    print(f"own: {len(roads_rows)} roads, 2 drivers, "
          f"妈妈标注 {sum(1 for i in range(1, did + 1) if i % 3 == 0)} 程, "
          f"{len(TRIP_GROUPS)} 分组, app_settings 演示行", flush=True)

print("READY", flush=True)
while thread.is_alive():
    time.sleep(1)
