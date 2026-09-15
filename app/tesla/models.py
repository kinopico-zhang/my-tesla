"""TeslaMate 表的 SQLAlchemy 声明映射 (只读使用, 仅映射用到的列)。

生产表由 TeslaMate 迁移维护, 这里绝不建表/改表; 建表只发生在测试的
SQLite 里 (Base.metadata.create_all)。数值列统一映射 Float: 库内
numeric 读出是 Decimal, 统一转 float 与旧接口输出一致。

OwnBase 是 My Tesla 自有表的基类 (SQLite 自有库, 与 TeslaMate 库
完全隔离), 由应用自己 create_all 建表。
"""
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """TeslaMate 表映射基类。"""


class OwnBase(DeclarativeBase):
    """My Tesla 自有表基类 (data/mytesla.db, 应用自己建表)。"""


class Car(Base):
    """车辆 (单用户通常一辆)。"""

    __tablename__ = "cars"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    model: Mapped[str | None]
    trim_badging: Mapped[str | None]
    vin: Mapped[str | None]


class Address(Base):
    """充电/行程起终点地址 (反向地理编码结果)。latitude/longitude 是
    GPS 原始坐标 (WGS-84), 充电地图用它定位充电点圆标。"""

    __tablename__ = "addresses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None]
    city: Mapped[str | None]
    display_name: Mapped[str | None]
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]


class Geofence(Base):
    """地理围栏 (家/公司等常去点)。"""

    __tablename__ = "geofences"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None]


class ChargingProcess(Base):
    """一次充电过程。"""

    __tablename__ = "charging_processes"
    id: Mapped[int] = mapped_column(primary_key=True)
    start_date: Mapped[datetime]
    end_date: Mapped[datetime | None]
    address_id: Mapped[int | None]
    geofence_id: Mapped[int | None]
    start_battery_level: Mapped[int | None]
    end_battery_level: Mapped[int | None]
    charge_energy_added: Mapped[float | None]
    charge_energy_used: Mapped[float | None]
    duration_min: Mapped[int | None]
    cost: Mapped[float | None]
    outside_temp_avg: Mapped[float | None]
    start_rated_range_km: Mapped[float | None]
    end_rated_range_km: Mapped[float | None]


class Charge(Base):
    """充电过程内的采样点 (功率/电压/电流曲线)。"""

    __tablename__ = "charges"
    id: Mapped[int] = mapped_column(primary_key=True)
    charging_process_id: Mapped[int]
    date: Mapped[datetime]
    battery_level: Mapped[int | None]
    charger_power: Mapped[float | None]
    charger_voltage: Mapped[float | None]
    charger_actual_current: Mapped[float | None]
    charge_energy_added: Mapped[float | None]
    outside_temp: Mapped[float | None]
    conn_charge_cable: Mapped[str | None]
    fast_charger_brand: Mapped[str | None]
    fast_charger_type: Mapped[str | None]
    fast_charger_present: Mapped[bool | None] = mapped_column(Boolean)


class Drive(Base):
    """一次行车行程 (只统计已完成: end_date 非空)。"""

    __tablename__ = "drives"
    id: Mapped[int] = mapped_column(primary_key=True)
    start_date: Mapped[datetime]
    end_date: Mapped[datetime | None]
    distance: Mapped[float | None]
    duration_min: Mapped[int | None]
    speed_max: Mapped[int | None]
    start_rated_range_km: Mapped[float | None]
    end_rated_range_km: Mapped[float | None]
    start_address_id: Mapped[int | None]
    end_address_id: Mapped[int | None]


class Position(Base):
    """行车 GPS 采样点。

    speed/power 是流式数据 (每秒多条); battery_level 同样全程有值,
    而 rated_battery_range_km / odometer 等车 API 轮询字段约每 12 秒
    才有一个非空值 (当前驾驶页按"最新非空"取)。"""

    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    drive_id: Mapped[int]
    date: Mapped[datetime]
    longitude: Mapped[float]
    latitude: Mapped[float]
    speed: Mapped[float | None]
    power: Mapped[float | None]
    battery_level: Mapped[int | None]
    rated_battery_range_km: Mapped[float | None]
    odometer: Mapped[float | None]


# ---------------------------------------------------------------- 自有表
# TeslaMate 原库始终只读; 断档补路这类"补出来"的数据全部落自有库。

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

    未设 (空串) 字段回落 env/.env 默认值; 密码/Key 只存不回显
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
