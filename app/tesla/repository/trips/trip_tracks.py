"""行程轨迹: 单条全精度轨迹 + 多段合并 (整包/流式) + 区间展开。"""
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Iterator, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from ...models import Address, Drive, Position
from .gap_fills import _track_points
from .trip_listing import _consumption, _trip_rows_stmt
from ..charging import charge_efficiency
from ..common import NotFound, _clean_addr, _keep_indices, fdate, ftime
from ...schemas import MergedTrack, TripTrack


TRIP_TRACK_PER = 5000


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
