"""足迹地图: 全精度全量轨迹 (增量) 与清单组装

本模块只管 map 域的查询与组装; 通用时间/参数工具在 common.py。
粗/细渲染的抽稀不再服务端做 (v4 起全精度下发, 客户端本地抽稀)。
"""
from collections.abc import Iterable, Sequence
from itertools import chain
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from ..models import Drive, Position
from .charging import _range_conditions
from .trips import _driver_condition
from .common import DateRange, fdate
from ..schemas import MapSummary, MapTrack


def map_summary(session: Session, own: Session, date_range: DateRange | None,
                driver_id: int | None = None,
                car_id: int | None = None) -> MapSummary:
    """地图页汇总: 行程数 / 总里程 / 总时长 / 起止日期; 驾驶员/车辆同轨迹口径。"""
    conds: list[ColumnElement[bool]] = [Drive.distance.is_not(None)]
    conds += _range_conditions(Drive.start_date, date_range)
    if driver_id is not None:
        conds.append(_driver_condition(own, driver_id))
    if car_id is not None:
        conds.append(Drive.car_id == car_id)
    count, distance, duration, first, last = session.execute(
        select(func.count(), func.coalesce(func.sum(Drive.distance), 0.0),
               func.coalesce(func.sum(Drive.duration_min), 0),
               func.min(Drive.start_date), func.max(Drive.start_date))
        .where(*conds)).one()
    return MapSummary(
        drives=int(count), distance_km=round(float(distance or 0.0), 1),
        duration_min=int(duration or 0),
        first_date=fdate(first) if first else None,
        last_date=fdate(last) if last else None)


def drive_max_id(session: Session) -> int:
    """drives 表当前最大有效行程 id (全量轨迹缓存的增量水位)。"""
    return int(session.scalar(
        select(func.max(Drive.id)).where(Drive.distance.is_not(None))) or 0)


def query_tracks(session: Session, after_id: int) -> list[MapTrack]:
    """全精度全量轨迹增量查询: id > after_id 的有效行程 (distance 非空),
    不抽稀 (客户端下载后本地抽稀渲染), 按行程开始时间升序。

    轨迹带 car_id (缓存是全车合存的, 车辆筛选在客户端清单侧做)。
    流式分块取行 (stream_results + partitions): 全量上百万行一次性
    .all() 会把 Row 全部物化, 小内存 NAS 直接 swap 颠簸假死。"""
    stmt = (select(Position.drive_id, Position.longitude, Position.latitude,
                   Drive.start_date, Drive.distance, Drive.duration_min,
                   Drive.car_id)
            .join(Drive, Drive.id == Position.drive_id)
            .where(Drive.distance.is_not(None), Drive.id > after_id)
            .order_by(Drive.start_date, Position.drive_id, Position.date)
            .execution_options(stream_results=True))
    result = session.execute(stmt)
    return _group_map_tracks(chain.from_iterable(result.partitions(20_000)))


def _group_map_tracks(rows: Iterable[Sequence[Any]]) -> list[MapTrack]:
    """行 → 轨迹分组; 少于 2 个点的段丢弃; pts 扁平 [lng, lat, ...]。

    行来自 execute(...).all() (SQLAlchemy Row), 直接按序列解包。
    """
    tracks: list[MapTrack] = []
    cur: MapTrack | None = None
    for drive_id, lng, lat, start_date, distance, duration_min, car_id in rows:
        if cur is None or cur.id != drive_id:
            if cur is not None and len(cur.pts) >= 4:
                tracks.append(cur)
            cur = MapTrack(id=drive_id, car_id=car_id, date=fdate(start_date),
                           km=round(float(distance), 1) if distance else 0.0,
                           min=duration_min, pts=[])
        cur.pts.extend((round(float(lng), 5), round(float(lat), 5)))
    if cur is not None and len(cur.pts) >= 4:
        tracks.append(cur)
    return tracks
