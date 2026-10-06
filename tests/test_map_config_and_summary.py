"""足迹地图配置与汇总测试: 环境变量透传, 汇总口径。
拆自 test_map.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime


from tests.seed_factories import seed_addresses, seed_drive

# ---------------------------------------------------------------- config
def test_config_empty_without_env(auth, monkeypatch):
    monkeypatch.delenv("AMAP_KEY", raising=False)
    monkeypatch.delenv("AMAP_SECURITY_CODE", raising=False)
    monkeypatch.delenv("AMAP_STYLE", raising=False)   # 退役的 env, 有也不再看
    # 地图样式已随「不允许用户选择」退役 (2026-10-05): 固定幻影黑住前端
    # 适配层, config 只发 Key 与安全码
    assert auth.get("/tesla/map/api/config").json() == \
        {"amap_key": None, "security_code": None}


def test_config_returns_env_values(auth, monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "abc123")
    monkeypatch.setenv("AMAP_SECURITY_CODE", "sec456")
    monkeypatch.setenv("AMAP_STYLE", "amap://styles/light")
    monkeypatch.setenv("MAP_PROVIDER", "osm")   # 退役的 env, 有也不再看
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
