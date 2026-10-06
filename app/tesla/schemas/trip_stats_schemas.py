"""行程统计页的接口模型 (2026-09-27 新增, 用户点名「加一个行程统计页面,
参考充电统计」): 汇总 / 按月 / 常去地点 / 多维聚合。"""
from pydantic import BaseModel, Field


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


class TripLocSpot(BaseModel):
    """常去地点组里的一个停车点坐标 (改名弹层小地图多点标记用)。"""

    lat: float
    lng: float


class TripLocRaw(BaseModel):
    """组内一个真实地点 (2026-10-03 用户点名「展开这个地点所有的真实地点」,
    2026-10-04 用户点名「点列表的 item, 地图切换到这个位置」—— 行带各自
    坐标): name = raw 原名, trips = 该名的停车次数, lat/lng = 该名最近
    一次出现的地址坐标 (WGS-84, 没坐标如实 None)。"""

    name: str
    trips: int
    lat: float | None
    lng: float | None


class TripLocStat(BaseModel):
    """常去地点 (按停车次数降序; 2026-09-30 用户点名「只看我停车是在哪,
    而不是路过哪」): 挪车微程不计, 同一次停车只计一次 —— trips 是真正停
    过几回。name = 显示名 (改过名 = 别名, 同别名并组 —— 两处原名改成同一
    个名就并成一组; 地址链自动并进末端裸地名); raws = 并进这组的原名们
    (改名接口的键, 并组要多名一起改); details = 组内各真实地点的名+次数
    (管理页点组行展开, 2026-10-03); lat/lng = 组内次数最多那个原名最近
    一次出现的地址坐标 (WGS-84); spots = 组内各原名各自的坐标 (去重, 主
    坐标在前 —— 并组里多个停车位置时改名弹层小地图一一点出); orig = 组里
    被改过名的最常原名 (2026-10-04 天玑公馆撞名组实锤: 前端旧判据「组名
    不在 raws 里 = 改过名」被 raw 本身就叫天玑公馆的组打穿, 没改过名的组
    反倒显示不出「原名」行 —— 改后端点名)。"""

    name: str
    trips: int
    lat: float | None
    lng: float | None
    raws: list[str]
    orig: str | None = None
    details: list[TripLocRaw] = []
    spots: list[TripLocSpot] = []


class PlaceAliasUpdate(BaseModel):
    """常用地点改名 (2026-09-30 用户点名): places = 要改的原名列表 (统计行
    的 raws 原样回传, 并组一起改); alias 空 = 还原原名。"""

    places: list[str] = Field(min_length=1)
    # 60 (2026-10-02 从 30 放宽): 命名框下拉能选已有名字, 领进的原始地址链
    # 有超过 30 字的 —— 选了存不进去就成了坑
    alias: str = Field(max_length=60)


class PlaceHideUpdate(BaseModel):
    """常用地点删除/恢复 (2026-10-03 用户点名「左滑删除」): places = raw
    原名或组显示名; hidden=True 落隐藏行 (统计里消失), False 删行恢复。"""

    places: list[str] = Field(min_length=1)
    hidden: bool = True


class TripDriverStat(BaseModel):
    """司机里程分布 (按里程降序; 2026-09-27 用户点名「行驶统计加一个司机
    里程分布」)。归集口径与行程卡片同源: 显式标注 > 默认驾驶员兜底,
    都没有的归「未标注」。"""

    name: str
    km: float                 # 该驾驶员名下行程的里程合计 (km)
    trips: int


class TripDims(BaseModel):
    """行程统计多维聚合: 出发时段 / 单程距离 / 行驶时长 / 车速 / 速度·电耗。"""

    by_hour: list[int]        # 出发时段 12 档: 每 2 小时一组, 出发小时 // 2 (本地时区)
    by_dist: list[int]        # 单程距离十档 (km): <2/2-5/5-10/10-20/20-50/50-100/
                              # 100-150/150-200/200-300/≥300
    by_dur: list[int]         # 行驶时长十档: <10分/10-20分/20-30分/30-45分/45-60分/1-1.5时/1.5-2时/2-3时/3-5时/≥5时
    by_spd: list[float]       # 车速九档 (km/h): 每 20 一档, ≥160 收尾;
                              # 档值 = 该速度段行驶里程 (km) —— 真速度分布,
                              # 行车采样逐秒积分 (2026-09-27 用户点名「车速
                              # 分布不是最大车速分布, 纵坐标是 km」), 路由侧
                              # 从 speed_hist_cache 合入
    by_spd_kwh: list[float]   # 车速九档行车电量 (kWh): 行车功率逐秒积分
                              # (含动能回收与附件负载, 缺采样如实 0), 路由侧
                              # 从 speed_hist_cache 合入 —— 各速度段平均电耗
                              # = by_spd_kwh ÷ by_spd (2026-09-30 用户点名
                              # 「横坐标是速度, 纵坐标是平均电耗」, 旧「行程
                              # Wh/km 落档计数」口径整链退役)
