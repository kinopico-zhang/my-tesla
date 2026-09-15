"""My Tesla 的接口模型 (Pydantic)。字段与既有前端逐字段对齐, JSON 形状不变。

`from` 是 Python 关键字, 字段名用 from_ + alias="from"
(FastAPI 响应默认按别名序列化)。
"""
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- 充电
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

# ---------------------------------------------------------------- 足迹地图
class AmapConfig(BaseModel):
    """高德地图前端配置 (env / 设置页注入)。"""

    amap_key: str | None
    security_code: str | None
    style: str

class MapSummary(BaseModel):
    """地图页汇总。"""

    drives: int
    distance_km: float
    duration_min: int
    first_date: str | None
    last_date: str | None

class MapTrack(BaseModel):
    """全量粗轨迹 (每条下采样到 ~40 点)。"""

    id: int
    date: str
    km: float
    min: int | None
    pts: list[list[float]]

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

class TracksResponse(BaseModel):
    """全量粗轨迹响应。"""

    count: int
    tracks: list[MapTrack]

class MapDetailTrack(BaseModel):
    """视野内高精度轨迹。"""

    id: int
    pts: list[list[float]]

class TracksDetailResponse(BaseModel):
    """视野内高精度轨迹响应。"""

    count: int
    tracks: list[MapDetailTrack]

# ---------------------------------------------------------------- 当前驾驶
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

# ---------------------------------------------------------------- 行程
class TripItem(BaseModel):
    """行程卡片字段 (列表与单条共用)。"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    date: str
    start: str
    end: str | None
    km: float | None
    min: int | None
    speed_max: int | None
    from_: str = Field(alias="from")
    to: str
    driver: str | None = None      # 展示名: 显式标注, 未标注回落默认驾驶员
    driver_id: int | None = None   # 显式标注的驾驶员 id (未标 = None)
    toll: float | None = None      # 估价高速费 (元); None=还没算过
    toll_km: float | None = None   # 收费路段里程 (km)
    kwh: float | None = None       # 总电耗 (kWh): 额定续航差 × 桩端换算系数
    wh_per_km: float | None = None # 平均电耗 (Wh/km); 里程 <1km 无意义 → None

class TollRoad(BaseModel):
    """一段收费路 (规划 step 里的 toll_road + tolls)。"""

    road: str
    tolls: float

class TripTollIn(BaseModel):
    """前端高德规划回传: 该行程的估价高速费。"""

    tolls: float = Field(ge=0, le=10000)           # 元
    toll_km: float = Field(ge=0, le=20000)          # 收费路段里程 (km)
    distance: int = Field(ge=0, le=1000000)         # 规划里程 (米), 跨省长途 300km+
    roads: list[TollRoad] = Field(max_length=50)    # 收费路段明细

class DriverMark(BaseModel):
    """标/清行程驾驶员 (driver_id 空 = 清除标注, 展示回默认兜底)。"""

    driver_id: int | None = None

class TripsPage(BaseModel):
    """行程列表页。"""

    total: int
    items: list[TripItem]

class RegionNode(BaseModel):
    """省市区三级筛选项 (children 为下一级, 区县层为空列表)。"""

    name: str
    count: int
    children: list["RegionNode"] = []

class TripRegions(BaseModel):
    """行程页起点 / 终点省市区树 (级联下拉数据源)。"""

    start: list[RegionNode]
    end: list[RegionNode]

class TripTrack(BaseModel):
    """单条行程全精度轨迹: pts 为 [lng, lat, speed_km_h, power_W]
    (power 正=放电 负=动能回收, 可能为 null); ts 为相对起点的秒偏移
    (与 pts 下标对齐, 播放动画里用来算"已行驶时长"和平均功耗)。"""

    id: int
    pts: list[list[float | None]]
    ts: list[int]

class MergedTrack(BaseModel):
    """多选连续行程 → 一条连续轨迹 (ts 为累计行驶秒, 行程间停驶剔除)。

    seg_starts 为每段在 pts 里的起始下标: 前端逐段跑单段行程的断档识别
    (各段下采样后采样密度差着量级, 混一个数组用全局阈值会误拆)。

    与旧版响应一致: 没有 id 字段 (前端自行用 "m:{ids}" 当弹层键)。"""

    model_config = ConfigDict(populate_by_name=True)

    ids: list[int]
    n: int
    pts: list[list[float | None]]
    ts: list[int]
    seg_starts: list[int]
    date: str
    start: str
    end: str | None
    km: float
    min: int
    speed_max: int | None
    kwh: float | None = None        # 总电耗 (kWh, 各段续航差换算之和)
    wh_per_km: float | None = None  # 平均电耗 (Wh/km, 按总里程)
    from_: str = Field(alias="from")
    to: str

class TeslaMateSettings(BaseModel):
    """TeslaMate 连接现值 (密码不回显, 只报是否在用)。"""

    host: str
    port: str
    user: str
    name: str
    password_set: bool

class AmapSettings(BaseModel):
    """高德 Key 现值 (打码回显 + 安全码是否在用) + 地图样式现值。"""

    key_masked: str
    security_code_set: bool
    style: str

class SettingsState(BaseModel):
    """设置页状态: 各字段现值 (回落 env 后的效果)。"""

    tmdb: TeslaMateSettings
    amap: AmapSettings

class SettingsUpdate(BaseModel):
    """保存设置: 字段留空 = 保持现值 (密码/Key 不回显, 前端重填才算改)。"""

    tmdb_host: str = ""
    tmdb_port: str = ""
    tmdb_user: str = ""
    tmdb_password: str = ""
    tmdb_name: str = ""
    amap_key: str = ""
    amap_security_code: str = ""
    amap_style: str = ""   # 官方样式名或 amap://styles/<自定义ID> (空 = 保持现值)

class DriverInfo(BaseModel):
    """驾驶员条目。"""

    id: int
    name: str
    is_default: bool

class DriverIn(BaseModel):
    """添加驾驶员。"""

    name: str = Field(min_length=1, max_length=30)

class DriverUpdate(BaseModel):
    """改驾驶员: 改名 / 设默认 (设默认会清掉其他人的默认)。"""

    name: str | None = Field(None, min_length=1, max_length=30)
    is_default: bool | None = None

class TripGroupIn(BaseModel):
    """存分组: 名字 + 行程 id 列表 (2~100 段, 与合并播放同上限)。"""
    name: str = Field(min_length=1, max_length=30)
    ids: list[int] = Field(min_length=2, max_length=100)

class TripGroupRename(BaseModel):
    """分组改名 (只改名字, 成员不动)。"""
    name: str = Field(min_length=1, max_length=30)

class TripGroupInfo(BaseModel):
    """分组条目: 段数/里程/日期跨度按当前行程数据现算。"""
    id: int
    name: str
    ids: list[int]
    n: int
    km: float
    span: str

class GapFillRequest(BaseModel):
    """断档补路回传 (前端高德路径规划成功后 POST, 坐标一律 WGS-84)。

    a/b 为断档两端轨迹点, 服务端据此锚定到最近的原始 positions 行;
    path 为 GCJ→WGS 转换后的道路折线。"""

    drive_id: int
    a: list[float]
    b: list[float]
    path: list[list[float]]

class GapFillResponse(BaseModel):
    """断档补路回传结果 (km 为服务端按 path 实算的里程)。"""

    ok: bool
    km: float

class CostUpdateRequest(BaseModel):
    """费用回写请求体。"""

    cost: float | None = None   # null = 清除费用
