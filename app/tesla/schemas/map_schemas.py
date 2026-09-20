"""足迹地图域接口模型: 地图配置/汇总/全精度轨迹清单与流。

轨迹点全部用扁平数组 [lng, lat, lng, lat, ...]: 75 万点的全量足迹,
点对嵌套会让浏览器端内存翻几倍 (每个小数组自带对象头), 扁平后一个
Float64 数组就装下。粗/细渲染的抽稀在客户端做 (见 TrackUtil)。
"""
from pydantic import BaseModel


class AmapConfig(BaseModel):
    """地图前端配置 (env / 设置页注入): 服务商 + 高德 Key/样式
    (类名沿用 Amap 起家时的旧名; provider=osm 时 Key/样式闲置)。"""

    provider: str
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
    """清单行: id / 点数 n / 驾驶员 d / 车 c / 日期 t。

    客户端拿清单对账本地库 (n 不符重下, 多余删掉), t/c/d 供
    时间/车辆/驾驶员筛选在本地做 —— 轨迹本体不用再按筛选请求。"""

    id: int
    n: int
    d: int | None
    c: int
    t: str


class MapManifest(BaseModel):
    """全量轨迹清单 (每次打开足迹地图现拉, 体积小)。"""

    v: int
    tracks: list[MapManifestTrack]
