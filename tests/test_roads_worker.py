"""roads_worker 测试: 无 key 空转 / 水位增量 (落行即占位, 同 v 不再试) /
v2 ok 无推断行直采不重拟合 / 配额歇一小时 / 网络错误同程 3 次后放弃 /
日配额歇到零点 (跨天清账) / start·reset 生命周期。AmapClient 换假件,
不发真请求。"""
from datetime import date, datetime, timedelta

from app.tesla import roads_amap, roads_worker
from app.tesla.repository.map_roads import (done_drive_ids, road_row,
                                            roads_lite, save_road)
from app.tesla.roads_fit import ROAD_FIT_V
from tests.seed_factories import seed_drive, seed_position


class _FakeClient:
    """grasp 原样回点 (两点行程 → ok), route 规划不出路。
    grasp 抛什么 / 回什么由类属性切换 (每轮新建实例)。"""

    mode = "ok"          # ok / none / quota / error
    made = 0             # 构造次数 (日配额用例断言没构造)
    grasp_calls = 0      # 累计 grasp 调用 (attempts 放弃后不再涨)

    def __init__(self, key, transport=None, min_interval=0.0):
        self.calls = 0
        _FakeClient.made += 1

    def grasp(self, pts):
        """纠偏 (mode 切换回声/抓不到/配额/网络错误)。"""
        _FakeClient.grasp_calls += 1
        mode = _FakeClient.mode
        if mode == "quota":
            raise roads_amap.AmapQuota("over limit")
        if mode == "error":
            raise roads_amap.AmapError("boom")
        if mode == "none":
            return None
        return [(p[0], p[1]) for p in pts]

    def route(self, a, b):
        """规划 (worker 用例不触断档补路)。"""
        return None

    def close(self):
        """连接收尾 (假件无操作)。"""


def _seed(db, drive_id, km=1.5):
    """两点行程 (间距 ~1.5km, 与 echo 拟合里程对得上账)。"""
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=drive_id, start_date=start,
               end_date=start + timedelta(hours=1), distance=km)
    seed_position(db, drive_id=drive_id, id=None, date=start,
                  longitude=114.05, latitude=22.55)
    seed_position(db, drive_id=drive_id, id=None,
                  date=start + timedelta(minutes=10),
                  longitude=114.06, latitude=22.56)


def _factories():
    from app import database  # pylint: disable=import-outside-toplevel
    return database.session_factory(), database.own_session_factory()


def _round(monkeypatch, mode="ok", key="k"):
    monkeypatch.setattr(roads_amap, "AmapClient", _FakeClient)
    _FakeClient.mode = mode
    _FakeClient.made = _FakeClient.grasp_calls = 0
    if key is None:
        monkeypatch.delenv("AMAP_WEB_KEY", raising=False)
    else:
        monkeypatch.setenv("AMAP_WEB_KEY", key)
    tesla_f, own_f = _factories()
    return roads_worker._round(tesla_f, own_f)   # pylint: disable=protected-access


# ---------------------------------------------------------------- 基本盘
def test_round_without_key_idles(db, monkeypatch):
    _seed(db, 5)
    assert _round(monkeypatch, key=None) == (False, 0.0)
    assert _FakeClient.made == 0


def test_round_fits_pending_then_watermark(db, owndb, monkeypatch):
    _seed(db, 5)
    _seed(db, 6)
    progressed, pause = _round(monkeypatch)
    assert (progressed, pause) == (True, 0.0)
    assert done_drive_ids(owndb, ROAD_FIT_V) == {5, 6}
    # 两点行程间隔 10 分钟 > OUTAGE_S: v3 切成 2 段各 1 点, 各调一次 grasp
    assert _FakeClient.grasp_calls == 4
    # 第二轮: 水位已到, 没待办不再构造 client
    assert _round(monkeypatch) == (False, 0.0)
    assert _FakeClient.made == 0


def test_round_raw_fallback_row_counts_as_done(db, owndb, monkeypatch):
    """抓不到路 (v3 原始轨迹直落) 也落行占水位: 同 v 不再重试。"""
    _seed(db, 5)
    assert _round(monkeypatch, mode="none") == (True, 0.0)
    assert done_drive_ids(owndb, ROAD_FIT_V) == {5}   # 占位行也算水位
    assert _round(monkeypatch) == (False, 0.0)        # 同 v 不再重试


# ---------------------------------------------------------------- v2 直采
def test_round_adopts_v2_ok_without_refit(db, owndb, monkeypatch):
    """v2 的 ok 无推断行直采 v3 (不重拟合不烧配额); guess / 带推断桥的
    照常重算。"""
    save_road(owndb, road_row(5, "ok", 2, [114.0, 22.5, 114.01, 22.51],
                              2, 1.4, "", []))
    save_road(owndb, road_row(6, "guess", 2, [114.0, 22.5, 114.01, 22.51],
                              2, 1.4, "km_mismatch", [[0, 1]]))
    _seed(db, 5)
    _seed(db, 6)
    assert _round(monkeypatch)[0]
    assert _FakeClient.grasp_calls == 2          # 只重算了 6 (5 直采零调用)
    lite = roads_lite(owndb)
    assert lite[5] == ("ok", 2, ROAD_FIT_V)      # 直采: 几何原样进 v3
    assert lite[6][2] == ROAD_FIT_V              # guess 重算
    assert _round(monkeypatch) == (False, 0.0)   # 幂等: 无待办


# ---------------------------------------------------------------- 错误路径
def test_round_quota_pauses_without_row(db, owndb, monkeypatch):
    _seed(db, 5)
    _progressed, pause = _round(monkeypatch, mode="quota")
    assert pause == roads_worker.QUOTA_PAUSE_S
    assert not done_drive_ids(owndb, ROAD_FIT_V)      # 不落行, 下轮重试


def test_round_gives_up_after_three_errors(db, owndb, monkeypatch):  # pylint: disable=protected-access
    """同程网络/服务错误 3 次后本进程放弃 (不落行, 第 4 轮不再调用)。"""
    _seed(db, 5)
    # 计数器不在轮间清零 (helper 会清): 手工置一次, 直呼 _round 三轮
    monkeypatch.setattr(roads_amap, "AmapClient", _FakeClient)
    _FakeClient.mode = "error"
    _FakeClient.made = _FakeClient.grasp_calls = 0
    monkeypatch.setenv("AMAP_WEB_KEY", "k")
    tesla_f, own_f = _factories()
    for _ in range(3):
        assert roads_worker._round(tesla_f, own_f) == (False, 0.0)
    assert _FakeClient.grasp_calls == 3
    assert not done_drive_ids(owndb, ROAD_FIT_V)      # 网络错误不落行
    roads_worker._round(tesla_f, own_f)               # 第 4 轮: attempts 满了
    assert _FakeClient.grasp_calls == 3               # 不再调用


def test_round_day_cap_sleeps_to_midnight(db, monkeypatch):
    _seed(db, 5)
    st = roads_worker._State                            # pylint: disable=protected-access
    st.day = date.today()
    st.calls_today = roads_worker.CALL_CAP_PER_DAY
    monkeypatch.setattr(roads_worker, "_seconds_to_midnight", lambda: 1234.0)
    progressed, pause = _round(monkeypatch)
    assert not progressed and pause == 1234.0           # 歇到次日零点
    assert _FakeClient.made == 0


def test_roll_day_clears_yesterdays_cap(db, owndb, monkeypatch):
    _seed(db, 5)
    st = roads_worker._State                            # pylint: disable=protected-access
    st.day = date(2020, 1, 1)                           # 跨天: 昨天的账清零
    st.calls_today = roads_worker.CALL_CAP_PER_DAY
    assert _round(monkeypatch)[0]                       # 跨天后照常开跑
    assert done_drive_ids(owndb, ROAD_FIT_V) == {5}


# ---------------------------------------------------------------- 生命周期
def test_start_reset_lifecycle(monkeypatch):
    monkeypatch.delenv("AMAP_WEB_KEY", raising=False)
    tesla_f, own_f = _factories()
    roads_worker.start(tesla_f, own_f)
    roads_worker.start(tesla_f, own_f)                  # 幂等: 不另起
    assert roads_worker.running()
    roads_worker.nudge()
    assert roads_worker._State.wake.is_set()            # pylint: disable=protected-access
    roads_worker.reset()
    assert not roads_worker.running()
    assert not roads_worker._State.wake.is_set()        # pylint: disable=protected-access
