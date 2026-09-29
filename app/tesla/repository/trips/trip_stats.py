"""行程统计: 汇总/按月/常去地点/司机里程/多维聚合 (2026-09-27 新增, 参照
充电统计; 电耗口径与行程列表同源 —— 额定续航差 × 桩端定标系数, 没定标
的车不进电耗)。"""
from typing import Any, Final

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, aliased

from ...models import Address, Drive, Driver, TripDriver
from ...schemas import (
    TripDims,
    TripDriverStat,
    TripLocStat,
    TripMonthlyStat,
    TripStatsSummary,
)
from ..charging import _bump
from ..common import _clean_addr, fdate, to_local
from .trip_listing import _consumption, _eff_by_car, _trip_rows_stmt

TRIP_DIST_EDGES: Final = (2, 5, 10, 20, 50, 100, 150, 200, 300)       # 单程距离十档
TRIP_DUR_EDGES: Final = (10, 20, 30, 45, 60, 90, 120, 180, 300)       # 行驶时长十档
TRIP_WH_EDGES: Final = (100, 120, 140, 160, 180, 200, 220, 240, 260)  # 平均电耗十档


def _trip_rows(session: Session, car_id: int | None = None) -> list[Any]:
    """全部已结束行程 (带起终点地址, 出发时间升序): 统计页各接口共用的取数。"""
    stmt: Select[Any] = _trip_rows_stmt(aliased(Address), aliased(Address))
    if car_id is not None:
        stmt = stmt.where(Drive.car_id == car_id)
    return list(session.execute(stmt.order_by(Drive.start_date)).all())


def trip_summary(session: Session,
                 car_id: int | None = None) -> TripStatsSummary:
    """行程汇总: 次数 / 里程 / 时长 / 电耗 / 最高车速 (没定标 = None)。"""
    rows = _trip_rows(session, car_id)
    effs = _eff_by_car(session, {d.car_id for d, _, _ in rows})
    kwhs = [k for d, _, _ in rows
            if (k := _consumption(d, effs.get(d.car_id))[0]) is not None]
    km = sum(float(d.distance) for d, _, _ in rows if d.distance is not None)
    duration = sum(d.duration_min or 0 for d, _, _ in rows)
    speeds = [s for s in (d.speed_max for d, _, _ in rows) if s is not None]
    dates = [d.start_date for d, _, _ in rows]
    total_kwh = round(sum(kwhs), 1) if kwhs else None
    return TripStatsSummary(
        trips=len(rows), km=round(km, 1), duration_min=duration, kwh=total_kwh,
        wh_per_km=(round(total_kwh / km * 1000)
                   if total_kwh is not None and km else None),
        speed_max=max(speeds) if speeds else None,
        first_date=fdate(min(dates)) if dates else None,
        last_date=fdate(max(dates)) if dates else None)


def trip_monthly(session: Session,
                 car_id: int | None = None) -> list[TripMonthlyStat]:
    """按本地月份分组的行程统计 (里程/电耗; 与充电统计同款 Python 侧分组)。"""
    rows = _trip_rows(session, car_id)
    effs = _eff_by_car(session, {d.car_id for d, _, _ in rows})
    grouped: dict[str, list[tuple[Drive, float | None]]] = {}
    for d, _, _ in rows:
        grouped.setdefault(
            to_local(d.start_date).strftime("%Y-%m"),
            []).append((d, _consumption(d, effs.get(d.car_id))[0]))
    stats = []
    for month, group in sorted(grouped.items()):
        kwhs = [k for _, k in group if k is not None]
        stats.append(TripMonthlyStat(
            month=month, trips=len(group),
            km=round(sum(float(d.distance) for d, _ in group
                         if d.distance is not None), 1),
            kwh=round(sum(kwhs), 1) if kwhs else None))
    return stats


def trip_locations(session: Session,
                   car_id: int | None = None) -> list[TripLocStat]:
    """常去地点: 起终点地址并计 (地名优先, 否则清洗后的地址链), 次数降序。"""
    rows = _trip_rows(session, car_id)
    counts: dict[str, int] = {}
    for _, start, end in rows:
        for addr in (start, end):
            if addr is None:
                continue        # 没反向地理编码的行程不起终点, 不进地点统计
            name = addr.name or _clean_addr(addr.display_name)
            if name:
                counts[name] = counts.get(name, 0) + 1
    return [TripLocStat(name=k, trips=v)
            for k, v in sorted(counts.items(),
                               key=lambda kv: (-kv[1], kv[0]))[:12]]


def trip_driver_stats(session: Session, own: Session,
                      car_id: int | None = None) -> list[TripDriverStat]:
    """司机里程分布: 按驾驶员归集的里程/次数 (2026-09-27 用户点名)。

    归集口径与行程卡片同源 (annotate_drivers): 显式标注 > 默认驾驶员
    兜底, 都没有的归「未标注」; 里程为空的行程照计次数不进里程。
    按里程降序, 同里程按名字。标注表在自有库, 与行程不在一个连接 ——
    先取 id 集合再 Python 侧归集 (与列表标注同套路, 不跨库子查询)。"""
    rows = _trip_rows(session, car_id)
    if not rows:
        return []
    drivers = {d.id: d for d in own.scalars(select(Driver)).all()}
    default = next((d for d in drivers.values() if d.is_default), None)
    marks = {m.drive_id: m.driver_id for m in own.scalars(
        select(TripDriver)
        .where(TripDriver.drive_id.in_([d.id for d, _, _ in rows]))).all()}
    stats: dict[str, tuple[float, int]] = {}
    for d, _, _ in rows:
        did = marks.get(d.id)
        driver = drivers.get(did) if did is not None else None
        shown = driver or default
        name = shown.name if shown is not None else "未标注"
        km, n = stats.get(name, (0.0, 0))
        stats[name] = (km + float(d.distance or 0), n + 1)
    return [TripDriverStat(name=k, km=round(v[0], 1), trips=v[1])
            for k, v in sorted(stats.items(),
                               key=lambda kv: (-kv[1][0], kv[0]))]


def trip_dimensions(session: Session, car_id: int | None = None) -> TripDims:
    """行程统计维度聚合: 出发时段 (每 2 小时) / 单程距离 / 行驶时长 /
    平均电耗 (充电统计落档同款, 没值/没定标的不进档)。车速档不在此算 ——
    是 positions 积分的各速度段里程 (speed_hist_cache), 路由侧合入,
    这里占位 [0] * 9。"""
    rows = _trip_rows(session, car_id)
    effs = _eff_by_car(session, {d.car_id for d, _, _ in rows})
    by_hour = [0] * 12    # 2 小时一组: 下标 = 出发小时 // 2 (与充电开始时段同款)
    by_dist = [0] * 10
    by_dur = [0] * 10
    by_spd = [0.0] * 9    # 占位: 路由侧换 speed_hist_cache 的真速度分布
    by_wh = [0] * 10
    for d, _, _ in rows:
        by_hour[to_local(d.start_date).hour // 2] += 1
        _bump(by_dist, d.distance, TRIP_DIST_EDGES)
        _bump(by_dur, d.duration_min, TRIP_DUR_EDGES)
        _bump(by_wh, _consumption(d, effs.get(d.car_id))[1], TRIP_WH_EDGES)
    return TripDims(by_hour=by_hour, by_dist=by_dist, by_dur=by_dur,
                    by_spd=by_spd, by_wh=by_wh)
