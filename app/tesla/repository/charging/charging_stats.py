"""充电统计: 维度聚合/地图点位/汇总/按月按地分组 (与列表同源同日期口径)。"""
from collections.abc import Callable
from typing import Final

from sqlalchemy.orm import Session

from .charge_samples import ChargeRow, CityAgg, MapPointAgg, _charge_rows
from .charging_sessions import _location_name
from ..common import DateRange, _clean_addr, _fnum, fdate, to_local
from ...models import Address, ChargingProcess
from ...schemas import (
    ChargeDims,
    ChargeMapLocation,
    ChargingSummary,
    CityStat,
    LocationStat,
    MonthlyStat,
)


_DISTRICT_SUFFIX = ("区", "县", "旗")
SOC_EDGES: Final = (10, 20, 30, 40, 50, 60, 70, 80, 90)          # 每 10% → 十档
POWER_EDGES: Final = (20, 40, 60, 80, 100, 120, 140, 160, 180)   # 每 20kW → 十档
PRICE_EDGES: Final = (.25, .5, .75, 1, 1.25, 1.5, 1.75, 2, 2.25)  # 每 0.25 → 十档
DUR_EDGES: Final = (30, 60, 90, 120, 180, 240, 300, 360, 480)    # 半小时细, 尾部变粗


def _bump(bins: list[int], value: float | None, edges: tuple[float, ...]) -> None:
    """值落档: None 不计; 按上界表进档, 超过表尾进最后一档 (100% → 90-100 档)。"""
    if value is None:
        return
    for i, edge in enumerate(edges):
        if value < edge:
            bins[i] += 1
            return
    bins[len(edges)] += 1


def _price_of(cp: ChargingProcess) -> float | None:
    """单次单价 = 费用 / 表计电量; 没记费用或没电量的返回 None (计未知)。"""
    cost = _fnum(cp.cost)
    energy = _fnum(cp.charge_energy_used) or _fnum(cp.charge_energy_added)
    return cost / energy if cost is not None and energy else None


def _city_name(address: Address | None) -> str | None:
    """城市分布只到市 (2026-09-27 用户点名): 区/县写进 city 时, 从 display_name
    完整链 (…, 龙华区, 深圳市, 广东省) 找回上级市; 找不到保持原值。"""
    if address is None:
        return None
    city = address.city
    if not city or not city.endswith(_DISTRICT_SUFFIX):
        return city
    for part in (address.display_name or "").replace("，", ",").split(","):
        if part.strip().endswith("市"):
            return part.strip()
    return city


def charging_dimensions(session: Session, date_range: DateRange | None,
                        car_id: int | None = None) -> ChargeDims:
    """充电统计维度聚合 (开始时段/起充 SOC/峰值功率/单价/时长/城市), 与列表
    同源同日期口径。快慢充计数随环形图退役 (汇总的 fast_sessions 还在)。"""
    rows = _charge_rows(session, date_range, None, car_id)
    by_hour = [0] * 12    # 2 小时一组 (2026-09-27 用户点名): 下标 = 开始小时 // 2
    by_soc = [0] * 10
    by_power = [0] * 10
    by_price = [0] * 10
    by_duration = [0] * 10
    cities: dict[str, CityAgg] = {}
    for row in rows:
        cp = row.process
        by_hour[to_local(cp.start_date).hour // 2] += 1
        _bump(by_soc, cp.start_battery_level, SOC_EDGES)
        _bump(by_power, row.agg.power_max, POWER_EDGES)
        _bump(by_price, _price_of(cp), PRICE_EDGES)
        _bump(by_duration, cp.duration_min, DUR_EDGES)
        city = _city_name(row.address)
        if city:      # 无地址/无城市的充电不进城市维度 (与城市筛选下拉同口径)
            c = cities.setdefault(city, CityAgg())
            c.sessions += 1
            c.energy += (_fnum(cp.charge_energy_used)
                         or _fnum(cp.charge_energy_added) or 0.0)
            c.cost += _fnum(cp.cost) or 0.0
    top = sorted(cities.items(), key=lambda kv: -kv[1].sessions)[:10]
    return ChargeDims(
        by_hour=by_hour, by_soc=by_soc, by_power=by_power,
        by_price=by_price, by_duration=by_duration,
        by_city=[CityStat(city=k, sessions=int(v.sessions),
                          energy=round(v.energy, 1), cost=round(v.cost, 2)) for k, v in top])


def charging_map_locations(session: Session,
                           date_range: DateRange | None,
                           car_id: int | None = None) -> list[ChargeMapLocation]:
    """充电地图聚合: 按地址聚充电点 (次数降序), 无坐标的地址不上图。

    展示名与列表口径一致 —— geofence 名 (家/公司) 优先于地址名;
    同一地址多次充电挂不同 geofence 时, 取最近一次充电的名字。"""
    rows = _charge_rows(session, date_range, None, car_id)
    points: dict[int, MapPointAgg] = {}
    for row in rows:
        addr = row.address
        if addr is None or addr.latitude is None or addr.longitude is None:
            continue    # 没反向地理编码过的地址没有坐标, 圆标无处可放
        cp = row.process
        p = points.get(addr.id)
        if p is None:
            p = points[addr.id] = MapPointAgg(
                id=addr.id, city=addr.city,
                lat=float(addr.latitude), lng=float(addr.longitude),
                latest=cp.start_date)
        p.sessions += 1
        if row.agg.is_fast:
            p.fast_sessions += 1
        p.energy += _fnum(cp.charge_energy_used) or _fnum(cp.charge_energy_added) or 0.0
        p.cost += _fnum(cp.cost) or 0.0
        if cp.start_date >= p.latest:     # ≥: 首行也会填名字
            p.latest = cp.start_date
            p.name = (row.geofence.name
                      if row.geofence is not None and row.geofence.name
                      else addr.name or _clean_addr(addr.display_name))
    return [ChargeMapLocation(
                id=p.id, name=p.name, city=p.city,
                lat=p.lat, lng=p.lng,
                sessions=p.sessions, fast_sessions=p.fast_sessions,
                energy=round(p.energy, 1), cost=round(p.cost, 2))
            for p in sorted(points.values(), key=lambda p: (-p.sessions, p.id))]


def charging_summary(session: Session,
                     date_range: DateRange | None,
                     car_id: int | None = None) -> ChargingSummary:
    """充电汇总: 次数 / 电量 / 费用 / 快充占比 / SOC 与续航增益。"""
    rows = _charge_rows(session, date_range, None, car_id)
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
                  date_range: DateRange | None,
                  car_id: int | None = None) -> list[MonthlyStat]:
    """按本地月份分组的充电统计 (分组在 Python 侧, 免 to_char 方言差异)。"""
    rows = _charge_rows(session, date_range, None, car_id)
    grouped: dict[str, list[ChargeRow]] = {}
    for row in rows:
        grouped.setdefault(
            to_local(row.process.start_date).strftime("%Y-%m"), []).append(row)
    return [MonthlyStat(
        month=month, sessions=len(group),
        energy_used=_sum_by(group, lambda r: r.process.charge_energy_used),
        cost=_sum_by(group, lambda r: r.process.cost),
        fast_sessions=sum(1 for r in group if r.agg.is_fast))
        for month, group in sorted(grouped.items())]


def location_stats(session: Session,
                   date_range: DateRange | None,
                   car_id: int | None = None) -> list[LocationStat]:
    """按充电地点 (围栏优先, 否则地址名) 分组的统计, 按次数降序。"""
    rows = _charge_rows(session, date_range, None, car_id)
    grouped: dict[tuple[str, str | None], list[ChargeRow]] = {}
    for row in rows:
        grouped.setdefault(
            (_location_name(row), row.address.city if row.address else None),
            []).append(row)
    stats = [LocationStat(
        location=location, city=city, sessions=len(group),
        energy_used=_sum_by(group, lambda r: r.process.charge_energy_used),
        cost=_sum_by(group, lambda r: r.process.cost),
        fast_sessions=sum(1 for r in group if r.agg.is_fast))
        for (location, city), group in grouped.items()]
    stats.sort(key=lambda s: s.sessions, reverse=True)
    return stats


def _sum_by(rows: list[ChargeRow],
            pick: Callable[[ChargeRow], float | None]) -> float | None:
    """按取值函数对行求和 (忽略 None); 全空返回 None。"""
    values = [v for row in rows if (v := pick(row)) is not None]
    return float(sum(values)) if values else None
