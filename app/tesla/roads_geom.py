"""足迹道路拟合的几何工具: 时间抽稀 / 方位角 / 折线里程 / 跳档阈值 / DP 压缩
(含保推断区间的 dp_ranges)。

纯函数无 IO, roads_fit 管线与测试共用。距离口径与 gap_fills._wgs_km 一致
(等距圆柱近似); 跳档阈值与 track_gaps.detect_gap_pairs 同款 (每 7 段中位
段长 ×10, 下限 160m) —— 抽稀后的输入上算, 对纠偏输出的内部跳档判定。"""
import math
from collections.abc import Sequence

from pydantic import BaseModel

EARTH_RADIUS_KM = 6371.0
DECIMATE_S = 5.0        # 抽稀目标间距 (秒): 高德纠偏最优密度 5-10s/点
DP_EPS = 5e-5           # Douglas-Peucker 阈值 (度, ≈5m): 拟合结果压库存
GAP_FLOOR_KM = 0.16     # 断档下限, 与 track_gaps.MIN_GAP_KM 同值


class RoadPoint(BaseModel):
    """拟合管线的工作点: worker 从 Position 行转换, 测试直接构造。"""

    lng: float
    lat: float
    sp: float    # km/h (Position.speed 原生单位)
    ts: float    # Unix 秒


def wgs_km(a: Sequence[float], b: Sequence[float]) -> float:
    """两个 WGS [lng, lat] 点的近似球面距离 (与 gap_fills._wgs_km 同式)。"""
    mid_lat = math.radians((a[1] + b[1]) / 2)
    dx = math.radians(b[0] - a[0]) * math.cos(mid_lat)
    dy = math.radians(b[1] - a[1])
    return EARTH_RADIUS_KM * math.hypot(dx, dy)


def decimate_by_time(points: Sequence[RoadPoint],
                     step_s: float = DECIMATE_S) -> list[RoadPoint]:
    """按时间间隔抽稀 (保首尾): 1s 原始采样压到纠偏最优密度 5s/点。"""
    if len(points) <= 2:
        return list(points)
    out = [points[0]]
    for p in points[1:-1]:
        if p.ts - out[-1].ts >= step_s:
            out.append(p)
    out.append(points[-1])
    return out


def bearing_deg(a: Sequence[float], b: Sequence[float]) -> float:
    """a→b 的正北方位角 (0-360): grasproad 的 ag 字段 (无 heading 采样, 用
    相邻点反推; 静止两点重合时返回 0, 由调用方兜)。"""
    mid_lat = math.radians((a[1] + b[1]) / 2)
    dx = math.radians(b[0] - a[0]) * math.cos(mid_lat)
    dy = math.radians(b[1] - a[1])
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def polyline_km(pts: Sequence[Sequence[float]]) -> float:
    """折线总里程 (km)。"""
    return sum(wgs_km(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def gap_threshold_km(pts: Sequence[Sequence[float]]) -> float:
    """断档阈值: 每 7 段采样的中位段长 ×10, 下限 160m (track_gaps 同款)。"""
    lens = sorted(wgs_km(pts[i - 1], pts[i]) for i in range(1, len(pts), 7))
    med = lens[len(lens) >> 1] if lens else 0.0
    return max(GAP_FLOOR_KM, med * 10)


def _perp_dist(p: Sequence[float], a: Sequence[float],
               b: Sequence[float]) -> float:
    """p 到线段 ab 的距离 (度域近似, DP 用)。"""
    ax, ay = b[0] - a[0], b[1] - a[1]
    if ax == 0 and ay == 0:
        return wgs_km(p, a) / 111.0
    t = ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / (ax * ax + ay * ay)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * ax), p[1] - (a[1] + t * ay))


def douglas_peucker(pts: list[tuple[float, float]],
                    eps: float = DP_EPS) -> list[tuple[float, float]]:
    """栈式 Douglas-Peucker: 拟合折线压库存 (首尾恒留)。"""
    if len(pts) <= 2:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        best, best_d = -1, 0.0
        for i in range(lo + 1, hi):
            d = _perp_dist(pts[i], pts[lo], pts[hi])
            if d > best_d:
                best, best_d = i, d
        if best >= 0 and best_d > eps:
            keep[best] = True
            stack.append((lo, best))
            stack.append((best, hi))
    return [p for p, k in zip(pts, keep) if k]


def dp_ranges(pts: list[tuple[float, float]], ranges: list[list[int]]
              ) -> tuple[list[tuple[float, float]], list[list[int]]]:
    """DP 压缩但保住推断层结构 (roads_fit 段间断链补路后的收尾): 以推断
    边界切段, 段内各自压缩 (DP 首尾恒留 → 边界必保), 拼回后按段归类重算
    推断区间 —— 虚线画得出对得上号的连续段, 不被压缩揉碎。边界顶点与两侧
    段都共享 (实线止于此、虚线始于此)。"""
    n = len(pts)
    if not ranges:
        return douglas_peucker(pts), []
    inf = [False] * n          # 推断层标记: 右端闭左端开, 边界顶点归前段
    for a, b in ranges:
        for i in range(max(0, a) + 1, min(n - 1, b) + 1):
            inf[i] = True
    bounds = sorted({0, n - 1} | {i for a, b in ranges for i in (a, b)})
    final: list[tuple[float, float]] = []
    kinds: list[bool] = []
    for s, e in zip(bounds, bounds[1:]):
        if e <= s:
            continue
        seg = douglas_peucker(pts[s:e + 1])
        cls = inf[e]                     # 段归类看右端 (左边界顶点归前段)
        for k, p in enumerate(seg):
            if final and k == 0:
                continue                 # 共享边界点不重复进
            final.append(p)
            kinds.append(cls)
    out: list[list[int]] = []
    i = 0
    while i < len(kinds):                # 相邻推断段顺势合段
        if kinds[i]:
            j = i
            while j + 1 < len(kinds) and kinds[j + 1]:
                j += 1
            # 左边界顶点 (前一证实段的终点) 归推断段也归证实段: 虚线从它
            # 起、实线到它止, 两线在此接上 (与前端 rowSpans 同一口径)
            out.append([i - 1 if i > 0 else 0, j])
            i = j + 1
        else:
            i += 1
    return final, out
