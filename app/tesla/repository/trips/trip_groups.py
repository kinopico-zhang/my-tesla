"""轨迹分组: 多选行程存成命名分组 (逻辑分组, TeslaMate 原库不动),
段数/里程/日期跨度按当前行程数据现算。
"""
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Drive, TripGroup
from ..charging import charge_efficiency
from ..common import NotFound, ftime, to_local
from ...schemas import TripGroupInfo
from .trip_listing import _consumption


def _group_rows(session: Session, ids: Sequence[int]) -> list[Drive]:
    """按当前行程库取分组里的行程 (只认已结束行程, 与列表同口径)。"""
    return list(session.scalars(
        select(Drive)
        .where(Drive.id.in_(ids), Drive.end_date.is_not(None))
        .order_by(Drive.start_date)).all())


def _group_ids(group: TripGroup) -> list[int]:
    """分组存库的逗号串 → id 列表。"""
    return [int(x) for x in group.ids.split(",")]


def _group_info(session: Session, group: TripGroup,
                effs: dict[int, float | None] | None = None) -> TripGroupInfo:
    """分组条目: 段数/里程/日期跨度按当前数据现算 (行程可能已被改动);
    起止/时长/最高速/电耗汇总与合并播放的流式汇总头同口径 —— 分组页
    一打开弹层数字带就显数, 不等地图加载 (2026-09-23 用户点名「平均
    电耗空着, 加载完地图才显示」)。effs 跨分组共用一份换算系数 (每车
    只查一次, 列表页一组一段查会放大到几十次)。"""
    drives = _group_rows(session, _group_ids(group))
    km = round(sum(float(d.distance or 0) for d in drives), 1)
    # 跨度日期用紧凑斜杠写法 (2026/09/09, 2026-09-25 用户点名「还是显示不
    # 全, 日期用这种紧凑写法」): 比连字符窄一档, 斜杠还是干净的断行点 ——
    # 前端格子里装不下按 / 换行, 保底显示全
    dates = [to_local(d.start_date).strftime("%Y/%m/%d") for d in drives]
    span = dates[0] if len(set(dates)) == 1 else f"{dates[0]}~{dates[-1]}" \
        if dates else ""
    car_ids = {d.car_id for d in drives}
    if effs is None:
        effs = {}
    for cid in car_ids:                      # 同一口径: Σ(续航差×换算系数)÷总里程
        if cid not in effs:
            effs[cid] = charge_efficiency(session, cid)
    raw_kwh = sum(_consumption(d, effs.get(d.car_id))[0] or 0.0 for d in drives)
    total_km = sum(float(d.distance or 0) for d in drives)
    has_eff = any(effs.get(cid) for cid in car_ids)
    return TripGroupInfo(
        id=group.id, name=group.name, ids=_group_ids(group),
        n=len(drives), km=km, span=span,
        start=ftime(drives[0].start_date) if drives else None,
        end=ftime(drives[-1].end_date) if drives and drives[-1].end_date else None,
        min=sum(d.duration_min or 0 for d in drives) or None,
        speed_max=max((d.speed_max or 0) for d in drives) or None if drives
        else None,
        kwh=round(raw_kwh, 1) if has_eff else None,
        wh_per_km=(round(raw_kwh / total_km * 1000)
                   if has_eff and total_km >= 1 else None))


def list_trip_groups(session: Session, own: Session) -> list[TripGroupInfo]:
    """全部分组 (最新存的前面; 换算系数跨分组共用一份)。"""
    groups = list(own.scalars(select(TripGroup).order_by(TripGroup.id.desc())))
    effs: dict[int, float | None] = {}
    return [_group_info(session, g, effs) for g in groups]


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
