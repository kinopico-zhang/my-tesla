"""行程列表与单条: 条目组装/过滤条件 (时间/地区/里程/驾驶员)/起终点地区树。"""
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from ...models import Address, Drive
from .trip_marks import _driver_condition, annotate_drivers, annotate_tolls
from ..charging import _range_conditions, charge_efficiency
from ..common import DateRange, _clean_addr, fdate, ftime
from ..region_tree import _acc_region_tree, region_address_ids
from ...schemas import RegionNode, TripItem, TripRegions


def _consumption(drive: Drive, eff: float | None) -> tuple[float | None, float | None]:
    """(总电耗 kWh, 平均电耗 Wh/km): 额定续航差 × 换算系数。

    续航差为负 (行驶中续航校准回弹) 夹到 0; 里程不足 1km 时平均无意义。"""
    if eff is None or drive.start_rated_range_km is None or drive.end_rated_range_km is None:
        return None, None
    raw = max(0.0, (float(drive.start_rated_range_km)
                    - float(drive.end_rated_range_km)) * eff)
    dist = float(drive.distance) if drive.distance is not None else None
    return (round(raw, 1),
            round(raw / dist * 1000) if dist and dist >= 1 else None)


def _trip_item(drive: Drive, start_addr: str | None,
               end_addr: str | None, eff: float | None = None) -> TripItem:
    kwh, wh_per_km = _consumption(drive, eff)
    return TripItem(
        id=drive.id,
        date=fdate(drive.start_date),
        start=ftime(drive.start_date),
        end=ftime(drive.end_date) if drive.end_date else None,
        km=round(float(drive.distance), 2) if drive.distance is not None else None,
        min=drive.duration_min,
        speed_max=drive.speed_max,
        from_=_clean_addr(start_addr),
        to=_clean_addr(end_addr),
        kwh=kwh, wh_per_km=wh_per_km)


@dataclass(frozen=True)
class TripFilter:
    """行程列表过滤条件 (顶栏时间 + 筛选行起终地区 / 里程)。

    from_loc / to_loc 是 "/" 连接的省市区路径 (1~3 段):
    "广东省"=整省, "广东省/深圳市"=整市, "广东省/深圳市/龙华区"=精确到区县。
    """

    date_range: DateRange | None = None
    from_loc: str | None = None     # 起点地区 (空 = 全部)
    to_loc: str | None = None       # 终点地区 (空 = 全部)
    km_min: float | None = None     # 里程下限 (km)
    km_max: float | None = None     # 里程上限 (km)
    driver_id: int | None = None    # 驾驶员 (own 库驾驶员 id, 空 = 全部)
    car_id: int | None = None       # 车辆 (多车切换, 空 = 全部)


def _trip_rows_stmt(start_addr: type[Address],
                    end_addr: type[Address]) -> Select[Any]:
    """行程查询骨架: 只取已结束行程, 带起终点地址 (结束时间降序交给调用方)。"""
    return (select(Drive, start_addr.display_name, end_addr.display_name)
            .join(start_addr, Drive.start_address_id == start_addr.id, isouter=True)
            .join(end_addr, Drive.end_address_id == end_addr.id, isouter=True)
            .where(Drive.end_date.is_not(None)))


def _trip_conditions(session: Session,
                     flt: TripFilter | None) -> list[ColumnElement[bool]]:
    """时间 / 起终地区 / 里程 / 车辆过滤条件 (计数与列表共用)。"""
    conds = _range_conditions(Drive.start_date, flt.date_range if flt else None)
    if flt:
        if flt.car_id is not None:
            conds.append(Drive.car_id == flt.car_id)
        if flt.from_loc:
            conds.append(Drive.start_address_id.in_(
                region_address_ids(session, flt.from_loc)))
        if flt.to_loc:
            conds.append(Drive.end_address_id.in_(
                region_address_ids(session, flt.to_loc)))
        if flt.km_min is not None:
            conds.append(Drive.distance >= flt.km_min)
        if flt.km_max is not None:
            conds.append(Drive.distance <= flt.km_max)
    return conds


def _eff_by_car(session: Session,
                car_ids: set[int]) -> dict[int, float | None]:
    """逐车的电耗换算系数 (各车电池效率不同; 每车一次聚合, 混排页共用)。"""
    return {cid: charge_efficiency(session, cid) for cid in car_ids}


def list_trips(session: Session, own: Session, offset: int, limit: int,
               flt: TripFilter | None = None) -> tuple[int, list[TripItem]]:
    """行程列表 (最新在前), total 为已结束行程数; 按出发时间/起终地区/里程过滤。"""
    conds = _trip_conditions(session, flt)
    if flt and flt.driver_id is not None:
        conds.append(_driver_condition(own, flt.driver_id))
    total = session.scalar(
        select(func.count()).select_from(Drive)
        .where(Drive.end_date.is_not(None), *conds)) or 0
    rows = session.execute(
        _trip_rows_stmt(aliased(Address), aliased(Address)).where(*conds)
        .order_by(Drive.start_date.desc())
        .offset(offset).limit(limit)).all()
    effs = _eff_by_car(session, {d.car_id for d, _, _ in rows})
    items = [_trip_item(d, s, e, effs.get(d.car_id)) for d, s, e in rows]
    annotate_drivers(own, items)
    annotate_tolls(own, items)
    return int(total), items


def _region_tree(session: Session,
                 address_id: InstrumentedAttribute[int | None],
                 car_id: int | None = None) -> list[RegionNode]:
    """某个地址角色 (起点/终点) 的省→市→区县计数树 (次数降序, 未结束行程不计)。"""
    addr = aliased(Address)
    stmt = (select(addr.display_name)
            .select_from(Drive)
            .join(addr, address_id == addr.id, isouter=True)
            .where(Drive.end_date.is_not(None)))
    if car_id is not None:
        stmt = stmt.where(Drive.car_id == car_id)
    rows = session.execute(stmt).all()
    return _acc_region_tree(name for (name,) in rows)


def list_trip_regions(session: Session,
                      car_id: int | None = None) -> TripRegions:
    """行程起终点省市区树 (级联下拉数据源); car_id 选定时只数那台车的行程。"""
    return TripRegions(
        start=_region_tree(session, Drive.start_address_id, car_id),
        end=_region_tree(session, Drive.end_address_id, car_id))


def get_trip(session: Session, own: Session, drive_id: int) -> TripItem | None:
    """单条行程 (未结束 / 不存在返回 None); 电耗按该车自己的充电定标。"""
    rows = session.execute(
        _trip_rows_stmt(aliased(Address), aliased(Address))
        .where(Drive.id == drive_id)).all()
    if not rows:
        return None
    drive = rows[0][0]
    item = _trip_item(drive, rows[0][1], rows[0][2],
                      charge_efficiency(session, drive.car_id))
    annotate_drivers(own, [item])
    annotate_tolls(own, [item])
    return item
