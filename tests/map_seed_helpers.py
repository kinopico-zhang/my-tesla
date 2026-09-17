"""足迹地图测试种子助手: 两点行程与详情行程的快捷播种。
拆自 test_map.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime, timedelta


from tests.seed_factories import seed_drive, seed_position



def _two_point_drive(db, drive_id, start):
    seed_drive(db, id=drive_id, start_date=start,
               end_date=start + timedelta(hours=1),
               distance=12.34, duration_min=25)
    seed_position(db, drive_id, id=None, date=start,
                  longitude=114.05, latitude=22.55)
    seed_position(db, drive_id, id=None, date=start + timedelta(minutes=10),
                  longitude=114.06, latitude=22.56)


def _seed_detail_drive(db, drive_id):
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=drive_id, start_date=start,
               end_date=start + timedelta(hours=1),
               distance=10.0, duration_min=60)
    seed_position(db, drive_id, id=None, date=start,
                  longitude=114.05, latitude=22.55)
    seed_position(db, drive_id, id=None, date=start + timedelta(minutes=10),
                  longitude=114.06, latitude=22.56)
