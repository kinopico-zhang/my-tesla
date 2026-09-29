"""行程统计页的接口模型 (2026-09-27 新增, 用户点名「加一个行程统计页面,
参考充电统计」): 汇总 / 按月 / 常去地点 / 多维聚合。"""
from pydantic import BaseModel


class TripStatsSummary(BaseModel):
    """行程统计汇总 (顶部统计卡)。"""

    trips: int
    km: float                 # 里程合计 (km)
    duration_min: int         # 行驶时长合计 (分钟)
    kwh: float | None         # 电耗合计: 额定续航差 × 桩端换算系数 (没定标 = None)
    wh_per_km: int | None     # 全程平均电耗 (ΣkWh / Σkm × 1000)
    speed_max: int | None     # 全程最高车速 (km/h)
    first_date: str | None
    last_date: str | None


class TripMonthlyStat(BaseModel):
    """按月行程统计 (月度趋势两幅柱状的数据行)。"""

    month: str                # 本地月份 YYYY-MM
    trips: int
    km: float
    kwh: float | None         # 没定标/该月无可用行程 = None


class TripLocStat(BaseModel):
    """常去地点 (起终点地址并计, 按次数降序)。"""

    name: str
    trips: int


class TripDriverStat(BaseModel):
    """司机里程分布 (按里程降序; 2026-09-27 用户点名「行驶统计加一个司机
    里程分布」)。归集口径与行程卡片同源: 显式标注 > 默认驾驶员兜底,
    都没有的归「未标注」。"""

    name: str
    km: float                 # 该驾驶员名下行程的里程合计 (km)
    trips: int


class TripDims(BaseModel):
    """行程统计多维聚合: 出发时段 / 单程距离 / 行驶时长 / 最高车速 / 平均电耗。"""

    by_hour: list[int]        # 出发时段 12 档: 每 2 小时一组, 出发小时 // 2 (本地时区)
    by_dist: list[int]        # 单程距离十档 (km): <2/2-5/5-10/10-20/20-50/50-100/
                              # 100-150/150-200/200-300/≥300
    by_dur: list[int]         # 行驶时长十档: <10分/10-20分/20-30分/30-45分/45-60分/1-1.5时/1.5-2时/2-3时/3-5时/≥5时
    by_spd: list[float]       # 车速九档 (km/h): 每 20 一档, ≥160 收尾;
                              # 档值 = 该速度段行驶里程 (km) —— 真速度分布,
                              # 行车采样逐秒积分 (2026-09-27 用户点名「车速
                              # 分布不是最大车速分布, 纵坐标是 km」), 路由侧
                              # 从 speed_hist_cache 合入
    by_wh: list[int]          # 平均电耗十档 (Wh/km): 每 20 一档, ≥260 收尾 (未定标不进档)
