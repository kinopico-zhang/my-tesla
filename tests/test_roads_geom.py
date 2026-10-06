"""roads_geom 几何工具测试: 时间抽稀 / 方位角象限 / 折线里程 / 跳档阈值 /
DP 压缩 (含保推断区间的 dp_ranges)。纯函数无 IO。"""
from app.tesla.roads_geom import (DP_EPS, GAP_FLOOR_KM, RoadPoint,
                                  bearing_deg, decimate_by_time,
                                  douglas_peucker, dp_ranges,
                                  gap_threshold_km, polyline_km, wgs_km)


def _pts(spacing_s=1.0, n=20, lng0=114.0, lat0=22.5, dlng=0.0001):
    """一条向东北方向匀速直线采样 (1s/点, ~11m/段)。"""
    return [RoadPoint(lng=lng0 + i * dlng, lat=lat0 + i * dlng * 0.5,
                      sp=40.0, ts=1000.0 + i * spacing_s)
            for i in range(n)]


# ---------------------------------------------------------------- 时间抽稀
def test_decimate_keeps_first_last_and_step():
    """1s 原始采样压到 5s/点: 首尾恒留 (尾点哪怕离上一个保留点不足 5s),
    其余相邻保留点间隔 ≥5s。"""
    dec = decimate_by_time(_pts(n=22))
    assert dec[0].ts == 1000.0 and dec[-1].ts == 1021.0   # 首尾恒留
    for a, b in zip(dec[:-1], dec[1:-1]):                 # 尾点不计 (保尾特例)
        assert b.ts - a.ts >= 5.0


def test_decimate_short_input_passthrough():
    """≤2 点不成抽稀 (原样返回新列表)。"""
    one = _pts(n=1)
    assert decimate_by_time(one) == one
    two = _pts(n=2)
    assert decimate_by_time(two) == two


# ---------------------------------------------------------------- 方位角
def test_bearing_quadrants():
    """正北 0 / 正东 90 / 正南 180 / 正西 270; 两点重合返回 0。"""
    o = (114.0, 22.5)
    assert bearing_deg(o, (114.0, 22.51)) == 0.0        # 北
    assert abs(bearing_deg(o, (114.01, 22.5)) - 90.0) < 1e-6   # 东
    assert abs(bearing_deg(o, (114.0, 22.49)) - 180.0) < 1e-6  # 南
    assert abs(bearing_deg(o, (113.99, 22.5)) - 270.0) < 1e-6  # 西
    assert bearing_deg(o, o) == 0.0                      # 重合兜底


# ---------------------------------------------------------------- 里程与断档
def test_polyline_km_equals_segment_sum():
    pts = [(114.0, 22.5), (114.01, 22.5), (114.01, 22.51)]
    assert polyline_km(pts) == (wgs_km(pts[0], pts[1]) + wgs_km(pts[1], pts[2]))


def test_gap_threshold_floor_and_median():
    """城市短段 (~10m/段) → 触底 160m; 大段 (2km/段) → 中位 ×10。"""
    assert gap_threshold_km([(114.0, 22.5), (114.0001, 22.5)]) == GAP_FLOOR_KM
    far = [(114.0 + i * 0.02, 22.5) for i in range(10)]   # ~2km/段
    assert gap_threshold_km(far) > 15.0                    # ~20km


# ---------------------------------------------------------------- DP 压缩
def test_dp_collapses_collinear_keeps_deviant():
    """共线中间点全压掉; 偏离 5m 阈值以上的拐点保留; 首尾恒留。"""
    line = [(114.0 + i * 0.001, 22.5) for i in range(10)]
    assert douglas_peucker(line) == [line[0], line[-1]]
    zig = list(line)
    zig[5] = (zig[5][0], 22.5 + 0.001)          # 偏 ~111m >> DP_EPS
    kept = douglas_peucker(zig)
    assert zig[5] in kept and zig[0] in kept and zig[-1] in kept
    # 拐点两侧的邻点对新弦线也偏超阈值 (拐角几何, 非误报): 0/4/5/6/9 共 5 点
    assert len(kept) == 5


def test_dp_short_and_duplicate_points():
    """≤2 点原样返回; 首点重复 (零长段) 不炸, 也不误保留。"""
    two = [(114.0, 22.5), (114.01, 22.5)]
    assert douglas_peucker(two) == two
    assert douglas_peucker([(114.0, 22.5)]) == [(114.0, 22.5)]
    dup = [(114.0, 22.5), (114.0, 22.5), (114.01, 22.5)]
    assert douglas_peucker(dup) == [(114.0, 22.5), (114.01, 22.5)]


def test_dp_eps_scale():
    """阈值口径是度 (≈5m): 0.00006° (~6.6m) 偏离保留, 更小压掉。"""
    base = [(114.0, 22.5), (114.01, 22.5)]
    for off, kept in ((DP_EPS * 1.5, True), (DP_EPS * 0.5, False)):
        mid = (114.005, 22.5 + off)
        assert ((mid in douglas_peucker([base[0], mid, base[1]])) is kept)


# ------------------------------------------------- dp_ranges (保推断区间)
def test_dp_ranges_no_ranges_is_plain_dp():
    """没有推断区间: 退化为整条 DP。"""
    line = [(114.0 + i * 0.001, 22.5) for i in range(10)]
    assert dp_ranges(line, []) == (douglas_peucker(line), [])


def test_dp_ranges_keeps_boundaries_recomputes_ranges():
    """推断边界顶点必保 (段内 DP 首尾恒留), 两侧段各自压缩, 推断区间按
    压缩后的位置重算 —— 边界顶点归推断段也归前段 (虚线从它起)。"""
    line = [(114.0 + i * 0.001, 22.5) for i in range(10)]
    zig = list(line)
    zig[3] = (zig[3][0], 22.5 + 0.001)          # 拐点 ~111m
    final, ranges = dp_ranges(zig, [[3, 5]])
    assert zig[3] in final and zig[5] in final   # 边界必保
    assert final[0] == zig[0] and final[-1] == zig[-1]
    assert ranges == [[final.index(zig[3]), final.index(zig[5])]]
