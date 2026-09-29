"""当前驾驶: 未结束行程的实时状态

本模块只管 live 域的查询与组装; 通用时间/参数工具在 common.py。
"""
from datetime import datetime
from datetime import timezone as dt_timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Drive, Position
from .charging import charge_efficiency
from .trips import _trip_item, _utc_seconds
from .common import ftime
from ..schemas import LiveStatus


LIVE_STALE_AFTER_S = 600   # 最新位置点超过 10 分钟没有 → 不算驾驶中
                           # (流式采样每秒多条, 只留短暂网络断档的余量)


def _db_now() -> datetime:
    """当前 UTC 裸时间戳 (与库内 date 同口径)。"""
    return datetime.now(dt_timezone.utc).replace(tzinfo=None)


def _last_known(session: Session, car_id: int | None) -> LiveStatus:
    """不开车时的最后已知车辆状态: 该车全库最新位置点 (行程开没开完不管)
    —— 状态页不开车也常显电量/续航/地图位置 (2026-09-26 用户点名)。电量/
    额定续航在流式点位上大多缺席, 各取最新非空值 (与开车态续航同口径)。
    点位不带 Drive 内连接 (2026-09-29 修「驻车不实时更新, 充满电还显示
    没电」): 停车充电的采样点 drive_id 为空, 原内连接把它们整段挡在门外,
    电量/续航冻在最后一段行程的末值 —— 车辆过滤改走 Position 自己的
    car_id。另带最后一段已结束行程 (2026-09-27 用户点名「驻车的时候,
    显示最后一段行程」) —— 条目与行程列表同口径 (_trip_item)。"""
    pos_stmt = select(Position)
    soc_stmt = select(Position.battery_level).where(
        Position.battery_level.is_not(None))
    rr_stmt = (select(Position.rated_battery_range_km)
               .where(Position.rated_battery_range_km.is_not(None)))
    if car_id is not None:
        car = Position.car_id == car_id
        pos_stmt, soc_stmt, rr_stmt = (pos_stmt.where(car), soc_stmt.where(car),
                                      rr_stmt.where(car))
    drive_stmt = (select(Drive).where(Drive.end_date.is_not(None))
                  .order_by(Drive.end_date.desc()).limit(1))
    if car_id is not None:
        drive_stmt = drive_stmt.where(Drive.car_id == car_id)
    drive = session.scalars(drive_stmt).first()
    last_drive = (_trip_item(drive, None, None, charge_efficiency(session, car_id))
                  if drive is not None else None)
    last = session.scalars(
        pos_stmt.order_by(Position.date.desc()).limit(1)).first()
    if last is None:
        return LiveStatus(driving=False, last_drive=last_drive,
                          now_utc=int(_utc_seconds(_db_now())))
    soc = session.scalars(
        soc_stmt.order_by(Position.date.desc()).limit(1)).one_or_none()
    rr = session.scalars(
        rr_stmt.order_by(Position.date.desc()).limit(1)).one_or_none()
    return LiveStatus(
        driving=False, soc=soc, last_drive=last_drive,
        rated_range_km=round(float(rr), 1) if rr is not None else None,
        lng=round(float(last.longitude), 6),
        lat=round(float(last.latitude), 6),
        pos_utc=int(_utc_seconds(last.date)),
        now_utc=int(_utc_seconds(_db_now())))


def live_status(session: Session,
                car_id: int | None = None) -> LiveStatus:
    """当前驾驶状态: 未结束行程里位置点最新的那条, 且位置点足够新;
    不开车时回落最后已知车辆状态 (电量/续航/位置, 见 _last_known)。

    car_id 选定时只看那台车 (多车切换); 缺省 None = 全库最新。
    判据见 LIVE_STALE_AFTER_S —— 未关闭 ≠ 在开 (库里躺着十几条
    TeslaMate 中断残留的未关闭行程)。里程 = odometer 差 (与行程页
    distance 同口径, 已在真实库逐位对齐验证); 电耗 = 额定续航差 ×
    充电定标, 续航取"首个/最新非空轮询值" (流式点位大多没有该字段)。
    """
    cand_stmt = (
        select(Drive.id, Drive.start_date, func.max(Position.date).label("last"))
        .join(Position, Position.drive_id == Drive.id)
        .where(Drive.end_date.is_(None)))
    if car_id is not None:
        cand_stmt = cand_stmt.where(Drive.car_id == car_id)
    cand = session.execute(
        cand_stmt.group_by(Drive.id, Drive.start_date)
        .order_by(func.max(Position.date).desc())).first()
    if cand is None or _utc_seconds(cand.last) < _utc_seconds(_db_now()) \
            - LIVE_STALE_AFTER_S:
        return _last_known(session, car_id)
    drive_id, start_date, _ = cand

    last_pos = session.scalars(
        select(Position).where(Position.drive_id == drive_id)
        .order_by(Position.date.desc()).limit(1)).first()
    odo_lo, odo_hi = session.execute(
        select(func.min(Position.odometer), func.max(Position.odometer))
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
    eff = charge_efficiency(session, car_id)
    if eff is not None and first_rr is not None and last_rr is not None:
        kwh = round(max(0.0, (float(first_rr) - float(last_rr)) * eff), 1)

    assert last_pos is not None   # cand 有位置点聚合, 最新行必然存在
    return LiveStatus(
        driving=True, drive_id=drive_id,
        start=ftime(start_date), started_utc=int(_utc_seconds(start_date)),
        speed=last_pos.speed,
        soc=last_pos.battery_level,
        rated_range_km=round(float(last_rr), 1) if last_rr is not None else None,
        km=km, kwh=kwh,
        lng=round(float(last_pos.longitude), 6),
        lat=round(float(last_pos.latitude), 6),
        pos_utc=int(_utc_seconds(last_pos.date)),
        now_utc=int(_utc_seconds(_db_now())))
