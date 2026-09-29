"""充电域接口模型: 列表/详情/汇总/按月按地统计/地图点位/费用回写。"""
from pydantic import BaseModel


class CarInfo(BaseModel):
    """车辆信息。"""

    id: int
    name: str
    model: str | None
    trim_badging: str | None
    vin: str | None


class ChargingSession(BaseModel):
    """充电卡片 (列表项与详情共用前缀)。"""

    id: int
    start: str
    end: str | None
    date: str
    location: str
    city: str | None
    address: str | None
    region: str | None       # 省市区链 (大→小, " · " 连); 解析不出省为 None
    start_soc: int | None
    end_soc: int | None
    energy_added: float | None
    energy_used: float | None
    cost: float | None
    price_per_kwh: float | None
    duration_min: int | None
    outside_temp: float | None
    power_max: float | None
    is_fast: bool
    tesla_supercharger: bool   # 采样里有 Tesla+Gb = 特斯拉超充 (列表打标用)


class ChargeCurve(BaseModel):
    """充电过程采样曲线 (各数组下标对齐)。

    tabs 是曲线有哪些档可看 (kw / voltage / current 的子集, kw 恒在):
    车辆直流快充时不回报电压/电流 (TeslaMate 里恒为 2V / 0A 的死字段),
    没有真数据的档不下发, 前端就不画那条 0 平线。"""

    minutes: list[float]
    soc: list[int | None]
    kw: list[float | None]
    voltage: list[float | None]
    current: list[float | None]
    energy: list[float | None]
    tabs: list[str]


class ChargingSessionDetail(ChargingSession):
    """充电详情: 卡片字段 + 曲线 / 线缆 / 快充品牌 + 充电站坐标。

    lat / lng 是地址表的 WGS-84 原始 GPS 坐标 (与充电地图同源),
    前端导航前自行换算 GC-02; 没反向地理编码过的地址为 None。"""

    start_rated_range: float | None
    end_rated_range: float | None
    cable: str | None
    charger_brand: str | None
    charger_type: str | None
    curve: ChargeCurve
    lat: float | None
    lng: float | None


class ChargingSummary(BaseModel):
    """充电汇总。"""

    sessions: int
    fast_sessions: int
    energy_added: float
    energy_used: float
    cost: float
    price_per_kwh: float | None
    duration_min: int
    soc_gain: int
    range_gain: float
    first_date: str | None
    last_date: str | None


class ChargingSessionsPage(BaseModel):
    """充电列表页。"""

    total: int
    items: list[ChargingSession]


class MonthlyStat(BaseModel):
    """按月充电统计。"""

    month: str
    sessions: int
    energy_used: float | None
    cost: float | None
    fast_sessions: int


class LocationStat(BaseModel):
    """按地点充电统计。"""

    location: str
    city: str | None
    sessions: int
    energy_used: float | None
    cost: float | None
    fast_sessions: int


class CostUpdateResult(BaseModel):
    """费用回写结果 (price_per_kwh 为回显换算值)。"""

    ok: bool
    cost: float | None
    price_per_kwh: float | None


class CityStat(BaseModel):
    """城市聚合 (充电统计页)。"""

    city: str
    sessions: int
    energy: float       # kWh (表计口径, 缺失回充入)
    cost: float         # 已记录费用合计 (未记录算 0)


class DistrictStat(BaseModel):
    """城市下钻的二级地区 (区/县/镇) 聚合 —— 双击城市柱展开 (2026-09-27)。"""

    district: str
    sessions: int
    energy: float
    cost: float


class ChargeDims(BaseModel):
    """充电统计多维聚合: 开始时段 / 起充 SOC / 峰值功率 / 单价 / 时长 / 城市。
    (快慢充占比图 2026-09-27 退役, 快慢充计数不再吐 —— 汇总的
    fast_sessions 仍供顶部统计卡; 城市只到市, 区/县并进上级市,
    双击城市柱走 /districts 下钻区县。)"""

    by_hour: list[int]        # 12 档: 每 2 小时一组, 开始小时 // 2 (本地时区)
    by_soc: list[int]         # 起充 SOC 十档: 每 10% 一档 (未知不进档)
    by_power: list[int]       # 峰值功率十档: 每 20kW 一档, ≥180 收尾 (无采样不进档)
    by_price: list[int]       # 单次单价十档 ¥/kWh: 每 0.25 一档, ≥2.25 收尾 (未记费用不进档)
    by_duration: list[int]    # 时长十档: <30/30-60/60-90/90-120 分起步, 后面按小时变粗
    by_city: list[CityStat]   # 次数降序, 最多 10 城


class ChargeMapLocation(BaseModel):
    """充电地图上的一个充电点 (按地址聚合)。"""

    id: int                    # address id
    name: str                  # 展示名: geofence 名优先, 否则地址名
    city: str | None
    lat: float                 # WGS-84 (前端转 GCJ-02 上图)
    lng: float
    sessions: int
    fast_sessions: int
    energy: float              # kWh (表计口径, 缺失回充入)
    cost: float                # 已记录费用合计 (未记录算 0)


class CostUpdateRequest(BaseModel):
    """费用回写请求体。"""

    cost: float | None = None   # null = 清除费用
