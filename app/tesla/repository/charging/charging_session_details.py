"""充电详情与费用回写: 采样曲线/线缆/快充品牌 + 唯一写库点。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Charge, ChargingProcess
from .charge_samples import _charge_rows_by_ids
from .charging_sessions import _session_item
from ..common import _fnum
from ...schemas import ChargeCurve, ChargingSessionDetail, CostUpdateResult


def charging_session_detail(session: Session,
                            session_id: int) -> ChargingSessionDetail | None:
    """充电详情: 卡片字段 + 采样曲线 / 充电线缆 / 快充品牌。"""
    rows = _charge_rows_by_ids(session, [session_id])
    if not rows:
        return None
    row = rows[0]
    cp = row.process
    samples = session.scalars(
        select(Charge).where(Charge.charging_process_id == session_id)
        .order_by(Charge.date)).all()

    def _clean(value: str | None) -> str | None:
        return value if value and value != "<invalid>" else None

    # 国标取值 (线缆 GB_AC/GB_DC, 充电类型 Gb) 在国内满屏都是, 没有信息量,
    # 2026-09-13 用户点名不展示; 其他取值 (CCS / v3 等) 照常
    def _clean_national(value: str | None) -> str | None:
        v = _clean(value)
        return None if v is not None and v.upper().startswith("GB") else v

    cable = _clean_national(next(
        (c.conn_charge_cable for c in samples if c.conn_charge_cable), None))
    brand = _clean(next(
        (c.fast_charger_brand for c in samples if c.fast_charger_brand), None))
    charger_type = _clean_national(next(
        (c.fast_charger_type for c in samples if c.fast_charger_type), None))
    base = _session_item(row)
    return ChargingSessionDetail(
        **base.model_dump(),
        start_rated_range=_fnum(cp.start_rated_range_km),
        end_rated_range=_fnum(cp.end_rated_range_km),
        cable=cable, charger_brand=brand, charger_type=charger_type,
        lat=_fnum(row.address.latitude) if row.address is not None else None,
        lng=_fnum(row.address.longitude) if row.address is not None else None,
        curve=ChargeCurve(
            minutes=[round((c.date - cp.start_date).total_seconds() / 60, 1)
                     for c in samples],
            soc=[c.battery_level for c in samples],
            kw=[_fnum(c.charger_power) for c in samples],
            voltage=[_fnum(c.charger_voltage) for c in samples],
            current=[_fnum(c.charger_actual_current) for c in samples],
            energy=[_fnum(c.charge_energy_added) for c in samples]))


def update_charging_cost(session: Session, session_id: int,
                         cost: float | None) -> CostUpdateResult | None:
    """更新 / 添加 / 清除一条充电记录的费用 (唯一写库点, 金额已由路由校验)。

    返回 None 表示记录不存在。
    """
    process = session.get(ChargingProcess, session_id)
    if process is None:
        return None
    base = float(process.charge_energy_used or 0) \
        or float(process.charge_energy_added or 0)
    process.cost = round(cost, 2) if cost is not None else None
    session.commit()
    price = round(cost / base, 3) if cost is not None and base else None
    return CostUpdateResult(ok=True, cost=cost, price_per_kwh=price)
