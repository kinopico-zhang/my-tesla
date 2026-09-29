"""足迹「走过之路」的数据访问: 拟合结果读取/落库, 已结束行程清单, 单程
原始点位流式读取。

读取全走 UNIQUE(drive_id) 点查/IN 查 (清单拼标注 + 流式下发), 聚合在
客户端做 (roads-grid) —— 服务端无聚合热路径 (口径见 mytesla_tables
.DriveRoad 注)。"""
from collections.abc import Sequence
from datetime import timezone
from itertools import chain
import json

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..models import Drive, DriveRoad, Position
from ..roads_geom import RoadPoint


def roads_lite(own: Session) -> dict[int, tuple[str, int, int]]:
    """drive_id → (status, n, v): 清单拼 s/rn 用 (一程一行, 全扫毫秒级)。"""
    rows = own.execute(select(DriveRoad.drive_id, DriveRoad.status,
                              DriveRoad.n, DriveRoad.v)).all()
    return {d: (s, n, v) for d, s, n, v in rows}


def done_drive_ids(own: Session, ver: int) -> set[int]:
    """当前算法版本已处理的行程 id 集 (ok/failed/skip 都算): worker 水位。"""
    return set(own.scalars(
        select(DriveRoad.drive_id).where(DriveRoad.v == ver)))


def adopt_v2_ok(own: Session, ver: int) -> int:
    """v2 的 ok 且无推断区间行原地改 v (v2→v3 一次性迁移): 这类行程抓路
    全程成功、没有桥接路径参与, v3 输出等价 (实线 ok, 无虚线), 不必重拟合
    烧配额 —— 真要重算的只有 guess / failed / 带推断桥的 ok。幂等, 返回
    改行数。"""
    res = own.execute(update(DriveRoad).values(v=ver)
                      .where(DriveRoad.v == 2, DriveRoad.status == "ok",
                             DriveRoad.gaps == "[]"))
    own.commit()
    # Result 类型桩上没有 rowcount (DML 运行时才有), getattr 取实跑值
    return int(getattr(res, "rowcount", 0) or 0)


def roads_rows(own: Session, ids: Sequence[int]) -> list[DriveRoad]:
    """按 id 批取有路的行 (ok=证实 / guess=推断; 流式接口 200 一批喂前端,
    failed/skip 没有几何不发)。"""
    if not ids:
        return []
    return list(own.scalars(select(DriveRoad)
                            .where(DriveRoad.drive_id.in_(ids),
                                   DriveRoad.status.in_(("ok", "guess")))))


def save_road(own: Session, row: DriveRoad) -> None:
    """拟合结果落库: 一程一行, 同 drive 重写 = 先删后插 (save_fill 同款)。"""
    own.execute(delete(DriveRoad).where(DriveRoad.drive_id == row.drive_id))
    own.add(row)
    own.commit()


def closed_drives(session: Session) -> list[tuple[int, float]]:
    """已结束行程 (distance/end_date 非空) 的 (id, distance_km), 开始时间
    倒序 —— worker 最新优先回填。"""
    rows = session.execute(select(Drive.id, Drive.distance)
                           .where(Drive.distance.is_not(None),
                                  Drive.end_date.is_not(None))
                           .order_by(Drive.start_date.desc())).all()
    return [(int(i), float(d)) for i, d in rows]


def drive_points(session: Session, drive_id: int) -> list[RoadPoint]:
    """单程原始点位 → RoadPoint (时间升序)。流式分块取行: 最大一程 6.7 万点,
    一次性 .all() 物化整段 Row 小内存 NAS 颠簸 (query_tracks 同款对策);
    date 是 UTC 裸时间戳, .timestamp() 前必须钉 UTC (naive 按本地时区算)。"""
    stmt = (select(Position.longitude, Position.latitude,
                   Position.speed, Position.date)
            .where(Position.drive_id == drive_id)
            .order_by(Position.date)
            .execution_options(stream_results=True))
    result = session.execute(stmt)
    return [RoadPoint(float(lng), float(lat), float(sp or 0.0),
                      d.replace(tzinfo=timezone.utc).timestamp())
            for lng, lat, sp, d in chain.from_iterable(result.partitions(20_000))]


def road_row(drive_id: int, status: str, v: int, pts: list[float],
             n: int, km: float, err: str,
             gaps: list[list[int]] | None = None) -> DriveRoad:
    """FitResult → 落库行 (pts/gaps 平铺 JSON; err 截 200 防刷库)。"""
    return DriveRoad(drive_id=drive_id, status=status, v=v,
                     pts=json.dumps(pts, separators=(",", ":")),
                     n=n, km=km, err=err[:200],
                     gaps=json.dumps(gaps or [], separators=(",", ":")))
