"""充电域: 列表/详情/费用回写/统计/地图点位/地区树

本模块只管 charging 域的查询与组装; 通用时间/参数工具在 common.py。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from collections.abc import Sequence

from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from ..models import Address, Car, Charge, ChargingProcess, Geofence
from .common import (
    DateRange,
    _acc_region_tree,
    _fnum,
    fdate,
    ftime,
    parse_region,
    to_local,
)
from ..schemas import (
    CarInfo,
    ChargeCurve,
    ChargeDims,
    ChargeMapLocation,
    ChargingSession,
    ChargingSessionDetail,
    ChargingSummary,
    CityStat,
    CostUpdateResult,
    LocationStat,
    MonthlyStat,
    RegionNode,
)


def list_cars(session: Session) -> list[CarInfo]:
    """车辆信息。"""
    rows = session.execute(
        select(Car.id, Car.name, Car.model, Car.trim_badging, Car.vin)
        .order_by(Car.id)).all()
    return [CarInfo(id=cid, name=name, model=model, trim_badging=trim, vin=vin)
            for cid, name, model, trim, vin in rows]


# ---------------------------------------------------------------- 充电


@dataclass
class ChargeAgg:
    """一次充电过程的采样聚合 (峰值功率 / 是否快充)。"""

    power_max: float | None
    is_fast: bool


_NO_AGG = ChargeAgg(power_max=None, is_fast=False)


def _charge_aggs(session: Session,
                 process_ids: Sequence[int]) -> dict[int, ChargeAgg]:
    """charges 采样聚合: max(功率) 与 bool_or(快充) 的方言中立等价写法。

    快充判定与旧 SQL 一致: fast_charger_present 为真 或 功率 ≥ 20kW;
    没有采样点的过程不在返回里 (等价 power_max=NULL, is_fast=false)。
    """
    if not process_ids:
        return {}
    fast_case = case(
        (or_(Charge.fast_charger_present.is_(True), Charge.charger_power >= 20), 1),
        else_=0)
    rows = session.execute(
        select(Charge.charging_process_id, func.max(Charge.charger_power),
               func.max(fast_case))
        .where(Charge.charging_process_id.in_(process_ids))
        .group_by(Charge.charging_process_id)).all()
    return {pid: ChargeAgg(power_max=pmax, is_fast=bool(fast))
            for pid, pmax, fast in rows}


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
                 q: str | None) -> list[ChargeRow]:
    """按日期区间与地址关键字取充电过程 (不排序不分页, 交由调用方)。"""
    conds: list[ColumnElement[bool]] = _range_conditions(ChargingProcess.start_date, date_range)
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


def _location_name(row: ChargeRow) -> str:
    if row.geofence is not None and row.geofence.name:
        return row.geofence.name
    if row.address is not None and row.address.name:
        return row.address.name
    return "未知位置"


def _session_item(row: ChargeRow) -> ChargingSession:
    cp = row.process
    energy_used = _fnum(cp.charge_energy_used)
    energy_added = _fnum(cp.charge_energy_added)
    cost = _fnum(cp.cost)
    base = energy_used or energy_added
    return ChargingSession(
        id=cp.id,
        start=ftime(cp.start_date),
        end=ftime(cp.end_date) if cp.end_date else None,
        date=fdate(cp.start_date),
        location=_location_name(row),
        city=row.address.city if row.address else None,
        address=row.address.display_name if row.address else None,
        start_soc=cp.start_battery_level,
        end_soc=cp.end_battery_level,
        energy_added=energy_added,
        energy_used=energy_used,
        cost=cost,
        price_per_kwh=round(cost / base, 3) if cost and base else None,
        duration_min=cp.duration_min,
        outside_temp=_fnum(cp.outside_temp_avg),
        power_max=row.agg.power_max,
        is_fast=row.agg.is_fast)


def _cost_of(row: ChargeRow) -> float | None:
    return row.process.cost


def _energy_of(row: ChargeRow) -> float | None:
    return row.process.charge_energy_used


def _duration_of(row: ChargeRow) -> int | None:
    return row.process.duration_min


def _power_of(row: ChargeRow) -> float | None:
    return row.agg.power_max


_SORT_FIELDS = {
    "cost_desc": _cost_of, "cost_asc": _cost_of,
    "energy_desc": _energy_of, "energy_asc": _energy_of,
    "duration_desc": _duration_of, "power_desc": _power_of,
}

SORT_OPTIONS = set(_SORT_FIELDS) | {"date_desc", "date_asc"}


def _sorted_charge_rows(rows: list[ChargeRow], sort: str) -> list[ChargeRow]:
    """排序; None 值排最后 (等价 Postgres NULLS LAST)。

    元组键的第一位保证 None 之间不再比较数值位 (None < None 会抛 TypeError)。
    """
    if sort == "date_desc":
        return sorted(rows, key=lambda r: r.process.start_date, reverse=True)
    if sort == "date_asc":
        return sorted(rows, key=lambda r: r.process.start_date)
    field = _SORT_FIELDS[sort]
    if sort.endswith("_asc"):
        return sorted(rows, key=lambda r: (field(r) is None, field(r)))
    return sorted(rows, key=lambda r: (field(r) is not None, field(r)),
                  reverse=True)


@dataclass(frozen=True)
class SessionFilter:
    """充电列表查询条件 (路由与仓库之间避免长参数列表)。"""

    date_range: DateRange | None
    charge_type: str        # all / fast / slow
    query: str | None       # 地址模糊搜索
    sort: str               # SORT_OPTIONS 之一
    offset: int
    limit: int
    region: str | None = None    # 充电地点 "/" 路径 (1~3 段 = 省/市/区县, 空 = 全部)
    cost: str | None = None      # 费用记录: recorded / missing (None = 全部)


def list_charging_sessions(session: Session,
                           flt: SessionFilter) -> tuple[int, list[ChargingSession]]:
    """充电列表: 日期/类型/搜索过滤 → 排序 → 分页; total 为过滤后总数。"""
    rows = _charge_rows(session, flt.date_range, flt.query)
    if flt.charge_type == "fast":
        rows = [row for row in rows if row.agg.is_fast]
    elif flt.charge_type == "slow":
        rows = [row for row in rows if not row.agg.is_fast]
    if flt.region:
        # 地点筛选与地点树同源同解析 (display_name 剥省市区), 段数即精确到哪一级
        rows = [row for row in rows if _match_region(row.address, flt.region)]
    if flt.cost == "recorded":   # 已记录费用 / 未记录费用 (费用记 0 也算已记录)
        rows = [row for row in rows if row.process.cost is not None]
    elif flt.cost == "missing":
        rows = [row for row in rows if row.process.cost is None]
    total = len(rows)
    rows = _sorted_charge_rows(rows, flt.sort)
    page = rows[flt.offset:flt.offset + flt.limit]
    return total, [_session_item(row) for row in page]


def charging_session_detail(session: Session,
                            session_id: int) -> ChargingSessionDetail | None:
    """充电详情: 卡片字段 + 采样曲线 / 充电线缆 / 快充品牌。"""
    rows = _charge_rows_by_ids(session, [session_id])
    if not rows:
        return None
    row = rows[0]
    cp = row.process
    samples = session.scalars(
        select(Charge).where(Charge.charging_process_id == session_id)
        .order_by(Charge.date)).all()

    def _clean(value: str | None) -> str | None:
        return value if value and value != "<invalid>" else None

    # 国标取值 (线缆 GB_AC/GB_DC, 充电类型 Gb) 在国内满屏都是, 没有信息量,
    # 2026-09-13 用户点名不展示; 其他取值 (CCS / v3 等) 照常
    def _clean_national(value: str | None) -> str | None:
        v = _clean(value)
        return None if v is not None and v.upper().startswith("GB") else v

    cable = _clean_national(next(
        (c.conn_charge_cable for c in samples if c.conn_charge_cable), None))
    brand = _clean(next(
        (c.fast_charger_brand for c in samples if c.fast_charger_brand), None))
    charger_type = _clean_national(next(
        (c.fast_charger_type for c in samples if c.fast_charger_type), None))
    base = _session_item(row)
    return ChargingSessionDetail(
        **base.model_dump(),
        start_rated_range=_fnum(cp.start_rated_range_km),
        end_rated_range=_fnum(cp.end_rated_range_km),
        cable=cable, charger_brand=brand, charger_type=charger_type,
        lat=_fnum(row.address.latitude) if row.address is not None else None,
        lng=_fnum(row.address.longitude) if row.address is not None else None,
        curve=ChargeCurve(
            minutes=[round((c.date - cp.start_date).total_seconds() / 60, 1)
                     for c in samples],
            soc=[c.battery_level for c in samples],
            kw=[_fnum(c.charger_power) for c in samples],
            voltage=[_fnum(c.charger_voltage) for c in samples],
            current=[_fnum(c.charger_actual_current) for c in samples],
            energy=[_fnum(c.charge_energy_added) for c in samples]))


def update_charging_cost(session: Session, session_id: int,
                         cost: float | None) -> CostUpdateResult | None:
    """更新 / 添加 / 清除一条充电记录的费用 (唯一写库点, 金额已由路由校验)。

    返回 None 表示记录不存在。
    """
    process = session.get(ChargingProcess, session_id)
    if process is None:
        return None
    base = float(process.charge_energy_used or 0) \
        or float(process.charge_energy_added or 0)
    process.cost = round(cost, 2) if cost is not None else None
    session.commit()
    price = round(cost / base, 3) if cost is not None and base else None
    return CostUpdateResult(ok=True, cost=cost, price_per_kwh=price)


def _match_region(address: Address | None, path: str) -> bool:
    """充电地点筛选: 地址剥出的省市区对 "/" 路径做逐级匹配。

    段数即精确到哪一级 (1=省 2=市 3=区县), 没给的层不陪绑;
    无地址 / 解析不出省 = 不命中。与地点树、行程页 region_address_ids 同一口径。
    """
    segs = [seg for seg in (t.strip() for t in path.split("/")) if seg]
    if not segs or address is None:
        return False
    region = parse_region(address.display_name or "")
    return region[:len(segs)] == tuple(segs)


def charging_region_tree(session: Session) -> list[RegionNode]:
    """充电地点省→市→区县计数树 (按充电次数降序), 地点级联下拉数据源。

    与行程页同款树 (同一解析器); 解析不出省的地址不进树, 但仍参与列表展示。
    """
    rows = session.execute(
        select(Address.display_name)
        .join(ChargingProcess, ChargingProcess.address_id == Address.id)).all()
    return _acc_region_tree(name for (name,) in rows)


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




def charge_efficiency(session: Session) -> float | None:
    """额定续航 km → 桩端 kWh 换算系数: 充电记录 Σ能量 / Σ续航增量。

    桩端口径 (含充电损耗), 与充电页对账一致 —— 同期 "充了多少" 和 "开了
    多少" 能对上。没有可用充电记录 → None, 前端不显示电耗。"""
    kwh, rng = session.execute(
        select(func.sum(ChargingProcess.charge_energy_added),
               func.sum(ChargingProcess.end_rated_range_km
                        - ChargingProcess.start_rated_range_km))
        .where(ChargingProcess.end_date.is_not(None),
               ChargingProcess.charge_energy_added > 1,
               ChargingProcess.end_rated_range_km.is_not(None),
               ChargingProcess.start_rated_range_km.is_not(None),
               ChargingProcess.end_rated_range_km
               - ChargingProcess.start_rated_range_km > 1)).one()
    if not kwh or not rng or float(rng) <= 0:
        return None
    return float(kwh) / float(rng)
