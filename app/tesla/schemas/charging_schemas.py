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


class ChargeCurve(BaseModel):
    """充电过程采样曲线 (各数组下标对齐)。"""

    minutes: list[float]
    soc: list[int | None]
    kw: list[float | None]
    voltage: list[float | None]
    current: list[float | None]
    energy: list[float | None]


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


class ChargeDims(BaseModel):
    """充电统计多维聚合: 快慢充 / 开始时段 / 起充 SOC / 峰值功率 / 城市。"""

    fast_sessions: int
    slow_sessions: int
    by_hour: list[int]        # 24 档: 0~23 点开始的充电次数 (本地时区)
    by_soc: list[int]         # 起充 SOC 五档: 0-20/20-40/…/80-100 (未知不进档)
    by_power: list[int]       # 峰值功率五档: <60/60-100/100-150/150-200/≥200 kW
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
