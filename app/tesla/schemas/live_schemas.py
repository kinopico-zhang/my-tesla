"""当前驾驶域接口模型。"""
from pydantic import BaseModel


class LiveStatus(BaseModel):
    """当前驾驶状态: 未结束行程 + 最新位置点足够新才算"在开车"
    (TeslaMate 记录中断会留下几个月前的未关闭行程, 不能当当前驾驶)。"""

    driving: bool
    drive_id: int | None = None
    start: str | None = None          # 出发时间 (本地 YYYY-MM-DD HH:MM)
    started_utc: int | None = None    # 出发 epoch 秒 (前端本地走秒算已行驶时长)
    speed: float | None = None        # 最新车速 km/h
    speed_max: float | None = None    # 本次驾驶最高车速 km/h
    soc: int | None = None            # 剩余电量 %
    rated_range_km: float | None = None   # 剩余额定续航 km (最近一次车 API 轮询值)
    km: float | None = None           # 已行驶里程 (odometer 差, 与行程里程同口径)
    kwh: float | None = None          # 已耗电 (额定续航差 × 充电定标, 同行程电耗口径)
    wh_per_km: int | None = None      # 平均电耗 Wh/km (里程 <1km 无意义 → None)
    lng: float | None = None          # 最新位置 (WGS-84)
    lat: float | None = None
    pos_utc: int | None = None        # 最新位置点 epoch 秒 (前端判数据新鲜度)
    now_utc: int | None = None        # 服务器当前 epoch 秒 (前端据此算手机时钟偏差,
                                      # 已行驶时长不被不准的手机时钟带偏成 0)
