"""轨迹断档补路 (隧道/信号丢失): 原始采样不动, 补出来的点全部存自有库,
轨迹接口在服务端拼好 —— 所有消费方都不再看到断档, 前端也不用每次
重新调高德规划。own 参数即自有库会话 (与 TeslaMate 会话隔离)。
"""
from datetime import datetime, timedelta
import json
import math
from typing import NamedTuple
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import Position, TrackFill
from ..common import NotFound
from ...schemas import GapFillRequest


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
