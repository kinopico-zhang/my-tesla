"""电池健康度估算 (2026-09-27 新增, 充电组新页面): 口径照 TeslaMate
Battery Health 仪表盘移植。

满电续航估算 = rated_battery_range_km × 100 ÷ usable_battery_level —— 纯
车端采样, 不掺充电损耗; 只采充电结尾 100% 的过程 (2026-09-27 用户点名
「满电续航你只能采集充电结尾是100%的样来估算」: 表显续航与电量在 SOC
顶部不线性, 部分充电外推满电有偏, 满充采样外推误差最小 —— 原先
TeslaMate 同款的大 Session 过滤随之退役)。曲线与峰值按「充电日」聚合
(Σ续航 ÷ Σ可用电量, 日均口径压单点噪声), 当前值取最近 100 个采样的均值。
电池容量 = 满电续航 × charge_efficiency (桩端定标, 与行程电耗同源 ——
容量是「可用电量」口径, 车端真实化学容量略高)。

日分桶在 Python 侧 (先按充电过程 SQL 聚合, 免 to_char/strftime 方言差异,
与 charging_stats.monthly_stats 同规矩); 采样按过程归属到过程起始日的
本地日 (跨午夜的充电整段记在开始日, 对健康曲线无感)。
"""
from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from ...models import Charge, ChargingProcess
from ...schemas import BatteryHealth, BatteryHealthPoint
from ..common import to_local
from .charge_samples import charge_efficiency


class DailyAgg(BaseModel):
    """充电日累加器 (Σ额定续航 / Σ可用电量)。"""

    rated: float = 0.0
    level: float = 0.0


def _daily_series(session: Session,
                  conds: list[ColumnElement[bool]]) -> list[BatteryHealthPoint]:
    """每日序列: 先按过程聚合 (Σ额定续航 / Σ可用电量), Python 侧归到
    过程起始日的本地日, 逐日 Σ续航 ÷ Σ可用电量 × 100。"""
    level = func.coalesce(Charge.usable_battery_level, Charge.battery_level)
    rows = session.execute(
        select(ChargingProcess.start_date,
               func.sum(Charge.rated_battery_range_km), func.sum(level))
        .join(Charge, Charge.charging_process_id == ChargingProcess.id)
        .where(*conds)
        .group_by(ChargingProcess.id, ChargingProcess.start_date)).all()
    days: dict[str, DailyAgg] = {}
    for start_date, rated_sum, level_sum in rows:
        bucket = days.setdefault(
            to_local(start_date).strftime("%Y-%m-%d"), DailyAgg())
        bucket.rated += float(rated_sum or 0.0)
        bucket.level += float(level_sum or 0.0)
    return [BatteryHealthPoint(day=day, range_km=round(b.rated / b.level * 100, 1))
            for day, b in sorted(days.items()) if b.level > 0]


def _current_estimate(session: Session,
                      conds: list[ColumnElement[bool]]) -> float | None:
    """当前值: 最近 100 个满充采样的估算均值 (与日序列同口径同过滤 ——
    只采充到 100% 的过程, 2026-09-27 用户点名)。"""
    level = func.coalesce(Charge.usable_battery_level, Charge.battery_level)
    est = Charge.rated_battery_range_km * 100.0 / level
    rows = session.execute(
        select(est)
        .join(ChargingProcess, ChargingProcess.id == Charge.charging_process_id)
        .where(*conds)
        .order_by(ChargingProcess.end_date.desc(), Charge.date.desc())
        .limit(100)).scalars().all()
    vals = [v for v in rows if v is not None]   # conds 已钉非空, 收窄给类型检查
    return round(sum(vals) / len(vals), 1) if vals else None


def battery_health(session: Session,
                   car_id: int | None = None) -> BatteryHealth:
    """电池健康度: 每日满电续航曲线 + 当前/峰值 (续航与容量两单位)。"""
    eff = charge_efficiency(session, car_id)
    level = func.coalesce(Charge.usable_battery_level, Charge.battery_level)
    conds = [ChargingProcess.end_date.is_not(None),
             ChargingProcess.end_battery_level == 100,   # 只采充到 100% 的过程
             Charge.rated_battery_range_km.is_not(None),
             level > 0]
    if car_id is not None:
        conds.append(ChargingProcess.car_id == car_id)
    series = _daily_series(session, conds)
    max_range = max((p.range_km for p in series), default=None)
    current = _current_estimate(session, conds)
    health = (min(100.0, round(current / max_range * 100, 1))
              if current and max_range else None)
    return BatteryHealth(
        health_pct=health,
        current_range_km=current,
        max_range_km=max_range,
        current_capacity_kwh=round(current * eff, 1)
        if current is not None and eff is not None else None,
        max_capacity_kwh=round(max_range * eff, 1)
        if max_range is not None and eff is not None else None,
        efficiency_kwh_per_km=round(eff, 4) if eff is not None else None,
        sample_days=len(series),
        series=series,
    )
