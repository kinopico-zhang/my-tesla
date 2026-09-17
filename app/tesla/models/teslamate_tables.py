"""TeslaMate 库的表映射 (只读使用, 仅映射用到的列)。"""
from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .model_bases import Base


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
