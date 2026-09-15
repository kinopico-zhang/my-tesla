"""足迹地图: 全量粗轨迹 (增量) 与多行程细节查询

本模块只管 map 域的查询与组装; 通用时间/参数工具在 common.py。
"""
from typing import Any
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import ColumnElement, Select, case, func, or_, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.selectable import Subquery

from ..models import Drive, Position
from .charging import _range_conditions
from .trips import _driver_condition
from .common import BBox, DateRange, fdate
from ..schemas import MapDetailTrack, MapSummary, MapTrack


def map_summary(session: Session, own: Session, date_range: DateRange | None,
                driver_id: int | None = None) -> MapSummary:
    """地图页汇总: 行程数 / 总里程 / 总时长 / 起止日期; 驾驶员同轨迹口径。"""
    conds: list[ColumnElement[bool]] = [Drive.distance.is_not(None)]
    conds += _range_conditions(Drive.start_date, date_range)
    if driver_id is not None:
        conds.append(_driver_condition(own, driver_id))
    count, distance, duration, first, last = session.execute(
        select(func.count(), func.coalesce(func.sum(Drive.distance), 0.0),
               func.coalesce(func.sum(Drive.duration_min), 0),
               func.min(Drive.start_date), func.max(Drive.start_date))
        .where(*conds)).one()
    return MapSummary(
        drives=int(count), distance_km=round(float(distance), 1),
        duration_min=int(duration),
        first_date=fdate(first) if first else None,
        last_date=fdate(last) if last else None)


def drive_max_id(session: Session) -> int:
    """drives 表当前最大有效行程 id (全量轨迹缓存的增量水位)。"""
    return int(session.scalar(
        select(func.max(Drive.id)).where(Drive.distance.is_not(None))) or 0)


MAP_TRACKS_PER_DRIVE = 40


def query_tracks(session: Session, after_id: int) -> list[MapTrack]:
    """全量轨迹增量查询: id > after_id 的有效行程 (distance 非空),
    每段窗口下采样到 MAP_TRACKS_PER_DRIVE 点, 按行程开始时间升序。"""
    inner = _position_window().join(
        Drive, Drive.id == Position.drive_id).where(
        Drive.distance.is_not(None), Drive.id > after_id).subquery()
    stmt = (select(inner.c.drive_id, inner.c.lng, inner.c.lat,
                   Drive.start_date, Drive.distance, Drive.duration_min)
            .join(Drive, Drive.id == inner.c.drive_id)
            .where(_window_keep(inner, MAP_TRACKS_PER_DRIVE))
            .order_by(Drive.start_date, inner.c.drive_id, inner.c.pos_date))
    return _group_map_tracks(session.execute(stmt).all())


def _position_window(
        *extra_conds: ColumnElement[bool]) -> Select[Any]:
    """位置点子查询: 每段内按时间的行号 rn 与总数 cnt (窗口函数双库都支持)。"""
    rn = func.row_number().over(
        partition_by=Position.drive_id, order_by=Position.date).label("rn")
    cnt = func.count().over(partition_by=Position.drive_id).label("cnt")
    stmt = select(
        Position.drive_id.label("drive_id"),
        Position.date.label("pos_date"),
        Position.longitude.label("lng"),
        Position.latitude.label("lat"),
        rn, cnt)
    if extra_conds:
        stmt = stmt.where(*extra_conds)
    return stmt


def _window_keep(inner: Subquery, per: int) -> ColumnElement[bool]:
    """窗口下采样保留条件: 首末点必留, 中间等间隔取点。

    步长必须整除: SA 2.0 的 ``/`` 在 Postgres 方言会 CAST 成 NUMERIC 真除,
    浮点步长让 ``%`` 永远取不到 0 → 中间点全丢 (SQLite 方言不转, 测不出来,
    用方言编译断言守住, 见 test_map)。
    """
    stride = case((inner.c.cnt < per, 1), else_=inner.c.cnt // per)
    return or_(inner.c.rn == 1, inner.c.rn == inner.c.cnt,
               (inner.c.rn - 1) % stride == 0)


def _group_map_tracks(rows: Iterable[Sequence[Any]]) -> list[MapTrack]:
    """行 → 轨迹分组; 少于 2 个点的段丢弃。

    行来自 execute(...).all() (SQLAlchemy Row), 直接按序列解包。
    """
    tracks: list[MapTrack] = []
    cur: MapTrack | None = None
    for drive_id, lng, lat, start_date, distance, duration_min in rows:
        if cur is None or cur.id != drive_id:
            if cur is not None and len(cur.pts) >= 2:
                tracks.append(cur)
            cur = MapTrack(id=drive_id, date=fdate(start_date),
                           km=round(float(distance), 1) if distance else 0.0,
                           min=duration_min, pts=[])
        cur.pts.append([round(float(lng), 5), round(float(lat), 5)])
    if cur is not None and len(cur.pts) >= 2:
        tracks.append(cur)
    return tracks


DETAIL_PER_MAX = 5000
DETAIL_PER_FLOOR = 2000
DETAIL_TOTAL_CAP = 250000
DETAIL_MAX_IDS = 150
DETAIL_WORKERS = 4


def detail_per_for(id_count: int) -> int:
    """视野框明细的每段点数预算: 段数越多预算越少, 有下限与上限。"""
    return max(DETAIL_PER_FLOOR,
               min(DETAIL_PER_MAX, DETAIL_TOTAL_CAP // id_count))


def query_detail(session: Session, id_list: Sequence[int], per: int,
                 bbox: BBox) -> list[MapDetailTrack]:
    """视野框内明细轨迹: bbox 过滤 + 窗口下采样, 按 (行程, 时间) 排序。"""
    inner = _position_window(*_detail_conditions(id_list, bbox)).subquery()
    stmt = (select(inner.c.drive_id, inner.c.lng, inner.c.lat)
            .where(_window_keep(inner, per))
            .order_by(inner.c.drive_id, inner.c.rn))
    tracks: list[MapDetailTrack] = []
    cur: MapDetailTrack | None = None
    for drive_id, lng, lat in session.execute(stmt):
        if cur is None or cur.id != drive_id:
            if cur is not None:
                tracks.append(cur)
            cur = MapDetailTrack(id=drive_id, pts=[])
        cur.pts.append([round(float(lng), 5), round(float(lat), 5)])
    if cur is not None:
        tracks.append(cur)
    return [t for t in tracks if len(t.pts) >= 2]


def _detail_conditions(
        id_list: Sequence[int], bbox: BBox
) -> tuple[ColumnElement[bool], ...]:
    """明细查询的位置点过滤: 指定行程 + 视野框内。"""
    return (Position.drive_id.in_(id_list),
            Position.longitude.between(bbox.west, bbox.east),
            Position.latitude.between(bbox.south, bbox.north))


def query_detail_parallel(factory: sessionmaker[Session],
                          id_list: Sequence[int], per: int,
                          bbox: BBox) -> list[MapDetailTrack]:
    """明细查询并行版: id 按步长切片到 DETAIL_WORKERS 个线程, 结果按 id 排序合并。"""
    chunks = [list(id_list)[i::DETAIL_WORKERS]
              for i in range(DETAIL_WORKERS)]
    chunks = [chunk for chunk in chunks if chunk]
    if len(chunks) <= 1:
        with factory() as session:
            return query_detail(session, id_list, per, bbox)
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        results = list(pool.map(
            _query_detail_chunk,
            [(factory, chunk, per, bbox) for chunk in chunks]))
    merged = {track.id: track for tracks in results for track in tracks}
    return [merged[drive_id] for drive_id in sorted(id_list)
            if drive_id in merged]


def _query_detail_chunk(
        args: tuple[sessionmaker[Session], list[int], int, BBox]
) -> list[MapDetailTrack]:
    factory, chunk, per, bbox = args
    with factory() as session:
        return query_detail(session, chunk, per, bbox)
