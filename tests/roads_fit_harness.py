"""roads_fit 测试共用的 mock 与行程拼装: 高德应答可注入的 httpx.MockTransport
客户端 (纠偏默认回声 / 规划默认不出路 / calls 逐请求记账)、锯齿/断链行程、
三点规划折线。纯拼装不碰数据库。"""
import json
from typing import Any

import httpx

from app.tesla.roads_amap import AmapClient
from app.tesla.roads_geom import RoadPoint, polyline_km


def make_client(grasp=None, route=None, calls=None):
    """纠偏/规划应答可注入的 mock 客户端: 默认纠偏原样回声 (坐标经 GCJ
    往返, 误差米级), 规划默认规划不出路; calls 逐请求记 body (grasp,
    list) / URL 参数 (route, dict)。"""
    def handler(request: httpx.Request) -> httpx.Response:
        if "grasproad" in str(request.url):
            body = json.loads(request.content)
            if calls is not None:
                calls.append(body)
            resp = grasp(body) if grasp else {"errcode": 0, "data": {"points": [
                {"x": p["x"], "y": p["y"]} for p in body]}}
            return httpx.Response(200, json=resp)
        if calls is not None:
            calls.append(dict(request.url.params))
        resp = route(dict(request.url.params)) if route else {"status": "0"}
        return httpx.Response(200, json=resp)
    return AmapClient("k", transport=httpx.MockTransport(handler))


def zigzag(n=12, dlng=0.0006):
    """锯齿行程 (6s/点抽稀全保, ±44m 振幅 DP 压不掉)。"""
    return [RoadPoint(lng=114.0 + i * dlng, lat=22.5 + (0.0004 if i % 2 else 0),
                      sp=40.0, ts=1000.0 + i * 6.0) for i in range(n)]


def km_of(points):
    """行程原始折线里程 (km)。"""
    return polyline_km([(p.lng, p.lat) for p in points])


def outage_line(nseg=2, step=10, gap_lng=0.003):
    """nseg 段东西向直线密采样 (~20m/段, 6s/点), 段间 200s 时间跳 (GPS 断链)
    + gap_lng 经度跨步 (弦 ≈ gap_lng × ~102m, 可调过/不过 MIN_ROUTE_KM)。"""
    pts = []
    for s in range(nseg):
        t0 = 1000.0 + s * (step * 6.0 + 200.0)
        pts += [RoadPoint(lng=114.0 + s * (step * 0.0002 + gap_lng)
                          + i * 0.0002, lat=22.5, sp=40.0, ts=t0 + i * 6.0)
                for i in range(step)]
    return pts


def route_poly(params, dogleg_deg=0.0):
    """起/中/终三点折线, 中点可向北外偏 (dogleg)。"""
    o, d = params["origin"].split(","), params["destination"].split(",")
    mid = [(float(o[0]) + float(d[0])) / 2,
           (float(o[1]) + float(d[1])) / 2 + dogleg_deg]
    poly = f"{o[0]},{o[1]};{mid[0]:.6f},{mid[1]:.6f};{d[0]},{d[1]}"
    return {"status": "1", "route": {"paths": [{"steps": [{"polyline": poly}]}]}}


def route_call_count(calls: list[Any]) -> int:
    """calls 里 route 请求的个数 (route 记 dict, grasp 记 list)。"""
    return sum(1 for c in calls if isinstance(c, dict))
