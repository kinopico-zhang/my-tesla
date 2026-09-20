"""足迹地图测试种子助手: 两点行程的快捷播种。"""
from datetime import timedelta


from tests.seed_factories import seed_drive, seed_position



def _two_point_drive(db, drive_id, start):
    seed_drive(db, id=drive_id, start_date=start,
               end_date=start + timedelta(hours=1),
               distance=12.34, duration_min=25)
    seed_position(db, drive_id, id=None, date=start,
                  longitude=114.05, latitude=22.55)
    seed_position(db, drive_id, id=None, date=start + timedelta(minutes=10),
                  longitude=114.06, latitude=22.56)
