"""电池健康度接口模型 (2026-09-27 新增, 充电组新页面)。

估算口径照 TeslaMate Battery Health 仪表盘移植: 满电续航 =
额定续航 ÷ 可用电量 × 100 (纯车端数据, 不掺充电损耗); 电池容量 =
满电续航 × 充电定标系数 (charge_efficiency, 桩端口径)。
"""
from pydantic import BaseModel


class BatteryHealthPoint(BaseModel):
    """曲线上的一个充电日: 当日采样的满电续航估算 (Σ续航 ÷ Σ可用电量)。"""

    day: str                 # 本地日期 YYYY-MM-DD
    range_km: float


class BatteryHealth(BaseModel):
    """电池健康度汇总 (无可用充电采样时各项全空, 前端亮空态)。"""

    health_pct: float | None          # 100 × 当前 ÷ 峰值, 封顶 100
    current_range_km: float | None    # 最近 100 个采样的满电续航均值
    max_range_km: float | None        # 充电日峰值 (曲线最高点)
    current_capacity_kwh: float | None    # 满电续航 × 定标系数; 未定标 None
    max_capacity_kwh: float | None
    efficiency_kwh_per_km: float | None   # 充电定标 (额定续航 km → 桩端 kWh)
    sample_days: int                  # 曲线点数 (有有效采样的充电日)
    series: list[BatteryHealthPoint]  # 按日升序
