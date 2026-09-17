"""充电统计: 维度聚合/地图点位/汇总/按月按地分组 (与列表同源同日期口径)。"""
from typing import Any

from sqlalchemy.orm import Session

from .charge_samples import ChargeRow, _charge_rows
from .charging_sessions import _location_name
from ..common import DateRange, _fnum, fdate, to_local
from ...schemas import (
    ChargeDims,
    ChargeMapLocation,
    ChargingSummary,
    CityStat,
    LocationStat,
    MonthlyStat,
)


def charging_dimensions(session: Session, date_range: DateRange | None) -> ChargeDims:
    """充电统计维度聚合 (快慢/时段/起充 SOC/峰值功率/城市), 与列表同源同日期口径。"""
    rows = _charge_rows(session, date_range, None)
    by_hour = [0] * 24
    by_soc = [0] * 5
    by_power = [0] * 5
    fast = slow = 0
    cities: dict[str, dict[str, float]] = {}
    for row in rows:
        cp, agg = row.process, row.agg
        if agg.is_fast:
            fast += 1
        else:
            slow += 1
        by_hour[to_local(cp.start_date).hour] += 1
        soc = cp.start_battery_level
        if soc is not None:
            by_soc[min(int(soc) // 20, 4)] += 1     # 100% 也进 80-100 档
        power = agg.power_max
        if power is not None:
            by_power[0 if power < 60 else 1 if power < 100 else
                     2 if power < 150 else 3 if power < 200 else 4] += 1
        city = row.address.city if row.address else None
        if city:      # 无地址/无城市的充电不进城市维度 (与城市筛选下拉同口径)
            c = cities.setdefault(city, {"sessions": 0, "energy": 0.0, "cost": 0.0})
            c["sessions"] += 1
            c["energy"] += (_fnum(cp.charge_energy_used)
                            or _fnum(cp.charge_energy_added) or 0.0)
            c["cost"] += _fnum(cp.cost) or 0.0
    top = sorted(cities.items(), key=lambda kv: -kv[1]["sessions"])[:10]
    return ChargeDims(
        fast_sessions=fast, slow_sessions=slow, by_hour=by_hour,
        by_soc=by_soc, by_power=by_power,
        by_city=[CityStat(city=k, sessions=int(v["sessions"]),
                          energy=round(v["energy"], 1), cost=round(v["cost"], 2))
                 for k, v in top])


def charging_map_locations(session: Session,
                           date_range: DateRange | None) -> list[ChargeMapLocation]:
    """充电地图聚合: 按地址聚充电点 (次数降序), 无坐标的地址不上图。

    展示名与列表口径一致 —— geofence 名 (家/公司) 优先于地址名;
    同一地址多次充电挂不同 geofence 时, 取最近一次充电的名字。"""
    rows = _charge_rows(session, date_range, None)
    points: dict[int, dict[str, Any]] = {}
    for row in rows:
        addr = row.address
        if addr is None or addr.latitude is None or addr.longitude is None:
            continue    # 没反向地理编码过的地址没有坐标, 圆标无处可放
        cp = row.process
        p = points.get(addr.id)
        if p is None:
            p = points[addr.id] = {
                "id": addr.id, "city": addr.city,
                "lat": float(addr.latitude), "lng": float(addr.longitude),
                "sessions": 0, "fast_sessions": 0, "energy": 0.0, "cost": 0.0,
                "name": "", "latest": cp.start_date,
            }
        p["sessions"] += 1
        if row.agg.is_fast:
            p["fast_sessions"] += 1
        p["energy"] += _fnum(cp.charge_energy_used) or _fnum(cp.charge_energy_added) or 0.0
        p["cost"] += _fnum(cp.cost) or 0.0
        if cp.start_date >= p["latest"]:     # ≥: 首行也会填名字
            p["latest"] = cp.start_date
            p["name"] = (row.geofence.name
                         if row.geofence is not None and row.geofence.name
                         else addr.name or addr.display_name or "未知位置")
    return [ChargeMapLocation(
                id=p["id"], name=p["name"], city=p["city"],
                lat=p["lat"], lng=p["lng"],
                sessions=p["sessions"], fast_sessions=p["fast_sessions"],
                energy=round(p["energy"], 1), cost=round(p["cost"], 2))
            for p in sorted(points.values(), key=lambda p: (-p["sessions"], p["id"]))]


def charging_summary(session: Session,
                     date_range: DateRange | None) -> ChargingSummary:
    """充电汇总: 次数 / 电量 / 费用 / 快充占比 / SOC 与续航增益。"""
    rows = _charge_rows(session, date_range, None)
    energy_added = sum(r.process.charge_energy_added or 0.0 for r in rows)
    energy_used = sum(r.process.charge_energy_used or 0.0 for r in rows)
    cost = sum(r.process.cost or 0.0 for r in rows)
    duration = sum(r.process.duration_min or 0 for r in rows)
    fast = sum(1 for r in rows if r.agg.is_fast)
    soc_gain = sum((r.process.end_battery_level or 0) -
                   (r.process.start_battery_level or 0) for r in rows)
    range_gain = sum((r.process.end_rated_range_km or 0.0) -
                     (r.process.start_rated_range_km or 0.0) for r in rows)
    dates = [r.process.start_date for r in rows]
    energy = energy_used or energy_added
    return ChargingSummary(
        sessions=len(rows), fast_sessions=fast,
        energy_added=float(energy_added), energy_used=float(energy_used),
        cost=round(cost, 2) if cost else 0.0,
        price_per_kwh=round(cost / energy, 3) if energy else None,
        duration_min=duration, soc_gain=int(soc_gain),
        range_gain=round(float(range_gain), 1),
        first_date=fdate(min(dates)) if dates else None,
        last_date=fdate(max(dates)) if dates else None)


def monthly_stats(session: Session,
                  date_range: DateRange | None) -> list[MonthlyStat]:
    """按本地月份分组的充电统计 (分组在 Python 侧, 免 to_char 方言差异)。"""
    rows = _charge_rows(session, date_range, None)
    grouped: dict[str, list[ChargeRow]] = {}
    for row in rows:
        grouped.setdefault(
            to_local(row.process.start_date).strftime("%Y-%m"), []).append(row)
    return [MonthlyStat(
        month=month, sessions=len(group),
        energy_used=_sum_field(group, "charge_energy_used"),
        cost=_sum_field(group, "cost"),
        fast_sessions=sum(1 for r in group if r.agg.is_fast))
        for month, group in sorted(grouped.items())]


def location_stats(session: Session,
                   date_range: DateRange | None) -> list[LocationStat]:
    """按充电地点 (围栏优先, 否则地址名) 分组的统计, 按次数降序。"""
    rows = _charge_rows(session, date_range, None)
    grouped: dict[tuple[str, str | None], list[ChargeRow]] = {}
    for row in rows:
        grouped.setdefault(
            (_location_name(row), row.address.city if row.address else None),
            []).append(row)
    stats = [LocationStat(
        location=location, city=city, sessions=len(group),
        energy_used=_sum_field(group, "charge_energy_used"),
        cost=_sum_field(group, "cost"),
        fast_sessions=sum(1 for r in group if r.agg.is_fast))
        for (location, city), group in grouped.items()]
    stats.sort(key=lambda s: s.sessions, reverse=True)
    return stats


def _sum_field(rows: list[ChargeRow], field: str) -> float | None:
    """对行的 process 属性求和 (忽略 None); 全空返回 None。"""
    values = [v for row in rows
              if (v := getattr(row.process, field)) is not None]
    return float(sum(values)) if values else None
