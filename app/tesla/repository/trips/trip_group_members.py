"""分组明细: 组内行程窗口与批量改成员 (分组 = 连续区间)。

区间口径与合并播放一致 (分享链接只记「首-尾」, 服务端按区间展开全部已
结束行程): 加一段 = 区间外延到该行程, 中间的已结束行程整段吸收 —— 连续
性靠构造保证, 不可能挖出洞; 移一段 = 只许收头尾 (中间挖洞会断开)。
窗口按 id 升序 (id 即行程落库序, 与出发序一致), 组内行 in_group=true,
组外候选行也一并给 (前端降透明画 + 加标记钮, 拉动加载沿两端翻页)。
改成员是「先标记后确认」的整批提交 (前端点行只是预览标记, 确认才发)。
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from ...models import Address, Drive, TripGroup
from ...schemas import GroupMemberUpdate, GroupTripsPage, GroupTripRow
from ...place_tpl_store import place_tpl_values
from ..common import NotFound
from ..place_names import place_info_map
from .trip_groups import _group_ids, _group_info
from .trip_listing import _eff_by_car, _trip_item, _trip_rows_stmt
from .trip_tracks import closed_drive_ids_between


def _stored_range(group: TripGroup) -> tuple[int, int]:
    """分组存库 ids 的首尾 (区间定义; 写库方恒存升序全展开, min/max 兜底)。"""
    ids = _group_ids(group)
    return min(ids), max(ids)


def _closed_before(session: Session, edge: int | None) -> bool:
    """edge 之前还有没有已结束行程 (两端「还有更多」旗标; 空 edge = 没有)。"""
    if edge is None:
        return False
    return session.scalar(
        select(Drive.id).where(Drive.end_date.is_not(None), Drive.id < edge)
        .limit(1)) is not None


def _closed_after(session: Session, edge: int | None) -> bool:
    """edge 之后还有没有已结束行程 (同上, 方向反过来)。"""
    if edge is None:
        return False
    return session.scalar(
        select(Drive.id).where(Drive.end_date.is_not(None), Drive.id > edge)
        .limit(1)) is not None


def _cursor_ok(session: Session, drive_id: int) -> None:
    """翻页游标 = 已加载边缘行程的 id, 必须是已结束行程 (防脏参数)。"""
    d = session.get(Drive, drive_id)
    if d is None or d.end_date is None:
        raise NotFound("游标行程不存在或未结束")


def _window_items(session: Session, own: Session, rows: list[Any],
                  eff: set[int]) -> list[GroupTripRow]:
    """窗口行组装: 起终点口径与行程列表对齐 (2026-10-17 随地点模板补齐 ——
    此前只回 TeslaMate 链), 高德名/区划/模板整行同走 place_names 缓存。"""
    effs = _eff_by_car(session, {d.car_id for d, _, _ in rows})
    amap = place_info_map(own, {a.id for _, s, e in rows for a in (s, e) if a})
    tpl = place_tpl_values(own)[0]
    return [GroupTripRow(**_trip_item(d, s, e, effs.get(d.car_id), amap,
                                      tpl).model_dump(),
                         in_group=d.id in eff) for d, s, e in rows]


def group_trip_window(session: Session, own: Session, group_id: int,
                      before_id: int | None = None,
                      after_id: int | None = None,
                      limit: int = 30) -> GroupTripsPage:
    """分组明细窗口: 默认给组内全部行程 (id 升序, 不截断 —— 组内行就是
    「当前分组的所有轨迹」); before/after = 沿两端翻组外候选 (各给 limit
    条, 贴近的先)。in_group 按当前区间现算, 两端旗标跟着本页边缘走。"""
    group = own.get(TripGroup, group_id)
    if group is None:
        raise NotFound("分组不存在")
    lo, hi = _stored_range(group)
    stmt = _trip_rows_stmt(aliased(Address), aliased(Address))  # 已含已结束过滤
    more = False
    if before_id is not None:
        _cursor_ok(session, before_id)
        rows = list(session.execute(stmt.where(Drive.id < before_id)
                                    .order_by(Drive.id.desc())
                                    .limit(limit + 1)).all())
        more = len(rows) > limit
        rows = list(reversed(rows[:limit]))    # 展示仍按 id 升序 (时间正序)
    elif after_id is not None:
        _cursor_ok(session, after_id)
        rows = list(session.execute(stmt.where(Drive.id > after_id)
                                    .order_by(Drive.id)
                                    .limit(limit + 1)).all())
        more = len(rows) > limit
        rows = rows[:limit]
    else:
        rows = list(session.execute(stmt.where(Drive.id >= lo, Drive.id <= hi)
                                    .order_by(Drive.id)).all())
    eff = set(closed_drive_ids_between(session, lo, hi))
    items = _window_items(session, own, rows, eff)
    edge_lo = items[0].id if items else None
    edge_hi = items[-1].id if items else None
    if before_id is not None:                  # 本方向翻页: limit+1 直接给出旗标
        return GroupTripsPage(group=_group_info(session, group), items=items,
                              has_more_before=more,
                              has_more_after=_closed_after(session, edge_hi))
    if after_id is not None:
        return GroupTripsPage(group=_group_info(session, group), items=items,
                              has_more_before=_closed_before(session, edge_lo),
                              has_more_after=more)
    return GroupTripsPage(group=_group_info(session, group), items=items,
                          has_more_before=_closed_before(session, edge_lo),
                          has_more_after=_closed_after(session, edge_hi))


def apply_group_changes(session: Session, own: Session, group_id: int,
                        adds: list[int],
                        removes: list[int]) -> GroupMemberUpdate:
    """分组改成员 (确认提交一批): 先吸收 —— 区间外延到全部新加段, 中间的
    已结束行程整段吸收; 再收窄 —— 移除集只许吃掉两端 (剩余成员必须是新
    区间的连续中段, 中间挖洞会断开), 至少保留 2 段 (与建组口径一致)。
    changed 列出全部翻转了状态的 id (新吸收的 + 被移走的), 前端就地在已
    加载行上翻, 不整页重拉。"""
    group = own.get(TripGroup, group_id)
    if group is None:
        raise NotFound("分组不存在")
    add_set, rm_set = set(adds), set(removes)
    if add_set & rm_set:
        raise ValueError("同一行程不能既加入又移出")
    for drive_id in sorted(add_set | rm_set):
        d = session.get(Drive, drive_id)
        if d is None or d.end_date is None:
            raise NotFound("行程不存在或未结束")
    lo, hi = _stored_range(group)
    effective = set(closed_drive_ids_between(session, lo, hi))
    if add_set & effective:
        raise ValueError("要加入的行程已在分组里")
    members = (set(closed_drive_ids_between(session, min(lo, *add_set), max(hi, *add_set)))
               if add_set else effective)
    if rm_set - members:
        raise ValueError("要移出的行程不在分组里")
    rest = sorted(i for i in members if i not in rm_set)
    if len(rest) < 2:
        raise ValueError("分组至少要保留 2 段")
    if rest != [i for i in sorted(members) if rest[0] <= i <= rest[-1]]:
        raise ValueError("只能移出最前或最后的行程")
    changed = sorted((set(rest) - effective) | (effective - set(rest)))
    group.ids = ",".join(str(i) for i in rest)
    own.commit()
    return GroupMemberUpdate(group=_group_info(session, group), changed=changed)
