"""充电取数与聚合: 充电过程行/采样聚合/日期条件/车辆信息/桩端换算系数。

列表/详情/统计都从这里的行取数出发 (排序分页与组装在调用方)。
"""
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from ...models import Address, Car, Charge, ChargingProcess, Geofence
from ..common import DateRange
from ...schemas import CarInfo


def list_cars(session: Session) -> list[CarInfo]:
    """车辆信息。"""
    rows = session.execute(
        select(Car.id, Car.name, Car.model, Car.trim_badging, Car.vin)
        .order_by(Car.id)).all()
    return [CarInfo(id=cid, name=name, model=model, trim_badging=trim, vin=vin)
            for cid, name, model, trim, vin in rows]


@dataclass
class ChargeAgg:
    """一次充电过程的采样聚合 (峰值功率 / 是否快充 / 是否特斯拉超充)。"""

    power_max: float | None
    is_fast: bool
    tesla_dc: bool


_NO_AGG = ChargeAgg(power_max=None, is_fast=False, tesla_dc=False)


def _charge_aggs(session: Session,
                 process_ids: Sequence[int]) -> dict[int, ChargeAgg]:
    """charges 采样聚合: max(功率) 与 bool_or(快充/特斯拉超充) 的方言中立等价写法。

    快充判定与旧 SQL 一致: fast_charger_present 为真 或 功率 ≥ 20kW;
    特斯拉超充 = 采样里有 brand=Tesla 且 type=Gb (国产 GB 桩端) —— 第三方
    国标快充同样报 Gb 但 brand 是 <invalid>, 不算。
    没有采样点的过程不在返回里 (等价 power_max=NULL, is_fast=false)。
    """
    if not process_ids:
        return {}
    fast_case = case(
        (or_(Charge.fast_charger_present.is_(True), Charge.charger_power >= 20), 1),
        else_=0)
    tesla_case = case(
        (and_(Charge.fast_charger_brand == "Tesla",
              Charge.fast_charger_type == "Gb"), 1),
        else_=0)
    rows = session.execute(
        select(Charge.charging_process_id, func.max(Charge.charger_power),
               func.max(fast_case), func.max(tesla_case))
        .where(Charge.charging_process_id.in_(process_ids))
        .group_by(Charge.charging_process_id)).all()
    return {pid: ChargeAgg(power_max=pmax, is_fast=bool(fast), tesla_dc=bool(tesla))
            for pid, pmax, fast, tesla in rows}


def _range_conditions(column: InstrumentedAttribute[datetime],
                      date_range: DateRange | None) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    if date_range is not None:
        if date_range.start is not None:
            conds.append(column >= date_range.start)
        if date_range.end is not None:
            conds.append(column < date_range.end)
    return conds


@dataclass
class ChargeRow:
    """充电过程 + 关联地址/围栏 + 采样聚合 (列表/详情/汇总共用)。"""

    process: ChargingProcess
    address: Address | None
    geofence: Geofence | None
    agg: ChargeAgg


def _charge_rows(session: Session, date_range: DateRange | None,
                 q: str | None, car_id: int | None = None) -> list[ChargeRow]:
    """按日期区间/地址关键字/车辆取充电过程 (不排序不分页, 交由调用方)。

    car_id 缺省 None = 全部车 (多车口径, 与前端车辆切换器一致)。"""
    conds: list[ColumnElement[bool]] = _range_conditions(ChargingProcess.start_date, date_range)
    if car_id is not None:
        conds.append(ChargingProcess.car_id == car_id)
    if q:
        # 拼接走 .concat() 运算符而非 func.concat(): 后者按 SQL 函数原样渲染,
        # SQLite 3.44 才有内建 concat() (ubuntu-22.04 的 3.37 直接 no such
        # function), .concat() 在 SQLite/PostgreSQL 编译成 ||, MySQL 才是
        # concat()。四个字段都 coalesce 过, || 不会把整串带成 NULL。
        haystack = (func.coalesce(Geofence.name, "")
                    .concat(" ")
                    .concat(func.coalesce(Address.name, ""))
                    .concat(" ")
                    .concat(func.coalesce(Address.city, ""))
                    .concat(" ")
                    .concat(func.coalesce(Address.display_name, "")))
        conds.append(func.lower(haystack).like(f"%{q.lower()}%"))
    stmt = (select(ChargingProcess, Address, Geofence)
            .join(Address, Address.id == ChargingProcess.address_id, isouter=True)
            .join(Geofence, Geofence.id == ChargingProcess.geofence_id, isouter=True))
    if conds:
        stmt = stmt.where(*conds)
    rows = [ChargeRow(process=cp, address=a, geofence=g, agg=_NO_AGG)
            for cp, a, g in session.execute(stmt).all()]
    _attach_aggs(session, rows)
    return rows


def _charge_rows_by_ids(session: Session,
                        ids: Sequence[int]) -> list[ChargeRow]:
    stmt = (select(ChargingProcess, Address, Geofence)
            .join(Address, Address.id == ChargingProcess.address_id, isouter=True)
            .join(Geofence, Geofence.id == ChargingProcess.geofence_id, isouter=True)
            .where(ChargingProcess.id.in_(ids)))
    rows = [ChargeRow(process=cp, address=a, geofence=g, agg=_NO_AGG)
            for cp, a, g in session.execute(stmt).all()]
    _attach_aggs(session, rows)
    return rows


def _attach_aggs(session: Session, rows: list[ChargeRow]) -> None:
    aggs = _charge_aggs(session, [row.process.id for row in rows])
    for row in rows:
        row.agg = aggs.get(row.process.id, _NO_AGG)


def charge_efficiency(session: Session,
                      car_id: int | None = None) -> float | None:
    """额定续航 km → 桩端 kWh 换算系数: 充电记录 Σ能量 / Σ续航增量。

    桩端口径 (含充电损耗), 与充电页对账一致 —— 同期 "充了多少" 和 "开了
    多少" 能对上; 多车时按车算 (各车电池效率不同), 缺省 None = 全部合算。
    没有可用充电记录 → None, 前端不显示电耗。"""
    conds = [ChargingProcess.end_date.is_not(None),
             ChargingProcess.charge_energy_added > 1,
             ChargingProcess.end_rated_range_km.is_not(None),
             ChargingProcess.start_rated_range_km.is_not(None),
             ChargingProcess.end_rated_range_km
             - ChargingProcess.start_rated_range_km > 1]
    if car_id is not None:
        conds.append(ChargingProcess.car_id == car_id)
    kwh, rng = session.execute(
        select(func.sum(ChargingProcess.charge_energy_added),
               func.sum(ChargingProcess.end_rated_range_km
                        - ChargingProcess.start_rated_range_km))
        .where(*conds)).one()
    if not kwh or not rng or float(rng) <= 0:
        return None
    return float(kwh) / float(rng)
