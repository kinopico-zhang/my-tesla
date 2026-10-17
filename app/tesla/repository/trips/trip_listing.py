"""行程列表与单条: 条目组装/过滤条件 (时间/地区/里程/驾驶员)/起终点地区树。"""
from typing import Any

from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from ...models import Address, Drive
from ...place_naming import render_place
from ...place_tpl_store import place_tpl_values
from .trip_marks import _driver_condition, annotate_drivers, annotate_tolls
from ..charging import _range_conditions, charge_efficiency
from ..common import DateRange, _clean_addr, fdate, ftime
from ..place_names import PlaceInfo, place_info_map
from ..region_tree import (_acc_triple_tree, amap_chain, amap_full,
                           region_address_ids, region_chain, resolve_region)
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


def _trip_item(drive: Drive, start_addr: Address | None,
               end_addr: Address | None, eff: float | None = None,
               amap: dict[int, PlaceInfo] | None = None,
               tpl: str = "") -> TripItem:
    """条目组装: from/to 是清洗后的整链 (播放会话还在用), from_region/
    from_loc 等是省市区链 + 地名 —— 前端配 fmtPlaceShort 取最小两段
    (用户点名: 卡片起终点与充电列表同款「区 · 地名」)。

    省市区/地名高德优先 (amap = 地址 id → 高德缓存行; TeslaMate 的 OSM
    反查语言/覆盖不可信, 2026-10-14 地名高德化), 没刷到/境外的逐址回退
    TeslaMate —— 后台慢慢刷, 刷好一址换一址。tpl = 地点显示模板 (空/
    渲染空 → place 字段 None, 前端走老拼装)。"""
    amap = amap or {}
    kwh, wh_per_km = _consumption(drive, eff)
    s_info = amap.get(start_addr.id) if start_addr else None
    e_info = amap.get(end_addr.id) if end_addr else None
    return TripItem(
        id=drive.id, date=fdate(drive.start_date),
        start=ftime(drive.start_date),
        end=ftime(drive.end_date) if drive.end_date else None,
        km=round(float(drive.distance), 2) if drive.distance is not None else None,
        min=drive.duration_min, speed_max=drive.speed_max,
        from_=(amap_full(s_info)
               or _clean_addr(start_addr.display_name if start_addr else None)),
        to=(amap_full(e_info)
            or _clean_addr(end_addr.display_name if end_addr else None)),
        from_region=((amap_chain(s_info)
                      or region_chain(start_addr.display_name))
                     if start_addr else None),
        from_loc=((s_info.name if s_info else None)
                  or (start_addr.name or None)) if start_addr else None,
        to_region=((amap_chain(e_info)
                    or region_chain(end_addr.display_name))
                   if end_addr else None),
        to_loc=((e_info.name if e_info else None)
                or (end_addr.name or None)) if end_addr else None,
        from_place=render_place(tpl, s_info) or None,   # 模板整行 (to_place 同)
        to_place=render_place(tpl, e_info) or None, kwh=kwh, wh_per_km=wh_per_km)


class TripFilter(BaseModel):
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
                    end_addr: type[Address]) -> Select[*tuple[Any, ...]]:
    """行程查询骨架: 只取已结束行程, 带起终点地址实体 (整链清洗与省市区
    链/地名都要, display_name 单列不够用; 结束时间降序交给调用方)。"""
    return (select(Drive, start_addr, end_addr)
            .join(start_addr, Drive.start_address_id == start_addr.id, isouter=True)
            .join(end_addr, Drive.end_address_id == end_addr.id, isouter=True)
            .where(Drive.end_date.is_not(None)))


def _trip_conditions(session: Session, own: Session,
                     flt: TripFilter | None) -> list[ColumnElement[bool]]:
    """时间 / 起终地区 / 里程 / 车辆过滤条件 (计数与列表共用)。"""
    conds = _range_conditions(Drive.start_date, flt.date_range if flt else None)
    if flt:
        if flt.car_id is not None:
            conds.append(Drive.car_id == flt.car_id)
        if flt.from_loc:
            conds.append(Drive.start_address_id.in_(
                region_address_ids(session, own, flt.from_loc)))
        if flt.to_loc:
            conds.append(Drive.end_address_id.in_(
                region_address_ids(session, own, flt.to_loc)))
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
    conds = _trip_conditions(session, own, flt)
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
    amap = place_info_map(own, {a.id for _, s, e in rows for a in (s, e) if a})
    tpl = place_tpl_values(own)[0]   # 行程起终点模板 (空 = 不套)
    items = [_trip_item(d, s, e, effs.get(d.car_id), amap, tpl)
             for d, s, e in rows]
    annotate_drivers(own, items)
    annotate_tolls(own, items)
    return int(total), items


def _region_tree(session: Session, own: Session,
                 address_id: InstrumentedAttribute[int | None],
                 car_id: int | None = None) -> list[RegionNode]:
    """某个地址角色 (起点/终点) 的省→市→区县计数树 (次数降序, 未结束行程
    不计); 三级高德优先, 没刷到的逐址回退 TeslaMate 链解析。"""
    addr = aliased(Address)
    stmt = (select(addr.id, addr.display_name)
            .select_from(Drive)
            .join(addr, address_id == addr.id, isouter=True)
            .where(Drive.end_date.is_not(None)))
    if car_id is not None:
        stmt = stmt.where(Drive.car_id == car_id)
    rows = session.execute(stmt).all()
    amap = place_info_map(own, [aid for aid, _ in rows if aid])
    return _acc_triple_tree(resolve_region(amap.get(aid), name)
                            for aid, name in rows)


def list_trip_regions(session: Session, own: Session,
                      car_id: int | None = None) -> TripRegions:
    """行程起终点省市区树 (级联下拉数据源); car_id 选定时只数那台车的行程。"""
    return TripRegions(
        start=_region_tree(session, own, Drive.start_address_id, car_id),
        end=_region_tree(session, own, Drive.end_address_id, car_id))


def drive_open(session: Session, drive_id: int) -> bool:
    """该行程是否还在进行中 (end_date 空; 主键一查)。

    单条轨迹接口的缓存口径用 (路由侧 trip_tracks): 已结束行程 positions
    不可变, 挂 ETag 安全; 进行中的行程 positions 一直在长, ETag 分量
    (盐值/id/补路版本) 却不随之变 —— 状态页驾驶态 20s 重拉全被 304 成
    打开时刻的旧缓存 (2026-09-27 用户实报: 轨迹终点冻住, 车位与它之间
    被尾巴线拉成一条直线)。"""
    d = session.get(Drive, drive_id)
    return d is not None and d.end_date is None


def get_trip(session: Session, own: Session, drive_id: int) -> TripItem | None:
    """单条行程 (未结束 / 不存在返回 None); 电耗按该车自己的充电定标。"""
    rows = session.execute(
        _trip_rows_stmt(aliased(Address), aliased(Address))
        .where(Drive.id == drive_id)).all()
    if not rows:
        return None
    drive = rows[0][0]
    amap = place_info_map(own, {a.id for _, s, e in rows for a in (s, e) if a})
    item = _trip_item(drive, rows[0][1], rows[0][2],
                      charge_efficiency(session, drive.car_id), amap,
                      place_tpl_values(own)[0])   # 起终点模板
    annotate_drivers(own, [item])
    annotate_tolls(own, [item])
    return item
