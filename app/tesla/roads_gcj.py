"""WGS-84 ↔ GCJ-02 坐标转换 (火星坐标), 服务端版。

与 static/js/gcj02.js 是同一份国测局公开近似式的双份维护 (Python 侧原先
没有现成转换): 足迹道路拟合 worker 调高德 REST 要 GCJ-02 进出, 而库内
不变量始终 WGS-84, 换算只在本层做。精度 ~1-2m; 逆变换为近似式 (<1m)。"""
import math

_PI = 3.14159265358979324
_A = 6378245.0                    # 长半轴
_EE = 0.00669342162296594323      # 偏心率平方


def out_of_china(lng: float, lat: float) -> bool:
    """粗判境外 (高德路网只覆盖境内; 境外点原样进出, 拟合侧按 skip 处理)。"""
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(x: float, y: float) -> float:
    ret = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
           + 0.2 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * _PI)
            + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI)
            + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI)
            + 320.0 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = (300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
           + 0.1 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * _PI)
            + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI)
            + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI)
            + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def _delta(lng: float, lat: float) -> tuple[float, float]:
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * _PI
    magic = 1 - _EE * math.sin(rad_lat) ** 2
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    d_lng = (d_lng * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * _PI)
    return d_lng, d_lat


def wgs_to_gcj(lng: float, lat: float) -> tuple[float, float]:
    """WGS-84 → GCJ-02 (发往高德 REST 前转)。"""
    if out_of_china(lng, lat):
        return lng, lat
    d_lng, d_lat = _delta(lng, lat)
    return lng + d_lng, lat + d_lat


def gcj_to_wgs(lng: float, lat: float) -> tuple[float, float]:
    """GCJ-02 → WGS-84 (高德返回落库前转; 近似逆变换)。"""
    if out_of_china(lng, lat):
        return lng, lat
    d_lng, d_lat = _delta(lng, lat)
    return lng - d_lng, lat - d_lat
