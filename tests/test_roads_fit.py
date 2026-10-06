"""roads_fit v3 拟合管线测试: mock 与行程拼装在 roads_fit_harness。v3 口径
(2026-09-29 用户反馈虚线过多后的反转): 段内兜底 (抓路失败/回声短/sane 出窗/
输出跳档) 一律原始轨迹直落 —— 实线 ok 不进 gaps; 只有段间 GPS 断链 (时间
跳 > OUTAGE_S) 才调导航推断 —— gaps 区间画虚线「可能走过」。"""
from typing import Any

import pytest

from app.tesla.roads_amap import AmapQuota
from app.tesla.roads_fit import BATCH_MAX, fit_drive
from app.tesla.roads_geom import RoadPoint
from tests.roads_fit_harness import (km_of, make_client, outage_line,
                                     route_call_count, route_poly, zigzag)

GRASP_FAIL = {"errcode": 30001, "errmsg": "no"}


# ---------------------------------------------------------------- 主路径
def test_fit_single_batch_ok():
    pts = zigzag(12)
    res = fit_drive(pts, km_of(pts), make_client())
    assert res.status == "ok" and res.err == ""
    assert res.n == 12 and len(res.pts) == 24        # 锯齿点 DP 全留
    assert abs(res.km - km_of(pts)) < 0.05           # 回声 ≈ 原折线
    assert res.gaps == []                            # 回声全程证实


def test_fit_batches_share_anchor_point():
    """501 点跨两批: 步长 BATCH_MAX-1, 后批首点 = 前批末点 (锚重叠),
    合并时锚点不重复 (STATIC_KM 内沿用批尾)。"""
    pts = zigzag(BATCH_MAX + 10)
    calls: list[Any] = []
    res = fit_drive(pts, km_of(pts), make_client(calls=calls))
    assert res.status == "ok"
    assert len(calls) == 2 and route_call_count(calls) == 0
    assert len(calls[0]) == BATCH_MAX and len(calls[1]) == 11
    assert calls[1][0]["x"] == calls[0][-1]["x"]     # 锚: 同一点
    assert res.n == len(pts)                         # 合并无重复


def test_fit_zero_expected_km_skips_reconcile():
    """行程里程缺失 (0) 时不对账 (抓到什么是什么)。"""
    res = fit_drive(zigzag(12), 0.0, make_client())
    assert res.status == "ok"


# ------------------------------------------- 段内兜底 (v3 反转: 实线)
def test_fit_grasp_fail_falls_back_to_raw():
    """抓路失败 (30001): 原始轨迹直落 (锯齿 DP 全留), 仍 ok 实线 —— v2 曾
    整程降 guess, 2026-09-29 虚线过多的来源之一。"""
    res = fit_drive(zigzag(12), km_of(zigzag(12)),
                    make_client(grasp=lambda b: GRASP_FAIL))
    assert res.status == "ok" and res.err == ""
    assert res.n == 12 and res.gaps == []
    assert abs(res.km - km_of(zigzag(12))) < 0.05


def test_fit_bad_batch_raw_rest_kept():
    """多批里坏一批 (回 <2 点同样算坏): 坏批原始轨迹直落, 其余批次照常
    —— 整程 ok 不降级 (v2 曾留桥墩标推断)。"""
    pts = zigzag(BATCH_MAX + 10)

    def grasp(body):        # 首批 (500 点) 坏, 次批 (11 点) 回声
        if len(body) >= 400:
            return {"errcode": 0, "data": {"points": []}}
        return {"errcode": 0, "data": {"points": [{"x": p["x"], "y": p["y"]}
                                                  for p in body]}}

    calls: list[Any] = []
    res = fit_drive(pts, km_of(pts), make_client(grasp=grasp, calls=calls))
    assert res.status == "ok" and res.err == ""
    assert res.gaps == [] and route_call_count(calls) == 0
    assert res.n == len(pts)                        # 坏批直落不丢点


def test_fit_sane_window_rejects_wild_batch():
    """批输出里程出 sane 窗口 (抓歪绕大圈): 整批弃用换原始轨迹直落, 野点
    不进几何 —— v2 绕路虚增里程的另一半来源。"""
    def grasp(body):
        pts = [{"x": p["x"], "y": p["y"]} for p in body]
        pts.append({"x": body[-1]["x"], "y": 2.5})   # ~2200km 外的野点
        return {"errcode": 0, "data": {"points": pts}}

    res = fit_drive(zigzag(12), km_of(zigzag(12)), make_client(grasp=grasp))
    assert res.status == "ok" and res.gaps == []
    assert res.n == 12 and max(res.pts[1::2]) < 23.0


def test_fit_output_jump_bridges_with_raw_track():
    """纠偏输出跳档 (中段没回): 两端最近原始点之间用原始轨迹补 —— 实线
    证实不调导航 (v2 在这调 route 补路, 绕路虚增里程即虚线事故根因)。"""
    pts = [RoadPoint(lng=114.0 + i * 0.0002, lat=22.5 + (0.0005 if i == 10 else 0),
                     sp=40.0, ts=1000.0 + i * 6.0) for i in range(20)]
    def grasp(body):
        return {"errcode": 0, "data": {"points": body[:2] + body[-2:]}}
    calls: list[Any] = []
    res = fit_drive(pts, km_of(pts), make_client(grasp=grasp, calls=calls))
    assert res.status == "ok" and route_call_count(calls) == 0
    assert res.gaps == []                            # 跳档补的是证实层
    assert 22.5004 < max(res.pts[1::2]) < 22.5006    # 外偏点被原始轨迹补回


def test_fit_static_jitter_collapsed_on_fallback():
    """直落前合并静止点: 停车 GPS 抖动 (±10m 框内 30 点) 不虚增里程。"""
    pts = [RoadPoint(lng=114.0 + (5e-5 if i % 2 else -5e-5),
                     lat=22.5 + (4e-5 if i % 3 else -4e-5),
                     sp=0.0, ts=1000.0 + i * 6.0) for i in range(30)]
    res = fit_drive(pts, 0.02, make_client(grasp=lambda b: GRASP_FAIL))
    assert res.status == "ok" and res.n == 2         # 只剩首尾
    assert res.km < 0.05


# ------------------------------------------- 段间断链 (v3 虚线唯一来源)
def test_fit_outage_routes_inferred_dashed():
    """段间 GPS 断链 (200s 时间跳): 调导航补最短路, 桥段进推断区间
    (gaps → 前端虚线「可能走过」)。"""
    pts = outage_line()                              # 弦 ~0.33km 过 MIN_ROUTE_KM
    calls: list[Any] = []
    res = fit_drive(pts, km_of(pts),
                    make_client(route=lambda p: route_poly(p, dogleg_deg=0.0005),
                                calls=calls))
    assert res.status == "ok"
    assert route_call_count(calls) == 1              # 断链调了一次规划
    assert res.n == 5                                # 首/桥墩/桥点/桥墩/终
    assert res.gaps == [[1, 3]]                      # 桥段标推断
    assert 22.5002 < res.pts[5] < 22.5009            # 桥点带外偏


def test_fit_outage_chord_when_route_unusable():
    """断链弦太短 (< MIN_ROUTE_KM) 不调规划 / 规划绕路 (> 3× 弦长) 弃补
    —— 都保直连, 直连同样标推断 (虚线)。"""
    pts = outage_line(gap_lng=0.0008)
    short = fit_drive(pts, km_of(pts), make_client())
    assert short.status == "ok" and short.gaps == [[1, 2]] and short.n == 4
    far = outage_line()
    detour = fit_drive(far, km_of(far),
                       make_client(route=lambda p: route_poly(p, dogleg_deg=0.01)))
    assert detour.status == "ok" and detour.gaps == [[1, 2]] and detour.n == 4
    assert max(detour.pts[1::2]) < 22.5001           # 绕路野点没进几何


def test_fit_outage_max_fills_caps_route_calls():
    """断链推断封顶 MAX_FILLS (防烧配额): 超出的断链保直连, 都标推断。"""
    pts = outage_line(nseg=18, step=3)               # 17 处断链
    calls: list[Any] = []
    res = fit_drive(pts, km_of(pts),
                    make_client(route=route_poly, calls=calls))
    assert res.status == "ok"
    assert route_call_count(calls) == 16             # 封顶后不再调
    assert len(res.gaps) == 17                       # 断链全标推断


# ---------------------------------------------------------------- 对账与跳过
def test_fit_km_mismatch_degrades_to_guess():
    """拟合里程与行程里程差超四成 (KM_TOL): 几何降级「可能走过」, 不丢几何。"""
    pts = zigzag(12)
    res = fit_drive(pts, km_of(pts) * 3, make_client())   # 期望 3 倍
    assert res.status == "guess" and res.err == "km_mismatch"
    assert len(res.pts) == 24 and res.n == 12        # 几何保留
    assert res.gaps == [[0, 11]]                     # 整程推断


def test_fit_grab_quota_raises():
    with pytest.raises(AmapQuota):
        fit_drive(zigzag(12), 10.0,
                  make_client(grasp=lambda b: {"errcode": 10003, "errmsg": "x"}))


def test_fit_skip_abroad_and_few_points():
    abroad = [RoadPoint(lng=139.69 + i * 1e-4, lat=35.69, sp=30.0,
                        ts=1000.0 + i * 6.0) for i in range(5)]
    assert fit_drive(abroad, 1.0, make_client()).status == "skip"
    assert fit_drive(abroad, 1.0, make_client()).err == "abroad"
    few = fit_drive(zigzag(1), 1.0, make_client())
    assert (few.status, few.pts, few.n, few.km, few.err,
            few.gaps) == ("skip", [], 0, 0.0, "few_points", [])
