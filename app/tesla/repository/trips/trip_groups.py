"""轨迹分组: 多选行程存成命名分组 (逻辑分组, TeslaMate 原库不动),
段数/里程/日期跨度按当前行程数据现算。
"""
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Drive, TripGroup
from ..common import NotFound, fdate
from ...schemas import TripGroupInfo


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
