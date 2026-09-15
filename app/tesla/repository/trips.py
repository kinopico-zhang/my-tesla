"""行程域: 列表/详情/分组/过路费/驾驶员归集/断档补路/合并轨迹

本模块只管 trips 域的查询与组装; 通用时间/参数工具在 common.py。
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import math
from typing import Any, NamedTuple
from collections.abc import Iterator, Sequence

from sqlalchemy import ColumnElement, Select, delete, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from ..models import (
    Address,
    Drive,
    Driver,
    Position,
    TrackFill,
    TripDriver,
    TripGroup,
    TripToll,
)
from .charging import _range_conditions, charge_efficiency
from .common import (
    DateRange,
    NotFound,
    _acc_region_tree,
    _clean_addr,
    _keep_indices,
    fdate,
    ftime,
    region_address_ids,
)
from ..schemas import (
    GapFillRequest,
    MapTrack,
    MergedTrack,
    RegionNode,
    TripItem,
    TripGroupInfo,
    TripTollIn,
    TripRegions,
    TripTrack,
)


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


def _trip_rows_stmt(start_addr: type[Address],
                    end_addr: type[Address]) -> Select[Any]:
    """行程查询骨架: 只取已结束行程, 带起终点地址 (结束时间降序交给调用方)。"""
    return (select(Drive, start_addr.display_name, end_addr.display_name)
            .join(start_addr, Drive.start_address_id == start_addr.id, isouter=True)
            .join(end_addr, Drive.end_address_id == end_addr.id, isouter=True)
            .where(Drive.end_date.is_not(None)))


def _trip_conditions(session: Session,
                     flt: TripFilter | None) -> list[ColumnElement[bool]]:
    """时间 / 起终地区 / 里程过滤条件 (计数与列表共用)。"""
    conds = _range_conditions(Drive.start_date, flt.date_range if flt else None)
    if flt:
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


def driver_scope(own: Session,
                 driver_id: int) -> tuple[set[int], set[int], bool] | None:
    """按驾驶员筛选的行程 id 口径: (标注它的, 任何标注过的, 是否默认驾驶员)。
    与卡片展示同口径 —— 选默认驾驶员时未标注的也算 (未标注在卡片上就显示
    默认驾驶员名)。驾驶员不存在 → None (调用方按空结果处理)。

    标注表在自有库, 与 TeslaMate 库不是同一个连接 —— 先取 id 集合再下推
    条件 (SQL 端) 或后置过滤 (轨迹缓存端), 不能跨库做子查询。"""
    driver = own.get(Driver, driver_id)
    if driver is None:
        return None
    marked = set(own.scalars(
        select(TripDriver.drive_id).where(TripDriver.driver_id == driver_id)).all())
    all_marked = set(own.scalars(select(TripDriver.drive_id)).all())
    return marked, all_marked, bool(driver.is_default)


def _driver_condition(own: Session, driver_id: int) -> ColumnElement[bool]:
    """按驾驶员筛选 (SQL 端), 口径见 driver_scope。"""
    scope = driver_scope(own, driver_id)
    if scope is None:
        return Drive.id.in_(set())   # 驾驶员不存在 → 空
    marked, all_marked, is_default = scope
    if is_default:
        return or_(Drive.id.in_(marked), Drive.id.not_in(all_marked))
    return Drive.id.in_(marked)


def filter_map_tracks_by_driver(tracks: list[MapTrack], own: Session,
                                driver_id: int) -> list[MapTrack]:
    """缓存轨迹按驾驶员后置过滤 (口径同 _driver_condition)。

    轨迹缓存只从 TeslaMate 库构建, 标注在自有库且会随标/清变动 —— 缓存里
    不落 driver_id, 每次请求现算 id 集合过滤 (全量轨迹在内存, 代价可忽略)。"""
    scope = driver_scope(own, driver_id)
    if scope is None:
        return []
    marked, all_marked, is_default = scope
    return [t for t in tracks
            if t.id in marked or (is_default and t.id not in all_marked)]


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
    eff = charge_efficiency(session)   # 电耗换算: 一页行程共用一次充电记录聚合
    items = [_trip_item(d, s, e, eff) for d, s, e in rows]
    annotate_drivers(own, items)
    annotate_tolls(own, items)
    return int(total), items


def annotate_drivers(own: Session, items: list[TripItem]) -> None:
    """行程条目补驾驶员: 显式标注 > 默认驾驶员兜底 (都没配 = None 不显示)。

    标注指向的驾驶员已被删时按未标注处理 (标注行会随删驾驶员联动清掉,
    这里再兜一层, 库里残留脏行也不致显示错名字)。"""
    if not items:
        return
    drivers = {d.id: d for d in own.scalars(select(Driver)).all()}
    default = next((d for d in drivers.values() if d.is_default), None)
    marks = {m.drive_id: m.driver_id for m in own.scalars(
        select(TripDriver)
        .where(TripDriver.drive_id.in_([i.id for i in items]))).all()}
    for it in items:
        did = marks.get(it.id)
        driver = drivers.get(did) if did is not None else None
        it.driver_id = driver.id if driver is not None else None
        shown = driver or default
        it.driver = shown.name if shown is not None else None


def annotate_tolls(own: Session, items: list[TripItem]) -> None:
    """行程条目补高速费估价 (算过的才有, 没算过保持 None)。"""
    if not items:
        return
    rows = own.scalars(select(TripToll).where(
        TripToll.drive_id.in_([i.id for i in items]))).all()
    by_id = {r.drive_id: r for r in rows}
    for it in items:
        row = by_id.get(it.id)
        if row is not None:
            it.toll = row.tolls
            it.toll_km = row.toll_km


def save_trip_toll(own: Session, drive_id: int, body: TripTollIn) -> None:
    """存/更新一条行程的高速费估价 (算过重算 = 覆盖)。"""
    row = own.scalars(select(TripToll).where(TripToll.drive_id == drive_id)).first()
    if row is None:
        row = TripToll(drive_id=drive_id)
        own.add(row)
    row.tolls = body.tolls
    row.toll_km = body.toll_km
    row.distance = body.distance
    row.roads = json.dumps([r.model_dump() for r in body.roads],
                           ensure_ascii=False, separators=(",", ":"))
    own.commit()


def set_trip_driver(own: Session, drive_id: int, driver_id: int | None) -> None:
    """标/清行程驾驶员 (清 = 删标注行, 展示回默认兜底)。"""
    if driver_id is not None and own.get(Driver, driver_id) is None:
        raise NotFound("驾驶员不存在")
    own.execute(delete(TripDriver).where(TripDriver.drive_id == drive_id))
    if driver_id is not None:
        own.add(TripDriver(drive_id=drive_id, driver_id=driver_id))
    own.commit()




def _region_tree(session: Session,
                 address_id: InstrumentedAttribute[int | None]) -> list[RegionNode]:
    """某个地址角色 (起点/终点) 的省→市→区县计数树 (次数降序, 未结束行程不计)。"""
    addr = aliased(Address)
    rows = session.execute(
        select(addr.display_name)
        .select_from(Drive)
        .join(addr, address_id == addr.id, isouter=True)
        .where(Drive.end_date.is_not(None))).all()
    return _acc_region_tree(name for (name,) in rows)


def list_trip_regions(session: Session) -> TripRegions:
    """行程起终点省市区树 (级联下拉数据源)。"""
    return TripRegions(
        start=_region_tree(session, Drive.start_address_id),
        end=_region_tree(session, Drive.end_address_id))


def get_trip(session: Session, own: Session, drive_id: int) -> TripItem | None:
    """单条行程 (未结束 / 不存在返回 None)。"""
    rows = session.execute(
        _trip_rows_stmt(aliased(Address), aliased(Address))
        .where(Drive.id == drive_id)).all()
    if not rows:
        return None
    item = _trip_item(rows[0][0], rows[0][1], rows[0][2],
                      charge_efficiency(session))
    annotate_drivers(own, [item])
    annotate_tolls(own, [item])
    return item


TRIP_TRACK_PER = 5000

# 断档补路 (隧道/信号丢失): 原始采样不动, 补出来的点全部存自有库,
# 轨迹接口在服务端拼好 —— 所有消费方都不再看到断档, 前端也不用每次
# 重新调高德规划。own 参数即自有库会话 (与 TeslaMate 会话隔离)。

EARTH_RADIUS_KM = 6371.0
GAP_ANCHOR_MAX_KM = 0.15   # 断档端点离真实轨迹点多近才算锚上 (规划结果与采样本就有几十米差)


def _wgs_km(a: Sequence[float], b: Sequence[float]) -> float:
    """两个 WGS [lng, lat] 点的近似球面距离 (等距圆柱投影, 与前端
    TrackUtil.ptDistKm 同口径)。"""
    mid_lat = math.radians((a[1] + b[1]) / 2)
    dx = math.radians(b[0] - a[0]) * math.cos(mid_lat)
    dy = math.radians(b[1] - a[1])
    return EARTH_RADIUS_KM * math.hypot(dx, dy)


class _TrackPoint(NamedTuple):
    """轨迹点 (原始采样或补路插入), 合并轨迹按 drive_id 分段。"""

    drive_id: int
    date: datetime
    lng: float
    lat: float
    speed: float
    power: float | None


def _interpolated_fill(a: Position, b: Position,
                       path: list[list[float]]) -> list[_TrackPoint]:
    """补路折线 → 插值后的轨迹点 (date 按弧长比例落在两锚点间, speed
    在两锚点速度间线性, power 置 None —— 推算值不冒充实测)。

    高德路线的首尾就是断档端点本身, 与锚点重合的去掉, 不然轨迹出现重复点。"""
    # 弧长参数: 锚点 a → path → 锚点 b
    chain = [[a.longitude, a.latitude], *path, [b.longitude, b.latitude]]
    cum = [0.0]
    for i in range(1, len(chain)):
        cum.append(cum[-1] + _wgs_km(chain[i - 1], chain[i]))
    total = cum[-1]
    frac = [(cum[i + 1] / total if total else 0.0) for i in range(len(path))]
    span = (b.date - a.date).total_seconds()
    speed_a, speed_b = a.speed or 0.0, b.speed or 0.0
    anchors = {(round(a.longitude, 5), round(a.latitude, 5)),
               (round(b.longitude, 5), round(b.latitude, 5))}
    return [_TrackPoint(
        a.drive_id,
        a.date + timedelta(seconds=span * f),
        round(float(lng), 5), round(float(lat), 5),
        round(speed_a + (speed_b - speed_a) * f, 1), None)
        for (lng, lat), f in zip(path, frac)
        if (round(float(lng), 5), round(float(lat), 5)) not in anchors]


def _fill_points(own: Session,
                 positions: Sequence[Position]) -> dict[int, list[_TrackPoint]]:
    """读自有库断档补路, 按 a_pos_id 返回待插入的补路点。

    锚点行不在本次轨迹里 (理论上不会发生) 就整条跳过。"""
    drive_ids = sorted({p.drive_id for p in positions})
    fills = own.scalars(
        select(TrackFill).where(TrackFill.drive_id.in_(drive_ids))).all()
    by_id = {p.id: p for p in positions}
    out: dict[int, list[_TrackPoint]] = {}
    for fill in fills:
        a, b = by_id.get(fill.a_pos_id), by_id.get(fill.b_pos_id)
        if a is None or b is None or a.date >= b.date:
            continue
        try:
            path = json.loads(fill.path)
        except ValueError:
            continue
        pts = _interpolated_fill(a, b, path)
        if pts:
            out[fill.a_pos_id] = pts
    return out


def _track_points(own: Session, positions: Sequence[Position]
                  ) -> tuple[list[_TrackPoint], set[int]]:
    """原始轨迹点 + 自有库补路点 (按日期归并, 时间序保持)。

    返回 (points, fill_indices): 补路点在 points 里的下标集合 —— 它们
    本就稀疏珍贵, 下采样时全部保留, 不能被等间隔抽掉 (抽掉等于白补)。
    """
    pts = [_TrackPoint(p.drive_id, p.date, round(float(p.longitude), 5),
                       round(float(p.latitude), 5), p.speed or 0.0, p.power)
           for p in positions]
    fills = _fill_points(own, positions)
    if not fills:
        return pts, set()
    # 补路点不能直接插到锚点后面: 锚点是客户端按它收到的 (下采样) 视图挑的,
    # a/b 两点在原始流里未必相邻 —— 锚点区间内夹着的原始点会整块落到补路点
    # 之后, 日期回退把 ts 打乱 (合并视图与单条视图的采样口径不同必踩)。
    # 按日期稳定归并 (原始点本就有序, 同刻时原始点在前), 任意视图都单调。
    extras: list[_TrackPoint] = [tp for seg in fills.values() for tp in seg]
    extra_ids = {id(tp) for tp in extras}
    pts = sorted([*pts, *extras], key=lambda tp: tp.date)
    return pts, {i for i, tp in enumerate(pts) if id(tp) in extra_ids}


def _nearest_position(positions: Sequence[Position],
                      pt: Sequence[float]) -> int:
    """离 pt (WGS [lng, lat]) 最近的 positions 行下标。"""
    best, best_d = 0, float("inf")
    for i, p in enumerate(positions):
        d = _wgs_km([p.longitude, p.latitude], pt)
        if d < best_d:
            best, best_d = i, d
    return best


def _anchor_km(positions: Sequence[Position], idx: int,
               pt: Sequence[float]) -> float:
    """positions[idx] 到锚定候选点 pt 的距离 (km)。"""
    p = positions[idx]
    return _wgs_km([p.longitude, p.latitude], pt)


FILL_STEP_KM = 0.08   # 补路折线加密步长 (80m): 高德路径顶点可相距数百米
                      # (长直道只给两个端点), 原样入库拼进轨迹后相邻点仍超
                      # 断档识别阈值 (最低 160m), 会被再拆成断档无限重规划


def _densify(path: list[list[float]]) -> list[list[float]]:
    """折线相邻顶点间按 FILL_STEP_KM 线性插值加密。

    顶点之间本就是直线段 (高德路径是多段折线), 插值不引入任何虚构几何;
    加密后相邻点恒 < 80m, 任何下采样密度下都不再被识别成断档。"""
    out = [path[0]]
    for i in range(1, len(path)):
        lng0, lat0 = path[i - 1]
        lng1, lat1 = path[i]
        n = int(_wgs_km(path[i - 1], path[i]) / FILL_STEP_KM)
        for k in range(1, n + 1):
            r = k / (n + 1)
            out.append([round(lng0 + (lng1 - lng0) * r, 5),
                        round(lat0 + (lat1 - lat0) * r, 5)])
        out.append(path[i])
    return out


def save_fill(session: Session, own: Session,
              req: GapFillRequest) -> float:
    """把前端回传的断档补路锚定到原始 positions 行并存入自有库。

    a/b 各自锚到最近的采样点; 里程按回传 path 在服务端实算 (不信前端)。
    同一断档重复回传 = 覆盖更新 (按 a_pos_id 唯一)。
    """
    positions = session.scalars(
        select(Position).where(Position.drive_id == req.drive_id)
        .order_by(Position.date)).all()
    if len(positions) < 2:
        raise NotFound("该行程没有轨迹数据")
    ia = _nearest_position(positions, req.a)
    ib = _nearest_position(positions, req.b)
    if (_anchor_km(positions, ia, req.a) > GAP_ANCHOR_MAX_KM
            or _anchor_km(positions, ib, req.b) > GAP_ANCHOR_MAX_KM):
        raise ValueError("断档端点偏离轨迹超过 150 米")
    if ia >= ib or ib - ia > 50:
        raise ValueError("断档端点锚定失败 (先后顺序或跨度异常)")
    a, b = positions[ia], positions[ib]
    if a.date >= b.date:
        raise ValueError("断档端点锚定失败 (时间顺序异常)")
    path = _densify([[round(p[0], 5), round(p[1], 5)] for p in req.path])
    km = sum(_wgs_km(path[i - 1], path[i]) for i in range(1, len(path)))
    own.execute(delete(TrackFill).where(TrackFill.a_pos_id == a.id))
    own.add(TrackFill(drive_id=req.drive_id, a_pos_id=a.id, b_pos_id=b.id,
                      path=json.dumps(path, separators=(",", ":")),
                      km=round(km, 3), source="amap"))
    own.commit()
    return round(km, 3)


def trip_track(session: Session, own: Session, drive_id: int) -> TripTrack:
    """单条行程轨迹 (含速度/功耗), 下采样到 TRIP_TRACK_PER 点。

    自有库里的断档补路先拼进原始轨迹再下采样, 前端拿到的就是
    沿真实道路的连续轨迹 (无需再客户端补路)。
    """
    positions = session.scalars(
        select(Position).where(Position.drive_id == drive_id)
        .order_by(Position.date)).all()
    if len(positions) < 2:
        raise NotFound("该行程没有轨迹数据")
    pts_all, fill_idx = _track_points(own, positions)
    # 补路点全保留: 它们是整段稀疏折线, 被等间隔抽掉一点就重新露出断档
    keep = set(_keep_indices(len(pts_all), TRIP_TRACK_PER)) | fill_idx
    kept = [pts_all[i] for i in sorted(keep)]
    t0 = kept[0].date
    return TripTrack(
        id=drive_id,
        pts=[[p.lng, p.lat, p.speed, p.power] for p in kept],
        ts=[int(round((p.date - t0).total_seconds())) for p in kept])


MERGED_TRACK_BUDGET = 12000   # 多段合并的总点数预算, 按各段原始点数占比分配
MERGED_TRACK_PER_MIN = 200


@dataclass
class MergedPlan:
    """合并轨迹的头部汇总与各段下采样预算 (流式接口: 头部先行, 逐段跟上)。"""

    header: MergedTrack        # pts/ts/seg_starts 为空, 其余字段齐
    id_list: list[int]         # 按出发时间升序的行程 id
    budgets: dict[int, int]    # drive_id → 该段保留点数上限


def merged_track(session: Session, own: Session,
                 ids: Sequence[int]) -> MergedTrack:
    """多段行程合并成一条连续轨迹 (整包 JSON)。

    - ids 必须都是已结束行程, 否则 NotFound("包含不存在或未完成的行程");
    - ts 为累计行驶秒, 行程之间的停驶时段被剔除;
    - 各段按原始点数占比分享总预算下采样 (见 merged_track_plan);
    - 各段的断档补路同样在服务端拼好 (见 _track_points);
    - 逐段流式版本见 merged_track_segments (前端边下边播用)。
    """
    plan = merged_track_plan(session, ids)
    pts: list[list[float | None]] = []
    ts: list[int] = []
    seg_starts: list[int] = []
    for seg_pts, seg_ts in merged_track_segments(session, own, plan):
        seg_starts.append(len(pts))
        pts += seg_pts
        ts += seg_ts
    if len(pts) < 2:
        raise NotFound("这些行程没有轨迹数据")
    plan.header.pts = pts
    plan.header.ts = ts
    plan.header.seg_starts = seg_starts
    return plan.header


def merged_track_plan(session: Session, ids: Sequence[int]) -> MergedPlan:
    """校验 ids (须全为已结束行程) 并算好汇总头 + 各段下采样预算。"""
    drive_rows = session.execute(
        _trip_rows_stmt(aliased(Address), aliased(Address))
        .where(Drive.id.in_(ids))
        .order_by(Drive.start_date)).all()
    if len(drive_rows) != len(set(ids)):
        raise NotFound("包含不存在或未完成的行程")
    id_list = [d.id for d, _, _ in drive_rows]
    counts: dict[int, int] = {
        int(did): int(cnt) for did, cnt in session.execute(
            select(Position.drive_id, func.count())
            .where(Position.drive_id.in_(id_list))
            .group_by(Position.drive_id)).all()}
    total = sum(counts.values())
    budgets = ({did: max(MERGED_TRACK_PER_MIN,
                         round(MERGED_TRACK_BUDGET * cnt / total))
                for did, cnt in counts.items()} if total else {})
    first, last = drive_rows[0][0], drive_rows[-1][0]
    eff = charge_efficiency(session)
    raw_kwh = sum(_consumption(d, eff)[0] or 0.0 for d, _, _ in drive_rows)
    total_km = sum(float(d.distance or 0) for d, _, _ in drive_rows)
    header = MergedTrack(
        ids=id_list, n=len(id_list), pts=[], ts=[], seg_starts=[],
        date=fdate(first.start_date), start=ftime(first.start_date),
        end=ftime(last.end_date) if last.end_date else None,
        km=round(total_km, 2),
        min=sum(d.duration_min or 0 for d, _, _ in drive_rows),
        speed_max=max((d.speed_max or 0) for d, _, _ in drive_rows) or None,
        kwh=round(raw_kwh, 1) if eff is not None else None,
        wh_per_km=(round(raw_kwh / total_km * 1000)
                   if eff is not None and total_km >= 1 else None),
        from_=_clean_addr(drive_rows[0][1]),
        to=_clean_addr(drive_rows[-1][2]))
    return MergedPlan(header, id_list, budgets)


def merged_track_segments(session: Session, own: Session, plan: MergedPlan
                          ) -> Iterator[tuple[list[list[float | None]], list[int]]]:
    """逐段产出 (pts, ts): ts 为跨段累计行驶秒 (行程间停驶剔除)。

    每段独立查询/下采样: 流式接口一段一段往外发, 前端拿到第一段就能
    开播, 不必等几十 MB 全下完; 断档补路已在段内拼好。
    """
    base = 0.0
    for did in plan.id_list:
        positions = session.scalars(
            select(Position).where(Position.drive_id == did)
            .order_by(Position.date)).all()
        points, fill_idx = _track_points(own, positions)
        if not points:
            continue
        # 补路点全保留 (理由同 trip_track), 只对原始点做等间隔下采样
        keep = set(_keep_indices(len(points),
                                 plan.budgets.get(did, MERGED_TRACK_PER_MIN))) \
            | fill_idx
        seg_pts: list[list[float | None]] = []
        seg_ts: list[int] = []
        t0 = _utc_seconds(points[0].date)   # 段首 (keep_indices 首点必留)
        prev_stamp = t0
        for i, tp in enumerate(points):
            if i not in keep:
                continue
            stamp = _utc_seconds(tp.date)
            prev_stamp = stamp
            seg_pts.append([tp.lng, tp.lat, tp.speed, tp.power])
            seg_ts.append(int(round(base + stamp - t0)))
        base += prev_stamp - t0    # 段行驶时长并入累计 (最后保留点 - 段首)
        if seg_pts:
            yield seg_pts, seg_ts


def closed_drive_ids_between(session: Session, first: int, last: int) -> list[int]:
    """头尾 id 区间内全部已结束行程的 id (升序; 与行程列表同口径)。

    连续行程的分享链接只记头尾 id, 服务端按区间展开成完整列表 ——
    区间里被过滤掉的未结束行程 (TeslaMate 记录中断残留) 自动跳过。"""
    rows = session.execute(
        select(Drive.id)
        .where(Drive.id >= first, Drive.id <= last,
               Drive.end_date.is_not(None))
        .order_by(Drive.id)).all()
    return [int(r[0]) for r in rows]


_EPOCH = datetime(1970, 1, 1)


def _utc_seconds(dt: datetime) -> float:
    """UTC 裸时间戳 → epoch 秒 (直接做差, 不做时区解释)。"""
    return (dt - _EPOCH).total_seconds()


def _group_rows(session: Session, ids: Sequence[int]) -> list[Drive]:
    """按当前行程库取分组里的行程 (只认已结束行程, 与列表同口径)。"""
    return list(session.scalars(
        select(Drive)
        .where(Drive.id.in_(ids), Drive.end_date.is_not(None))
        .order_by(Drive.start_date)).all())


def _group_ids(group: TripGroup) -> list[int]:
    """分组存库的逗号串 → id 列表。"""
    return [int(x) for x in group.ids.split(",")]


def _group_info(session: Session, group: TripGroup) -> TripGroupInfo:
    """分组条目: 段数/里程/日期跨度按当前数据现算 (行程可能已被改动)。"""
    drives = _group_rows(session, _group_ids(group))
    km = round(sum(float(d.distance or 0) for d in drives), 1)
    dates = [fdate(d.start_date) for d in drives]
    span = dates[0] if len(set(dates)) == 1 else f"{dates[0]}~{dates[-1]}" \
        if dates else ""
    return TripGroupInfo(
        id=group.id, name=group.name, ids=_group_ids(group),
        n=len(drives), km=km, span=span)


def list_trip_groups(session: Session, own: Session) -> list[TripGroupInfo]:
    """全部分组 (最新存的前面)。"""
    groups = list(own.scalars(select(TripGroup).order_by(TripGroup.id.desc())))
    return [_group_info(session, g) for g in groups]


def save_trip_group(session: Session, own: Session,
                    name: str, ids: Sequence[int]) -> TripGroupInfo:
    """存分组: ids 升序去重后落库; 含无效行程 (不存在/未结束) 则拒绝。"""
    unique = sorted(set(ids))
    rows = _group_rows(session, unique)
    if len(rows) != len(unique):
        raise NotFound("包含不存在或未结束的行程")
    group = TripGroup(name=name, ids=",".join(str(i) for i in unique))
    own.add(group)
    own.commit()
    return _group_info(session, group)


def rename_trip_group(session: Session, own: Session,
                      group_id: int, name: str) -> TripGroupInfo:
    """分组改名 (成员不动)。"""
    group = own.get(TripGroup, group_id)
    if group is None:
        raise NotFound("分组不存在")
    group.name = name
    own.commit()
    return _group_info(session, group)


def delete_trip_group(own: Session, group_id: int) -> None:
    """删分组 (只删自有库记录, 行程原数据不动)。"""
    group = own.get(TripGroup, group_id)
    if group is None:
        raise NotFound("分组不存在")
    own.delete(group)
    own.commit()
