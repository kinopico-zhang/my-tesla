"""足迹地图配置与汇总测试: 高德 Key 只认设置页存库 (2026-10-08 起不走
env), 汇总口径。拆自 test_map.py (结构化重构)。"""
from datetime import datetime


from app.tesla.models import AppSetting
from tests.seed_factories import seed_addresses, seed_drive

# ---------------------------------------------------------------- config
def test_config_empty_when_unset(auth, owndb):
    """没在设置页配过: config 就是空 (Key 与安全码都 None)。"""
    row = owndb.get(AppSetting, 1)
    row.amap_key = ""     # conftest 种的引导完成口径撤掉, 回到「没配」
    owndb.commit()
    assert auth.get("/tesla/map/api/config").json() == \
        {"amap_key": None, "security_code": None}


def test_config_reads_settings_row_not_env(auth, monkeypatch):
    """高德 Key 只认设置页 (2026-10-08 收敛): env 里有也不看, 设置页
    保存的即时反映 (改完即生效, 无需重启)。"""
    monkeypatch.setenv("AMAP_KEY", "env-key")
    monkeypatch.setenv("AMAP_SECURITY_CODE", "env-code")
    auth.post("/tesla/api/settings",
              json={"amap_key": "abc123", "amap_security_code": "sec456"})
    assert auth.get("/tesla/map/api/config").json() == \
        {"amap_key": "abc123", "security_code": "sec456"}


# ---------------------------------------------------------------- summary
def test_map_summary(auth, db):
    seed_addresses(db)
    seed_drive(db, id=1, distance=52525.4, duration_min=66000,
               start_date=datetime(2025, 3, 24, 4, 0),
               end_date=datetime(2025, 3, 24, 5, 0))
    d = auth.get("/tesla/map/api/summary").json()
    assert d == {"drives": 1, "distance_km": 52525.4, "duration_min": 66000,
                 "first_date": "2025-03-24", "last_date": "2025-03-24"}
    # 日期过滤 (本地日期)
    d2 = auth.get("/tesla/map/api/summary",
                  params={"from": "2026-01-01"}).json()
    assert d2 == {"drives": 0, "distance_km": 0.0, "duration_min": 0,
                  "first_date": None, "last_date": None}
