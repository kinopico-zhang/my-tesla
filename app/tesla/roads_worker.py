"""足迹「走过之路」后台 worker: 已结束行程逐段拟合到实际道路, 结果写
drive_roads (一次性回填 ~1-2 千次调用, 之后水位增量补新行程)。

节奏: 最新优先, 每轮 ≤50 程再查 (不长占库); REST 调用间隔节流 0.4s;
配额码歇 1 小时, 自记账日上限 9000 次歇到次日零点。key 每轮现读 (设置页
换 key 不用重启, 保存时 /roads/tick 会 nudge); 会话全短开短闭 (list/
单程读/写各一个)。网络/服务错误不落行 (下轮重试), 同程 3 次后本进程
放弃 —— 对账不过/抓路全灭才是落 guess 行 (几何保留虚线), 彻底没几何
才 failed/skip (同 v 不再重算)。"""
import sys
import threading
from datetime import date, datetime, time as dtime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from . import roads_amap
from .repository.map_roads import (adopt_v2_ok, closed_drives,
                                   done_drive_ids, drive_points, road_row,
                                   save_road)
from .roads_fit import ROAD_FIT_V, fit_drive
from .settings_store import amap_web_key_value

CALL_CAP_PER_DAY = 9000   # 自记账日上限 (官方个人 1 万, 留余量)
THROTTLE_S = 0.4          # 相邻 REST 调用最小间隔
IDLE_SLEEP_S = 60         # 空转轮询 (无 key / 无待办)
PEAK_DELAY_S = 90         # 启动错峰: 两条预热线程先跑
ROUND_MAX = 50            # 每轮最多处理行程数 (再查待办, 不长占库)
QUOTA_PAUSE_S = 3600      # 配额码的歇时
ATTEMPTS_MAX = 3          # 同程网络/服务错误重试上限 (本进程)


class _State:
    """模块单例 (与 tracks_cache 同款): 测试用 reset 收线程清记账。"""

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
        daemon=True, name="roads-fit")
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
    """一轮: 读 key → 拉待办 → 逐程拟合落库。返回 (有无进展, 该歇秒数)。"""
    with own_factory() as own:
        # v2 的 ok 无推断行直采为当前版 (输出等价, 不重拟合烧配额)
        adopted = adopt_v2_ok(own, ROAD_FIT_V)
        if adopted:
            print(f"[roads] v2→v{ROAD_FIT_V} 直采 {adopted} 程 "
                  f"(ok 无推断, 不重拟合)", file=sys.stderr)
        key = amap_web_key_value(own)
        if not key:
            return False, 0.0
        done = done_drive_ids(own, ROAD_FIT_V)
    _roll_day()
    if _State.calls_today >= CALL_CAP_PER_DAY:
        return False, _seconds_to_midnight()
    with tesla_factory() as session:
        pending = [(i, km) for i, km in closed_drives(session)
                   if i not in done][:ROUND_MAX]
    if not pending:
        return False, 0.0
    progressed = False
    client = roads_amap.AmapClient(key, min_interval=THROTTLE_S)
    try:
        for drive_id, km in pending:
            if _State.stop.is_set():
                break
            if _State.attempts.get(drive_id, 0) >= ATTEMPTS_MAX:
                continue
            with tesla_factory() as session:
                points = drive_points(session, drive_id)
            try:
                res = fit_drive(points, km, client)
            except roads_amap.AmapQuota as exc:
                print(f"[roads] {drive_id} 配额, 歇 {QUOTA_PAUSE_S}s: {exc}",
                      file=sys.stderr)
                return progressed, QUOTA_PAUSE_S
            except roads_amap.AmapError as exc:
                _State.attempts[drive_id] = _State.attempts.get(drive_id, 0) + 1
                print(f"[roads] {drive_id} 调用失败 "
                      f"({_State.attempts[drive_id]}/{ATTEMPTS_MAX}): {exc}",
                      file=sys.stderr)
                continue
            with own_factory() as own:
                save_road(own, road_row(drive_id, res.status, ROAD_FIT_V,
                                        res.pts, res.n, res.km, res.err,
                                        res.gaps))
            progressed = True
            print(f"[roads] {drive_id} {res.status} {res.km}km {res.n}pts"
                  + (f" {res.err}" if res.err else ""), file=sys.stderr)
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
            print(f"[roads] 轮次异常, 歇 {IDLE_SLEEP_S}s: {exc!r}", file=sys.stderr)
            progressed, pause = False, IDLE_SLEEP_S
        if pause:
            _sleep(pause)
        elif not progressed:
            _sleep(IDLE_SLEEP_S)
