"""高德 REST 客户端 (足迹道路拟合 + 地点命名共用): 轨迹纠偏 grasproad v4、
驾车规划 v3、逆地理 regeo v3。

只做协议层: 坐标换算 (WGS-84 ↔ GCJ-02, roads_gcj)、tm 增量编码、错误归类
(AmapQuota 配额可歇 / AmapError 其他; 应答形状不对也归 AmapError, 验形在
roads_amap_wire)。节流/重试/配额记账都在调用方 (roads_worker /
place_worker); transport 可注入 httpx.MockTransport 供测试。
key 必须是控制台「Web 服务」类型 (JS 端 Key 调不了 REST 纠偏)。"""
import time
from typing import TypeVar

import httpx
from pydantic import TypeAdapter, ValidationError

from . import roads_gcj
from .roads_amap_wire import (GraspPoint, Regeocode, _GRASP_RESPONSE,
                              _REGEO_RESPONSE, _ROUTE_RESPONSE)

_T = TypeVar("_T")

_GRASP_URL = "https://restapi.amap.com/v4/grasproad/driving"
_ROUTE_URL = "https://restapi.amap.com/v3/direction/driving"
_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
_TIMEOUT = 20.0
_QUOTA_CODES = {"10003", "10044"}   # v3/v4 共用的配额码 (日限/并发限)


class AmapQuota(RuntimeError):
    """当日配额用尽: 调用方应歇到明天, 不算失败。"""


class AmapError(RuntimeError):
    """其他调用失败 (网络/参数/服务端错误): 调用方可稍后重试。"""


def _parse(adapter: TypeAdapter[_T], text: str) -> _T:
    """应答文本 → 模型; 坏 JSON / 形状不对归 AmapError (可重试的失败)。"""
    try:
        return adapter.validate_json(text)
    except ValidationError as exc:
        raise AmapError(f"应答形状不对: {str(exc)[:200]}") from exc


class AmapClient:
    """纠偏 + 规划两个端点的薄封装 (无状态, worker 每轮换 key 重建)。

    min_interval 是相邻 REST 调用的最小间隔 (worker 传节流值, 测试默认 0);
    timeout 供设置页测试钮缩短等待 (默认 20s, 钮上 8s); calls 记本实例调用
    次数 (worker 日配额自记账)。"""

    def __init__(self, key: str, transport: httpx.BaseTransport | None = None,
                 min_interval: float = 0.0, timeout: float = _TIMEOUT):
        self._key = key
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._interval = min_interval
        self._next_ok = 0.0
        self.calls = 0

    def _pace(self) -> None:
        """调用间隔节流 + 计数 (grasp/route 进门都走这)。"""
        now = time.monotonic()
        if now < self._next_ok:
            time.sleep(self._next_ok - now)
            now = time.monotonic()
        self._next_ok = now + self._interval
        self.calls += 1

    def close(self) -> None:
        """释放底层连接 (worker 每轮重建时调用)。"""
        self._client.close()

    def grasp(self, pts: list[tuple[float, float, float, float, float]]
              ) -> list[tuple[float, float]] | None:
        """轨迹纠偏: pts = [(lng, lat, sp, ag, ts)] (WGS-84, ts 为绝对 Unix 秒)。
        返回纠偏后 WGS-84 折线; None = 抓路失败 (点太稀/不可上路, 30001)。"""
        self._pace()
        body: list[GraspPoint] = []
        for i, (lng, lat, sp, ag, ts) in enumerate(pts):
            x, y = roads_gcj.wgs_to_gcj(lng, lat)
            tm = int(ts) if i == 0 else int(round(ts - pts[i - 1][4]))
            body.append(GraspPoint(x=round(x, 6), y=round(y, 6),
                                   sp=round(max(sp, 0.0), 1), ag=round(ag, 1),
                                   tm=tm))
        resp = _parse(_GRASP_RESPONSE, self._client.post(
            _GRASP_URL, params={"key": self._key},
            json=[p.model_dump() for p in body]).text)
        if resp.errcode == 0:
            out = [(p.x, p.y) for p in resp.data.points]
            return [(roads_gcj.gcj_to_wgs(x, y)) for x, y in out]
        if resp.errcode == 30001:   # 抓路失败: 点太稀/离路太远, 是数据不是故障
            return None
        if str(resp.errcode) in _QUOTA_CODES:
            raise AmapQuota(f"grasproad 配额: {resp.errcode} {resp.errmsg}")
        raise AmapError(f"grasproad {resp.errcode}: {resp.errmsg}")

    def route(self, a: tuple[float, float],
              b: tuple[float, float]) -> list[tuple[float, float]] | None:
        """两点间驾车规划 (strategy=2 距离优先): 拟合断档补路用。
        返回 WGS-84 折线 (首尾即 a/b); None = 规划不出路。"""
        self._pace()
        gx, gy = roads_gcj.wgs_to_gcj(a[0], a[1])
        hx, hy = roads_gcj.wgs_to_gcj(b[0], b[1])
        resp = _parse(_ROUTE_RESPONSE, self._client.get(
            _ROUTE_URL, params={"key": self._key, "strategy": 2,
                                "origin": f"{gx:.6f},{gy:.6f}",
                                "destination": f"{hx:.6f},{hy:.6f}"}).text)
        if resp.infocode in _QUOTA_CODES:
            raise AmapQuota(f"direction 配额: {resp.info}")
        if resp.status != "1":    # v3 的 status 是字符串
            return None
        paths = resp.route.paths
        steps = paths[0].steps if paths else []
        flat: list[tuple[float, float]] = []
        for step in steps:
            for seg in step.polyline.split(";"):
                if not seg:
                    continue
                lng_s, _, lat_s = seg.partition(",")
                flat.append((float(lng_s), float(lat_s)))
        if len(flat) < 2:
            return None
        return [roads_gcj.gcj_to_wgs(x, y) for x, y in flat]

    def regeo(self, lng: float, lat: float) -> Regeocode | None:
        """逆地理 (地点命名用): WGS-84 进, extensions=all 拿 POI/道路/区划。
        返回 regeocode 模型; None = 境外坐标 (问不出中国名, 调用方记 skip
        不耗配额)。"""
        gx, gy = roads_gcj.wgs_to_gcj(lng, lat)
        if roads_gcj.out_of_china(gx, gy):
            return None
        self._pace()
        resp = _parse(_REGEO_RESPONSE, self._client.get(
            _REGEO_URL, params={"key": self._key, "extensions": "all",
                                "location": f"{gx:.6f},{gy:.6f}"}).text)
        if resp.infocode in _QUOTA_CODES:
            raise AmapQuota(f"regeo 配额: {resp.info}")
        if resp.status != "1":    # v3 的 status 是字符串
            raise AmapError(f"regeo {resp.infocode}: {resp.info}")
        return resp.regeocode
