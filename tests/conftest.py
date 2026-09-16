"""pytest 共享 fixtures: SQLite 测试库 (免真实数据库) + 全局状态隔离。

每个用例一个独立的 SQLite 文件库, 用真实 ORM 种子数据跑真实 SQL
(不再是 FakePool / patch query); 引擎由 isolate 注入, TestClient 不触发
lifespan, 不会碰真实 TeslaMate 库 (CI 三平台可跑)。
"""
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# sys.path 注入必须先于 app 导入 (import 位置告警属预期, 按需豁免)
from app import account_store, authentication, config, database  # pylint: disable=wrong-import-position
from app.tesla import tracks_cache  # pylint: disable=wrong-import-position
from app.models import UsersBase  # pylint: disable=wrong-import-position
from app.tesla.models import (Address, Base, Car, Charge,  # pylint: disable=wrong-import-position
                        ChargingProcess, Drive, OwnBase, Position)
import app.main as m  # pylint: disable=wrong-import-position


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """每个用例独立: SQLite 库 / 自有库 / 账号库 / 会话密钥 /
    登录限速 / 轨迹缓存互不串扰。"""
    database.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(database.engine())
    database.init_own_engine(f"sqlite:///{tmp_path / 'mytesla.db'}")
    OwnBase.metadata.create_all(database.own_engine())
    database.init_users_engine(f"sqlite:///{tmp_path / 'users.db'}")
    UsersBase.metadata.create_all(database.users_engine())
    # 管理员种子 (生产在 lifespan 里做, TestClient 不触发 lifespan)
    with database.users_session_factory()() as users:  # pylint: disable=not-callable
        account_store.ensure_admin(users, config.AUTH_USER, config.AUTH_PASS)
    secret = b"unit-test-secret-0123456789abcdef"
    secret_file = tmp_path / "secret"
    secret_file.write_bytes(secret)
    monkeypatch.setattr(config, "SECRET_FILE", secret_file)
    # 测试直接替换内部密钥持有者 (与生产同构, 走真实签名路径)
    monkeypatch.setattr(authentication, "_secret",  # pylint: disable=protected-access
                        authentication._SecretHolder(  # pylint: disable=protected-access
                            hashlib.sha256(secret).digest()))
    monkeypatch.setattr(authentication, "_legacy_secret",  # pylint: disable=protected-access
                        authentication._SecretHolder(  # pylint: disable=protected-access
                            authentication._compute_legacy_secret(secret)))  # pylint: disable=protected-access
    monkeypatch.setattr(authentication, "_login_fails", {})
    tracks_cache.reset()
    monkeypatch.setenv("MAP_CACHE_FILE", str(tmp_path / "tracks_cache.json"))
    # TeslaMate 地址固定走环境变量短路: build_db_url 永不落到 docker inspect
    # (有真容器的机器上测试会静默依赖本机 docker, CI 无 docker 直接炸)
    monkeypatch.setenv("TMDB_HOST", "127.0.0.1")
    yield
    database.dispose_engine()
    database.dispose_own_engine()
    database.dispose_users_engine()


@pytest.fixture()
def client():
    """未登录的 client (不触发 lifespan, 引擎由 isolate 注入的 SQLite)。"""
    return TestClient(m.app)


@pytest.fixture()
def auth(client):  # pylint: disable=redefined-outer-name
    """已登录的 client (正确账密, 走真实签名 cookie)。"""
    r = client.post("/api/login",
                    json={"user": config.AUTH_USER, "password": config.AUTH_PASS})
    assert r.status_code == 200
    return client


@pytest.fixture()
def db():
    """直连测试库的会话 (种子数据 / 回读断言)。"""
    with database.session_factory()() as session:  # pylint: disable=not-callable
        yield session


@pytest.fixture()
def owndb():
    """直连自有库的会话 (断档补路种子 / 回读断言)。"""
    with database.own_session_factory()() as session:  # pylint: disable=not-callable
        yield session


@pytest.fixture()
def usersdb():
    """直连账号库的会话 (种子用户 / 邀请 / 回读断言)。"""
    with database.users_session_factory()() as session:  # pylint: disable=not-callable
        yield session


# ---------------------------------------------------------------- 种子工厂
# 默认值沿用旧版替身数据, 断言数字可直接对照。

def seed_charging(session: Session, **kw: Any) -> ChargingProcess:
    """一条充电过程 (默认: 2026-09-07 UTC 15:50, 快充, 家充桩地址)。"""
    fields: dict[str, Any] = {
        "id": 1, "start_date": datetime(2026, 9, 7, 15, 50),
        "end_date": datetime(2026, 9, 7, 23, 2),
        "address_id": 1, "geofence_id": None,
        "start_battery_level": 20, "end_battery_level": 80,
        "charge_energy_added": 45.0, "charge_energy_used": 48.0,
        "duration_min": 432, "cost": 25.5, "outside_temp_avg": 28.5,
        "start_rated_range_km": 120.0, "end_rated_range_km": 330.0,
    }
    fields.update(kw)
    process = ChargingProcess(**fields)
    session.add(process)
    session.commit()
    return process


def seed_charge(session: Session, process_id: int, **kw: Any) -> Charge:
    """一条充电采样 (默认: 16:00 90kW 快充, CCS / Tesla v3)。"""
    fields: dict[str, Any] = {
        "id": None, "charging_process_id": process_id,
        "date": datetime(2026, 9, 7, 16, 0), "battery_level": 20,
        "charger_power": 90.0, "charger_voltage": 400.0,
        "charger_actual_current": 220.0,
        "charge_energy_added": 0.0, "outside_temp": 28.0,
        "conn_charge_cable": "CCS",
        "fast_charger_brand": "Tesla", "fast_charger_type": "v3",
        "fast_charger_present": True,
    }
    fields.update(kw)
    charge = Charge(**fields)
    session.add(charge)
    session.commit()
    return charge


def seed_drive(session: Session, **kw: Any) -> Drive:
    """一条行程 (默认: 2026-09-10 UTC 00:32→01:44, 42.5km)。"""
    fields: dict[str, Any] = {
        "id": 1, "start_date": datetime(2026, 9, 10, 0, 32),
        "end_date": datetime(2026, 9, 10, 1, 44),
        "distance": 42.5, "duration_min": 72, "speed_max": 118,
        "start_address_id": 1, "end_address_id": 2,
    }
    fields.update(kw)
    drive = Drive(**fields)
    session.add(drive)
    session.commit()
    return drive


def seed_position(session: Session, drive_id: int, **kw: Any) -> Position:
    """一个轨迹点 (默认: 深圳附近, 30km/h, 45kW)。"""
    fields: dict[str, Any] = {
        "id": None, "drive_id": drive_id,
        "date": datetime(2026, 9, 10, 0, 32),
        "longitude": 114.05, "latitude": 22.55, "speed": 30.0, "power": 45000.0,
    }
    fields.update(kw)
    position = Position(**fields)
    session.add(position)
    session.commit()
    return position


def seed_positions(session: Session, drive_id: int,
                   rows: list[dict[str, Any]]) -> list[Position]:
    """一批轨迹点一次入库 (add_all + 单次 commit)。

    seed_position 每点一次 commit, NAS 磁盘高压下一次 fsync ~100ms,
    大轨迹种子 (降采样用例 10001 点) 光播种就能拖十几分钟;
    上百点的批量一律走这里, rows 内字段同 seed_position 的覆盖参数。
    """
    positions = [Position(drive_id=drive_id, **r) for r in rows]
    session.add_all(positions)
    session.commit()
    return positions


def seed_addresses(session: Session) -> None:
    """默认地址: 1=深圳南山 (起), 2=东莞长安 (终)。"""
    session.add(Address(id=1, name="华为立体车库", city="深圳市",
                        display_name="广东省深圳市龙岗区坂田街道"))
    session.add(Address(id=2, name="长安镇", city="东莞市",
                        display_name="广东省东莞市长安镇"))
    session.commit()


def seed_car(session: Session) -> None:
    """默认车辆: 臭哈子 (Model Y 50)。"""
    session.add(Car(id=1, name="臭哈子", model="Y", trim_badging="50", vin="LRW1"))
    session.commit()
