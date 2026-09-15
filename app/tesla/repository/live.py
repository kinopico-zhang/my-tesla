"""当前驾驶: 未结束行程的实时状态

本模块只管 live 域的查询与组装; 通用时间/参数工具在 common.py。
"""
from datetime import datetime
from datetime import timezone as dt_timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Drive, Position
from .charging import charge_efficiency
from .trips import _utc_seconds
from .common import ftime
from ..schemas import LiveStatus


LIVE_STALE_AFTER_S = 600   # 最新位置点超过 10 分钟没有 → 不算驾驶中
                           # (流式采样每秒多条, 只留短暂网络断档的余量)


def _db_now() -> datetime:
    """当前 UTC 裸时间戳 (与库内 date 同口径)。"""
    return datetime.now(dt_timezone.utc).replace(tzinfo=None)


def live_status(session: Session) -> LiveStatus:
    """当前驾驶状态: 未结束行程里位置点最新的那条, 且位置点足够新。

    判据见 LIVE_STALE_AFTER_S —— 未关闭 ≠ 在开 (库里躺着十几条
    TeslaMate 中断残留的未关闭行程)。里程 = odometer 差 (与行程页
    distance 同口径, 已在真实库逐位对齐验证); 电耗 = 额定续航差 ×
    充电定标, 续航取"首个/最新非空轮询值" (流式点位大多没有该字段)。
    """
    cand = session.execute(
        select(Drive.id, Drive.start_date, func.max(Position.date).label("last"))
        .join(Position, Position.drive_id == Drive.id)
        .where(Drive.end_date.is_(None))
        .group_by(Drive.id, Drive.start_date)
        .order_by(func.max(Position.date).desc())).first()
    if cand is None or _utc_seconds(cand.last) < _utc_seconds(_db_now()) \
            - LIVE_STALE_AFTER_S:
        return LiveStatus(driving=False, now_utc=int(_utc_seconds(_db_now())))
    drive_id, start_date, _ = cand

    last_pos = session.scalars(
        select(Position).where(Position.drive_id == drive_id)
        .order_by(Position.date.desc()).limit(1)).first()
    speed_max, odo_lo, odo_hi = session.execute(
        select(func.max(Position.speed), func.min(Position.odometer),
               func.max(Position.odometer))
        .where(Position.drive_id == drive_id)).one()
    first_rr = session.execute(
        select(Position.rated_battery_range_km)
        .where(Position.drive_id == drive_id,
               Position.rated_battery_range_km.is_not(None))
        .order_by(Position.date).limit(1)).scalar_one_or_none()
    last_rr = session.execute(
        select(Position.rated_battery_range_km)
        .where(Position.drive_id == drive_id,
               Position.rated_battery_range_km.is_not(None))
        .order_by(Position.date.desc()).limit(1)).scalar_one_or_none()

    km = (round(float(odo_hi) - float(odo_lo), 2)
          if odo_lo is not None and odo_hi is not None else None)
    kwh: float | None = None
    wh_per_km: int | None = None
    eff = charge_efficiency(session)
    if eff is not None and first_rr is not None and last_rr is not None:
        raw = max(0.0, (float(first_rr) - float(last_rr)) * eff)
        kwh = round(raw, 1)
        if km is not None and km >= 1:
            wh_per_km = int(round(raw / km * 1000))

    assert last_pos is not None   # cand 有位置点聚合, 最新行必然存在
    return LiveStatus(
        driving=True, drive_id=drive_id,
        start=ftime(start_date), started_utc=int(_utc_seconds(start_date)),
        speed=last_pos.speed, speed_max=speed_max,
        soc=last_pos.battery_level,
        rated_range_km=round(float(last_rr), 1) if last_rr is not None else None,
        km=km, kwh=kwh, wh_per_km=wh_per_km,
        lng=round(float(last_pos.longitude), 6),
        lat=round(float(last_pos.latitude), 6),
        pos_utc=int(_utc_seconds(last_pos.date)),
        now_utc=int(_utc_seconds(_db_now())))
