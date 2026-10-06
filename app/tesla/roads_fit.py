"""足迹「走过之路」拟合管线 v3: 抽稀 → 按 GPS 断链切段 (时间跳 > OUTAGE_S)
→ 高德纠偏 (500/批锚重叠) → 段内抓失败/输出跳档用原始轨迹补 (实线) →
段间断链调导航推断或直连 (虚线) → 分段 DP → 里程对账 (不过整程降虚线)。

v2 教训 (2026-09-29 用户反馈「广西/云南大量虚线, 跟行程分组矛盾」): 抓路
输出跳档一律调导航补路, 绕路把 291km 长途程虚增到 480km, 对账挂了整程
降级虚线。v3 反转: 原始轨迹就是走过的铁证 (弧长与行程里程对得上), 跳档/
抓失败一律原始轨迹直落 (实线、进计数); 只有真没数据的断链才调导航推断
画虚线「可能走过」 —— 没连上的才推断。

fit_drive 纯编排 (client 注入, 不碰数据库; 重试/节流/配额在 worker)。
pts 平铺 WGS-84 [lng, lat, ...]; gaps 记推断层顶点闭区间 (前端虚线渲染
「可能走过」且计数剔除)。"""
from pydantic import BaseModel, Field

from . import roads_gcj
from .roads_amap import AmapClient
from .roads_geom import (RoadPoint, bearing_deg, decimate_by_time,
                         douglas_peucker, dp_ranges, gap_threshold_km,
                         polyline_km, wgs_km)

ROAD_FIT_V = 3     # 算法版本: v3 = 原始轨迹桥接 (v2 补路虚增里程教训, 见上)
BATCH_MAX = 500    # grasproad 单批点数上限 (批间 1 点锚重叠, 步长 499)
MAX_FILLS = 16     # 单程最多断链推断 (导航规划) 次数 (防烧配额; 超出直连)
KM_TOL = 0.40      # 里程对账容忍: 回填后 guess 全落 1.21–1.37 (GPS 弧长对
                   # 表显里程的常态虚增, 市内低速程), 0.20 全误杀; 1.42+ 仍留虚线
ROUTE_DETOL = 3.0  # 断链规划里程超直线 3 倍视为绕路, 弃补保直连
OUTAGE_S = 90.0    # 相邻原始点时间跳超过这秒数 = GPS 断链 (推断补), 否则数据连续
MIN_ROUTE_KM = 0.3    # 断链短于这距离不值得调规划 (直连)
STATIC_KM = 0.015     # 原始轨迹直落时合并静止点 (停车 GPS 抖动会虚增里程)
GRASP_LO = 0.6     # 批输出里程 / 原始弧长的 sane 窗口, 出窗弃批用原始轨迹
GRASP_HI = 1.5


class FitResult(BaseModel):
    """一段行程的拟合结果: status = ok / guess / failed / skip。

    ok=证实到路 (实线进计数); guess=可能走过 (几何保留, gaps 覆盖全程,
    虚线不进计数); failed=一点几何都没有; skip=境外或点太少 (本就没路)。"""

    status: str
    pts: list[float]         # 平铺 [lng, lat, ...] (ok/guess 有内容)
    n: int
    km: float
    err: str
    gaps: list[list[int]] = Field(default_factory=list)   # 推断层顶点闭区间


def _grasp_input(span: list[RoadPoint]) -> list[tuple[float, float, float, float, float]]:
    """一段抽稀点 → 纠偏输入 (lng, lat, sp, ag, ts): 方位角按前进方向反推
    (Position 无 heading 采样), 末点沿用前一段方向, sp 为原生 km/h。"""
    out: list[tuple[float, float, float, float, float]] = []
    for i, p in enumerate(span):
        nxt = span[i + 1] if i + 1 < len(span) else p
        ag = bearing_deg((p.lng, p.lat), (nxt.lng, nxt.lat))
        out.append((p.lng, p.lat, p.sp, ag, p.ts))
    return out


def _segments(dec: list[RoadPoint]) -> list[list[RoadPoint]]:
    """按 GPS 断链 (相邻点时间跳 > OUTAGE_S) 切段: 段内数据连续 (跳档/
    抓路失败都能用段内原始轨迹补), 段间没有点 (只能推断 —— 虚线的场景)。"""
    segs: list[list[RoadPoint]] = []
    cur = [dec[0]]
    for p in dec[1:]:
        if p.ts - cur[-1].ts > OUTAGE_S:
            segs.append(cur)
            cur = [p]
        else:
            cur.append(p)
    segs.append(cur)
    return segs


def _nearest(raw: list[tuple[float, float]], v: tuple[float, float],
             start: int) -> int:
    """raw[start:] 里离 v 最近的点下标 (输出跳档 → 原始轨迹桥接的定位)。"""
    best, best_d = start, float("inf")
    for i in range(start, len(raw)):
        d = wgs_km(raw[i], v)
        if d < best_d:
            best, best_d = i, d
    return best


def _drop_static(raw: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """原始轨迹直落前合并静止点 (挪动 < STATIC_KM): 停车 GPS 抖动一路累加
    会把几十米的挪车虚增成几公里, 对账就挂了。保首尾。"""
    if len(raw) <= 2:
        return list(raw)
    out = [raw[0]]
    for p in raw[1:-1]:
        if wgs_km(out[-1], p) >= STATIC_KM:
            out.append(p)
    out.append(raw[-1])
    return out


def _sane(got: list[tuple[float, float]],
          braw: list[tuple[float, float]]) -> bool:
    """批输出里程与原始弧长同量级才采信: 抓歪 (绕一大圈) / 抓丢 (砍半) 的
    批弃用, 整批换成原始轨迹直落。"""
    if len(braw) < 2:
        return True
    r = polyline_km(got) / max(polyline_km(braw), STATIC_KM)
    return GRASP_LO <= r <= GRASP_HI


def _fit_segment(seg: list[RoadPoint], threshold_km: float,
                 client: AmapClient) -> list[tuple[float, float]]:
    """一个连续段 → 顶点列表 (全证实层)。抓路失败 / sane 窗口出窗 / 输出
    内部跳档, 一律用段内原始轨迹补 —— GPS 为凭, 仍是「走过」(实线进
    计数); 真没数据的断链不在这层 (段间, fit_drive 推断)。"""
    raw = [(p.lng, p.lat) for p in seg]
    out: list[tuple[float, float]] = []
    cursor = 0     # 原始点游标 (跳档桥接从这往后找最近点)
    step = BATCH_MAX - 1
    for bi in range(0, len(seg), step):
        batch = seg[bi:bi + BATCH_MAX]
        braw = raw[bi:bi + len(batch)]
        got = client.grasp(_grasp_input(batch))
        if got is None or len(got) < 2 or not _sane(got, braw):
            # 抓路失败/抓歪: 原始轨迹直落 (合并静止点, GPS 为凭)
            seg_pts = douglas_peucker(_drop_static(braw))
            out.extend(seg_pts[1:] if out else seg_pts)
            continue
        for v in got:
            if out:
                d = wgs_km(out[-1], v)
                if d < STATIC_KM:
                    continue    # 批间锚点贴合/输出微动: 沿用批尾不重复进
                if d > threshold_km:
                    # 输出跳档 (批内或批间): 两端最近原始点之间的轨迹补上
                    j1 = _nearest(raw, out[-1], cursor)
                    j2 = _nearest(raw, v, j1)
                    cursor = j2
                    if j2 > j1 + 1:
                        out.extend(douglas_peucker(raw[j1:j2 + 1])[1:])
            out.append(v)
    return out


def _reconcile(km: float, km_expected: float) -> bool:
    """里程对账: 拟合里程与 TeslaMate 行程里程差太远说明几何不可信。"""
    if km_expected <= 0:
        return False
    return abs(km - km_expected) / max(km_expected, 2.0) > KM_TOL


def _pack(status: str, final: list[tuple[float, float]], err: str,
          gaps: list[list[int]], km: float) -> FitResult:
    flat = [round(v, 5) for p in final for v in p]
    return FitResult(status=status, pts=flat, n=len(final), km=round(km, 2),
                     err=err, gaps=gaps)


def fit_drive(points: list[RoadPoint], km_expected: float,
              client: AmapClient) -> FitResult:
    """一段行程 → 拟合到实际道路的折线 (全管线, 见模块 docstring)。"""
    dec = decimate_by_time(points)
    if len(points) < 2 or len(dec) < 2:   # 原始不足两点 / 抽稀后只剩首尾一点
        return FitResult(status="skip", pts=[], n=0, km=0.0, err="few_points")
    if roads_gcj.out_of_china(points[0].lng, points[0].lat) or \
            roads_gcj.out_of_china(points[-1].lng, points[-1].lat):
        return FitResult(status="skip", pts=[], n=0, km=0.0, err="abroad")
    threshold = gap_threshold_km([(p.lng, p.lat) for p in dec])
    fitted: list[tuple[float, float]] = []
    inferred: list[list[int]] = []
    fills = 0
    for si, seg in enumerate(_segments(dec)):
        if si:
            # GPS 断链: 段间没有数据, 调导航推断 (用户点名的虚线场景);
            # 规划不出/绕路/超预算保直连 —— 都算推断
            a0 = len(fitted) - 1
            b = (seg[0].lng, seg[0].lat)
            route = None
            if fills < MAX_FILLS and wgs_km(fitted[-1], b) >= MIN_ROUTE_KM:
                fills += 1
                route = client.route(fitted[-1], b)
            if route and polyline_km(route) <= ROUTE_DETOL * wgs_km(fitted[-1], b):
                fitted.extend(route[1:-1])  # 首尾与 a/b 各自重合, 只进内部
            fitted.append(b)
            inferred.append([a0, len(fitted) - 1])
        got = _fit_segment(seg, threshold, client)
        fitted.extend(got[1:] if fitted else got)
    if len(fitted) < 2:
        return FitResult(status="failed", pts=[], n=0, km=0.0, err="grab_fail")
    final, franges = dp_ranges(fitted, inferred)
    km = polyline_km(final)
    if _reconcile(km, km_expected):
        # 对账不过: 几何降级「可能走过」(整程虚线, 不进计数), 不丢
        return _pack("guess", final, "km_mismatch", [[0, len(final) - 1]], km)
    return _pack("ok", final, "", franges, km)
