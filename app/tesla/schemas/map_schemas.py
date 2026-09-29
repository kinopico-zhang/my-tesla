"""足迹地图域接口模型: 地图配置/汇总/全精度轨迹清单与流。

轨迹点全部用扁平数组 [lng, lat, lng, lat, ...]: 75 万点的全量足迹,
点对嵌套会让浏览器端内存翻几倍 (每个小数组自带对象头), 扁平后一个
Float64 数组就装下。粗/细渲染的抽稀在客户端做 (见 TrackUtil)。
"""
from pydantic import BaseModel


class AmapConfig(BaseModel):
    """地图前端配置 (env / 设置页注入): 高德 Key/样式
    (类名沿用 Amap 起家时的旧名; 2026-09-25 起单服务商, 无 provider 字段)。"""

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
    """全精度轨迹 (一个行程一条): pts 扁平 [lng, lat, ...]。
    客户端下载后存 IndexedDB, 清单 (MapManifestTrack) 驱动增量。"""

    id: int
    car_id: int
    date: str
    km: float
    min: int | None
    pts: list[float]


class MapManifestTrack(BaseModel):
    """清单行: id / 点数 n / 驾驶员 d / 车 c / 日期 t / 道路拟合态 s·rn / 时长 m。

    客户端拿清单对账本地库 (n 不符重下, 多余删掉), t/c/d 供
    时间/车辆/驾驶员筛选在本地做 —— 轨迹本体不用再按筛选请求。
    s: 0=未拟合 (还没有路) / 1=已拟合到路 (实线进计数) / 2=拟合不成
    (failed/skip, 同 v 不再试) / 3=可能走过 (guess, 推断层虚线);
    rn=拟合点数 (fp_roads 对账用); m=时长
    分钟 (道路层详情卡显示, 免客户端另存)。"""

    id: int
    n: int
    d: int | None
    c: int
    t: str
    s: int = 0
    rn: int = 0
    m: int | None = None


class MapManifest(BaseModel):
    """全量轨迹清单 (每次打开足迹地图现拉, 体积小)。

    rv=道路算法版本 (不符时客户端清掉本地 fp_roads 全量重下);
    rd/rt=道路拟合进度 (已处理/总行程, 图例「拟合 x/y」)。"""

    v: int
    tracks: list[MapManifestTrack]
    rv: int = 0
    rd: int = 0
    rt: int = 0


class RoadStreamRow(BaseModel):
    """走过之路流的一行: pts 扁平 WGS-84 [lng, lat, ...]; g 为推断层
    顶点闭区间 [[i0, i1], ...] (可能走过: 虚线渲染, 次数计数剔除)。

    客户端存 IndexedDB (fp_roads), 按清单 rn 对账 (不符重下)。"""

    id: int
    n: int
    km: float
    pts: list[float]
    g: list[list[int]] = []
