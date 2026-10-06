"""常去地点命名后台 worker (2026-10-02 用户点名「用 GPS 坐标结合高德, 不要
相信 teslamate」): TeslaMate 的地址名来自 OSM 反查, 中国覆盖稀, 三成停车点
只剩「XX街道」兜底名 —— 这里拿停车 GPS 坐标问高德逆地理, 结果写 place_names
(一次性回填几百次调用, 之后水位增量补新地址)。

节奏照 roads_worker: 每轮 ≤100 址再查, REST 节流 0.4s; 配额码歇 1 小时,
自记账日上限 3000 歇到次日零点; key 每轮现读 (换 key 不用重启, /roads/tick
会 nudge); 会话短开短闭; 境外坐标 regeo 短路不耗配额 (落 skip 行)。
网络/服务错误不落行, 同址 3 次后本进程放弃 —— 读侧没缓存自然回退
TeslaMate 名, 不会更糟。"""
# pylint: disable=duplicate-code   # _State/轮次样板与 roads_worker 有意同款
import sys
import threading
from datetime import date, datetime, time as dtime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from . import roads_amap
from .repository.place_names import (all_address_coords, done_address_ids,
                                     place_name_row, save_place_name)
from .roads_amap_wire import AmapSpot, Regeocode
from .settings_store import amap_web_key_value

PLACE_NAME_V = 1          # 取名策略版本: 阈值/优先级改了 bump 重查
CALL_CAP_PER_DAY = 3000   # 自记账日上限 (官方个人 5000, 留余量)
THROTTLE_S = 0.4          # 相邻 REST 调用最小间隔
IDLE_SLEEP_S = 60         # 空转轮询 (无 key / 无待办)
PEAK_DELAY_S = 150        # 启动错峰: 预热线程与 roads worker (90s) 先跑
ROUND_MAX = 100           # 每轮最多处理地址数 (再查待办, 不长占库)
QUOTA_PAUSE_S = 3600      # 配额码的歇时
ATTEMPTS_MAX = 3          # 同址网络/服务错误重试上限 (本进程)

_POI_MAX_M = 300.0        # POI 认定半径: 送学停校门 300m 外也是「到学校」
_ROAD_MAX_M = 100.0       # 没有近 POI 时贴路名 (停路边)


def _nearest(spots: list[AmapSpot]) -> tuple[str, float] | None:
    """列表里距离最近的一条 (pois/roads 不保证按距离排, 自己挑;
    距离缺/坏的条目跳过)。"""
    best: AmapSpot | None = None
    best_d = float("inf")
    for spot in spots:
        if spot.distance is not None and spot.distance < best_d:
            best_d, best = spot.distance, spot
    return (best.name, best_d) if best is not None else None


def pick_place_name(geo: Regeocode) -> str:
    """regeocode → 展示名: 最近的 POI ≤300m 优先, 其次 ≤100m 的道路名,
    都没有用 区+街道 兜底 (addressComponent 的空字段是 [] 不是 "", 验形时
    已收编成 "")。取不出回 "" (落 skip, 同 v 不再重试)。"""
    poi = _nearest(geo.pois)
    if poi and poi[0] and poi[1] <= _POI_MAX_M:
        return poi[0][:60]
    road = _nearest(geo.roads)
    if road and road[0] and road[1] <= _ROAD_MAX_M:
        return road[0][:60]
    return (geo.address.district + geo.address.township)[:60]


class _State:
    """模块单例 (roads_worker 同款): 测试用 reset 收线程清记账。"""

    stop = threading.Event()
    wake = threading.Event()
    thread: threading.Thread | None = None
    attempts: dict[int, int] = {}
    calls_today = 0
    day: date | None = None


def start(tesla_factory: sessionmaker[Session],
          own_factory: sessionmaker[Session]) -> None:
    """起后台线程 (幂等: 已在跑不另起); 两个工厂都是 sessionmaker。"""
    if _State.thread is not None and _State.thread.is_alive():
        return
    _State.stop.clear()
    _State.wake.clear()
    _State.thread = threading.Thread(
        target=_loop, args=(tesla_factory, own_factory),
        daemon=True, name="places-name")
    _State.thread.start()


def nudge() -> None:
    """踢醒空转的 worker (设置页存了 Web 服务 key 后立即开跑)。"""
    _State.wake.set()


def running() -> bool:
    """worker 是否在跑 (诊断用)。"""
    return _State.thread is not None and _State.thread.is_alive()


def reset() -> None:
    """测试隔离: 收掉在跑的线程, 清空记账。"""
    _State.stop.set()
    _State.wake.set()
    if _State.thread is not None:
        _State.thread.join(timeout=5)
    _State.thread = None
    _State.stop.clear()
    _State.wake.clear()
    _State.attempts.clear()
    _State.calls_today = 0
    _State.day = None


def _sleep(seconds: float) -> None:
    """可被 nudge 打断的睡 (stop 由外层 while 收)。"""
    _State.wake.clear()
    _State.wake.wait(seconds)


def _roll_day() -> None:
    """日记账翻页 (过了零点清当日调用数)。"""
    today = date.today()
    if _State.day != today:
        _State.day = today
        _State.calls_today = 0


def _seconds_to_midnight() -> float:
    """到次日零点的秒数 (日配额歇)。"""
    now = datetime.now()
    mid = datetime.combine(now + timedelta(days=1), dtime.min)
    return max(60.0, (mid - now).total_seconds())


def _round(tesla_factory: sessionmaker[Session],
           own_factory: sessionmaker[Session]) -> tuple[bool, float]:
    """一轮: 读 key → 拉待办地址 → 逐址问高德落库。返回 (有无进展, 歇秒)。"""
    with own_factory() as own:
        key = amap_web_key_value(own)
        if not key:
            return False, 0.0
        done = done_address_ids(own, PLACE_NAME_V)
    _roll_day()
    if _State.calls_today >= CALL_CAP_PER_DAY:
        return False, _seconds_to_midnight()
    with tesla_factory() as session:
        pending = [(i, lat, lng) for i, lat, lng in all_address_coords(session)
                   if i not in done][:ROUND_MAX]
    if not pending:
        return False, 0.0
    progressed = False
    client = roads_amap.AmapClient(key, min_interval=THROTTLE_S)
    try:
        for addr_id, lat, lng in pending:
            if _State.stop.is_set():
                break
            if _State.attempts.get(addr_id, 0) >= ATTEMPTS_MAX:
                continue
            try:
                geo = client.regeo(lng, lat)
            except roads_amap.AmapQuota as exc:
                print(f"[places] {addr_id} 配额, 歇 {QUOTA_PAUSE_S}s: {exc}",
                      file=sys.stderr)
                return progressed, QUOTA_PAUSE_S
            except roads_amap.AmapError as exc:
                _State.attempts[addr_id] = _State.attempts.get(addr_id, 0) + 1
                print(f"[places] {addr_id} 调用失败 "
                      f"({_State.attempts[addr_id]}/{ATTEMPTS_MAX}): {exc}",
                      file=sys.stderr)
                continue
            name = pick_place_name(geo) if geo else ""
            status = "ok" if name else "skip"
            with own_factory() as own:
                save_place_name(own, place_name_row(
                    addr_id, status, PLACE_NAME_V, name))
            progressed = True
            print(f"[places] {addr_id} {status} {name}", file=sys.stderr)
    finally:
        _State.calls_today += client.calls
        client.close()
    return progressed, 0.0


def _loop(tesla_factory: sessionmaker[Session],
          own_factory: sessionmaker[Session]) -> None:
    """主循环: 有进展立刻下一轮, 没事歇 60s (nudge 可踢醒)。"""
    if _State.stop.wait(PEAK_DELAY_S):
        return
    while not _State.stop.is_set():
        try:
            progressed, pause = _round(tesla_factory, own_factory)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[places] 轮次异常, 歇 {IDLE_SLEEP_S}s: {exc!r}",
                  file=sys.stderr)
            progressed, pause = False, IDLE_SLEEP_S
        if pause:
            _sleep(pause)
        elif not progressed:
            _sleep(IDLE_SLEEP_S)
