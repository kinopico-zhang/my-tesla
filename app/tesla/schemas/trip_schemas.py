"""行程域接口模型: 列表条目/过路费回传/驾驶员标注/地区树/轨迹/合并轨迹/分组/断档补路。"""
from pydantic import BaseModel, ConfigDict, Field


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
