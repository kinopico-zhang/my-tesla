"""My Tesla 自有表 (SQLite 自有库, 与 TeslaMate 库完全隔离)。

TeslaMate 原库始终只读; 断档补路这类"补出来"的数据全部落自有库。
"""
from datetime import datetime

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .model_bases import OwnBase


class TrackFill(OwnBase):
    """轨迹断档补路: 一条记录 = 一个 GPS 断档 (隧道/信号丢失)。

    a_pos_id/b_pos_id 锚定断档两端原始 positions 行的主键 (稳定, 不受
    下采样影响); path 为前端用高德规划成功后回传的 WGS-84 折线。
    同一断档重复回传时按 a_pos_id 覆盖更新。
    """

    __tablename__ = "track_fills"
    __table_args__ = (UniqueConstraint("a_pos_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    drive_id: Mapped[int] = mapped_column(Integer, index=True)
    a_pos_id: Mapped[int] = mapped_column(Integer)
    b_pos_id: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String)   # JSON: [[lng, lat], ...] WGS-84
    km: Mapped[float]
    source: Mapped[str] = mapped_column(String, default="amap")
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class TripGroup(OwnBase):
    """轨迹分组: 多选的行程存成命名分组 (逻辑分组, TeslaMate 原库不动)。

    ids 为升序去重后的 drive id 逗号串; 段数/里程/日期跨度不落库,
    展示时按当前行程数据现算 (行程列表同口径, 只认已结束行程)。"""

    __tablename__ = "trip_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    ids: Mapped[str] = mapped_column(String)     # "2195,2197,2200" 升序去重
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class AppSetting(OwnBase):
    """运行时设置 (设置页改, 存自有库; 恒单行 id=1)。

    未设 (空串) 字段回落 env 默认值; 密码/Key 只存不回显
    (GET 打码, 前端留空 = 保持现值)。"""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_host: Mapped[str] = mapped_column(String, default="")
    tmdb_port: Mapped[str] = mapped_column(String, default="")
    tmdb_user: Mapped[str] = mapped_column(String, default="")
    tmdb_password: Mapped[str] = mapped_column(String, default="")
    tmdb_name: Mapped[str] = mapped_column(String, default="")
    amap_key: Mapped[str] = mapped_column(String, default="")
    amap_security_code: Mapped[str] = mapped_column(String, default="")
    amap_style: Mapped[str] = mapped_column(String, default="")
    amap_web_key: Mapped[str] = mapped_column(String, default="")  # Web服务 key (轨迹拟合)
    map_provider: Mapped[str] = mapped_column(String, default="")  # 已退役: 列留而不用 (只留高德)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now,
                                                 onupdate=datetime.now)


class Driver(OwnBase):
    """驾驶员 (设置页维护): 行程可标注驾驶员, 未标注 = 默认驾驶员兜底。

    is_default 全库至多一个 (设置新默认时其余清掉)。"""

    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class TripToll(OwnBase):
    """行程高速费估价 (高德驾车规划 tolls, 存自有库, TeslaMate 原数据不动)。

    一行程至多一条 (drive_id 唯一); tolls=0 也是有效结果 (没走收费路),
    与"还没算过"(无行, TripItem.toll=None) 区分开。distance 是规划里程
    (米), 与实际里程差得远说明估得不准; roads 是收费路段明细 (JSON)。"""

    __tablename__ = "trip_tolls"

    id: Mapped[int] = mapped_column(primary_key=True)
    drive_id: Mapped[int] = mapped_column(unique=True)
    tolls: Mapped[float] = mapped_column(default=0.0)          # 元
    toll_km: Mapped[float] = mapped_column(default=0.0)        # 收费路段里程 km
    distance: Mapped[int] = mapped_column(default=0)           # 规划总里程 米
    roads: Mapped[str] = mapped_column(default="[]")           # [{"road","tolls"}]
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class TripDriver(OwnBase):
    """行程 → 驾驶员标注 (逻辑标注, TeslaMate 原数据不动)。

    一行程至多一条 (drive_id 唯一); 标注的驾驶员被删时标注一起清掉,
    行程展示回落默认驾驶员兜底。"""

    __tablename__ = "trip_drivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    drive_id: Mapped[int] = mapped_column(unique=True)
    driver_id: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class DriveHistCache(OwnBase):
    """速度档直方图的每段聚合原料 (统计页三卡, 口径见 trip_hist 模块注)。

    已结束行程的 positions 不可变 → 原料算一次永久有效; 合并分组在
    原始点位上聚合要 ~10s (NAS 实测 68.6 万点), 不缓存挡不起弹层。
    payload 为 JSON {"v": 2, "rows": [[档, 地形(-1下坡/0平地/1上坡),
    n功率, Σpower, Σpw·speed, Σspeed, Σ秒, Σ里程差], ...]} —— v2 起
    公式原料按官方面板口径收 (AVG(power) 要 Σpower/n); v1 (裸 list)
    读不回, 作废重算。"""

    __tablename__ = "drive_hist_cache"

    drive_id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class DriveRoad(OwnBase):
    """足迹「走过之路」: 一条记录 = 一段行程拟合到实际道路的结果。

    后台 worker 用高德轨迹纠偏 (grasproad) 把原始 1s 采样拟合成路网
    折线, 断档用驾车规划 (距离优先) 补全; pts 为 DP 压缩后的 WGS-84
    平铺 JSON [lng,lat,...]。一程一行写一次 (v=算法版本, 不变不重算);
    status: ok=有路 / guess=可能走过 (推断层虚线, 几何保留不进计数) /
    failed=拟合失败(err 记因) / skip=境外或点太少 —— failed/skip 同 v
    都算已处理, 水位增量只补新行程。gaps 为推断层顶点闭区间 JSON
    [[i0,i1],...] (规划补的/直连的; guess 行覆盖全程)。读取全走
    UNIQUE(drive_id) 点查/IN 查 (清单拼标注 + 流式下发), 无聚合热路径。"""

    __tablename__ = "drive_roads"

    id: Mapped[int] = mapped_column(primary_key=True)
    drive_id: Mapped[int] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(String, default="ok")
    v: Mapped[int] = mapped_column(default=1)
    pts: Mapped[str] = mapped_column(String, default="")
    n: Mapped[int] = mapped_column(default=0)
    km: Mapped[float] = mapped_column(default=0.0)
    err: Mapped[str] = mapped_column(String, default="")
    gaps: Mapped[str] = mapped_column(String, default="[]")
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


# 地点域三表 (改名 PlaceAlias / 高德命名 PlaceName / 隐藏 HiddenPlace)
# 2026-10-03 拆去 place_tables.py (本文件顶 200 行上限)
