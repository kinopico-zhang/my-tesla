"""行车速度直方图缓存: 行程统计「车速分布」的数据源 —— 各速度段的行驶
里程, 从 positions 逐秒采样积分 (每点采样速度 × 距上一点的间隔, 间隔超
60s 的整段丢 —— NAS 实测 12.1M 点全量流扫 ~63s、≤60s 间隔已覆盖 100.5%
行驶里程, 超出的缺口是断连丢的采样, 不猜)。

2026-09-27 用户点名「车速分布, 不是最大车速分布」「纵坐标是 km」——
每程 speed_max 的口径退役, 换真速度分布。

已完成行程不会变更 → 内存 + 磁盘两级按 drive id 记账 (同 tracks_cache
口径); 增量按「缺哪条补哪条」而不追 id 水位 —— 多车行程 id 交错, 小 id
晚结束会漏在水位后面。磁盘缓存 JSONL (首行头 {v}, 之后一行一条
{id, b}), 逐行解析、整册重写落盘。

缓存持有者/落盘样板与 tracks_cache 有意同款 (验证过的两级缓存配方,
不抽公共件 —— 那边还要背着历史行为跑测试)。
"""
# pylint: disable=duplicate-code
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from itertools import chain
from pathlib import Path
from typing import Any, Final

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .. import config
from .models import Drive, Position

CACHE_VERSION = 1
SPD_EDGES: Final = (20, 40, 60, 80, 100, 120, 140, 160)   # 车速九档 (≥160 收尾)
CAP_SECS: Final = 60          # 采样间隔上限 (秒): 正常采样 ~1s, 超出当断连缺口整段丢


@dataclass
class _CacheState:
    """内存缓存水位: 每条已结束行程的速度档里程 (drive id → 九档 km)。"""

    hist: dict[int, list[float]]


class _Cache:
    """模块级缓存持有者 (避免 global 语句; 测试用 reset 清空)。"""

    state: _CacheState | None = None


_cache = _Cache()
_lock = threading.Lock()


def reset() -> None:
    """清空内存缓存 (测试隔离用)。"""
    _cache.state = None


def cache_file() -> str:
    """磁盘缓存路径 (测试用 SPEED_HIST_CACHE_FILE 重定向)。"""
    return os.environ.get("SPEED_HIST_CACHE_FILE") or str(
        config.PROJECT_DIR / "data" / "speed_hist_cache.json")


def speed_bins(session: Session, car_id: int | None = None) -> list[float]:
    """车速九档行驶里程 (该车的已结束行程合计, km, 0.1 精度)。"""
    rows = _finished(session)
    hist = load_hist(session, [i for i, _ in rows])
    bins = [0.0] * (len(SPD_EDGES) + 1)
    for i, cid in rows:
        if car_id is None or cid == car_id:
            for k, v in enumerate(hist[i]):
                bins[k] += v
    return [round(b, 1) for b in bins]


def load_hist(session: Session,
              wanted: list[int]) -> dict[int, list[float]]:
    """确保直方图覆盖 wanted (内存 → 磁盘 → 现场积分, 缺哪条补哪条)。"""
    with _lock:
        state = _cache.state if _cache.state is not None else _read_disk_cache()
        missing = [i for i in wanted if i not in state.hist]
        if missing:
            state.hist.update(_scan(session, missing))
            _write_disk_cache(state.hist)
        _cache.state = state
        return state.hist


def warm(factory: sessionmaker[Session]) -> None:
    """启动时后台预热 (失败静默, 首次访问会重试)。"""
    try:
        with factory() as session:
            load_hist(session, [i for i, _ in _finished(session)])
    except (SQLAlchemyError, OSError):
        pass


def _finished(session: Session) -> list[Any]:
    """已结束行程 (id, car_id) 行: 直方图取数范围, 与统计页行程口径一致。"""
    return list(session.execute(
        select(Drive.id, Drive.car_id).where(Drive.end_date.is_not(None))))


def _scan(session: Session, ids: list[int]) -> dict[int, list[float]]:
    """现场积分: positions 按 (drive_id, date) 序流式取行, 每点速度 × 距
    上一点的间隔 (超 CAP_SECS 的缺口整段丢) 落速度档; 分区取行防整册物化
    (12M 点 .all() 会把 NAS 顶进 swap)。"""
    stmt: Select[Any] = (select(Position.drive_id, Position.date, Position.speed)
                         .where(Position.drive_id.in_(ids),
                                Position.speed.is_not(None))
                         .order_by(Position.drive_id, Position.date)
                         .execution_options(stream_results=True))
    hist: dict[int, list[float]] = {i: [0.0] * (len(SPD_EDGES) + 1) for i in ids}
    cur_id: int | None = None
    prev: datetime | None = None
    for drive_id, date, speed in chain.from_iterable(
            session.execute(stmt).partitions(20_000)):
        if drive_id != cur_id:
            cur_id, prev = drive_id, None
        elif prev is not None:
            secs = (date - prev).total_seconds()
            if 0 < secs <= CAP_SECS:
                spd = float(speed)
                for i, edge in enumerate(SPD_EDGES):
                    if spd < edge:
                        hist[drive_id][i] += spd * secs / 3600.0
                        break
                else:
                    hist[drive_id][len(SPD_EDGES)] += spd * secs / 3600.0
        prev = date
    return {i: [round(v, 3) for v in b] for i, b in hist.items()}


def _read_disk_cache() -> _CacheState:
    """读磁盘缓存 (JSONL, 见模块头); 版本不符 / 损坏一律当作没有。"""
    try:
        with open(cache_file(), encoding="utf-8") as handle:
            head = json.loads(handle.readline())
            if int(head["v"]) != CACHE_VERSION:
                return _CacheState({})
            hist: dict[int, list[float]] = {}
            for line in handle:
                if not line.strip():
                    continue
                rec = json.loads(line)
                bins = [float(x) for x in rec["b"]]
                if len(bins) != len(SPD_EDGES) + 1:
                    raise ValueError("档数不对, 整册作废")
                hist[int(rec["id"])] = bins
            return _CacheState(hist)
    except (OSError, ValueError, TypeError, KeyError):
        return _CacheState({})


def _write_disk_cache(hist: dict[int, list[float]]) -> None:
    """落盘 (临时文件 + 原子替换, JSONL 一行一条); 失败不影响本次响应。"""
    try:
        path = Path(cache_file())
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(path) + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"v": CACHE_VERSION},
                                    separators=(",", ":")) + "\n")
            for i, bins in hist.items():
                handle.write(json.dumps({"id": i, "b": bins},
                                        separators=(",", ":")) + "\n")
        os.replace(tmp, path)
    except OSError:
        pass
