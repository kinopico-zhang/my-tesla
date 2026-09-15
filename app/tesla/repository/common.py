"""通用工具: 时间/日期参数 + 省市区地址解析 (充电与行程共用)
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from functools import lru_cache
import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import config
from ..models import Address
from ..schemas import RegionNode


class NotFound(LookupError):
    """查无数据 (路由捕获后转 404, detail 用异常消息)。"""


# ---------------------------------------------------------------- 时间与参数


def to_local(dt: datetime) -> datetime:
    """库内 UTC 裸时间戳 → 本地时间 (默认北京时间)。"""
    return dt.replace(tzinfo=dt_timezone.utc).astimezone(config.LOCAL_TZ)


def fdate(dt: datetime) -> str:
    """本地日期 (YYYY-MM-DD)。"""
    return to_local(dt).strftime("%Y-%m-%d")


def ftime(dt: datetime) -> str:
    """本地时间 (YYYY-MM-DD HH:MM)。"""
    return to_local(dt).strftime("%Y-%m-%d %H:%M")


def _fnum(value: float | int | None) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True)
class DateRange:
    """本地日期区间 → 库内 UTC 裸时间戳边界 ([start, end), end 为 to 次日零点)。"""

    start: datetime | None
    end: datetime | None


def _local_date_to_utc(date_str: str, days: int = 0) -> datetime:
    """本地日期零点 (默认北京时间) → UTC 裸时间戳。

    与原 SQL `date AT TIME ZONE 'Asia/Shanghai' AT TIME ZONE 'UTC'` 等价。
    """
    naive = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
    return naive.replace(tzinfo=config.LOCAL_TZ).astimezone(
        dt_timezone.utc).replace(tzinfo=None)


def parse_date_range(frm: str | None, to: str | None) -> DateRange | None:
    """解析 from/to 查询参数 (YYYY-MM-DD); 非法格式抛 ValueError (路由转 400)。"""
    if not frm and not to:
        return None
    try:
        start = _local_date_to_utc(frm) if frm else None
        end = _local_date_to_utc(to, days=1) if to else None
    except ValueError as exc:
        raise ValueError("日期格式错误, 应为 YYYY-MM-DD") from exc
    return DateRange(start=start, end=end)


@dataclass(frozen=True)
class BBox:
    """地图视野框 (西/南/东/北)。"""

    west: float
    south: float
    east: float
    north: float


def _keep_indices(count: int, per: int) -> list[int]:
    """下采样保留的下标 (0-based): 首末点必留, 中间等间隔取。

    与旧版 SQL `rn=1 OR rn=cnt OR (rn-1) % greatest(cnt/per, 1) = 0` 等价。
    """
    stride = max(count // per, 1)
    return [i for i in range(count)
            if i == 0 or i == count - 1 or i % stride == 0]


def _clean_addr(s: str | None) -> str:
    """地址去掉反查带来的尾部悬挂逗号/空白。"""
    return (s or "未知位置").rstrip(", ").strip()[:80] or "未知位置"


# ---------------------------------------------------------------- 省市区解析
# TeslaMate (OSM) 的 display_name 是逗号分隔、从细到粗的地址链:
# "POI, 路, 街道/镇, 区县, 市, 省, 邮编, 中国", 但市/区偶尔重复或缺失
# ("…, 顺德区, 佛山市, 顺德区, 广东省", 省直辖县没有市)。addresses 的
# city 列则混着 市/区/街道, 不能当层级用 —— 三级只能从 display_name 解析。

_PROV_SUF = ("省", "自治区", "特别行政区")
_CITY_SUF = ("市", "盟", "地区", "自治州")
_DIST_SUF = ("区", "县", "旗", "镇", "街道", "市")
_LEGACY_RE = re.compile(r"^(?:(.{1,12}?(?:省|自治区))?)\s*(?:(.{1,12}?市)?)"
                        r"\s*(?:(.{1,12}?(?:区|县|镇|街道))?)")


def _suffixed(token: str, suffixes: tuple[str, ...]) -> bool:
    return any(token.endswith(s) for s in suffixes)


def _scan_left(parts: list[str], start: int, suffixes: tuple[str, ...],
               window: int = 2) -> int:
    """从 start 向左 window 格内找第一个以后缀结尾的 token 下标 (找不到 = -1)。"""
    for j in range(start - 1, max(-1, start - 1 - window), -1):
        if _suffixed(parts[j], suffixes):
            return j
    return -1


@lru_cache(maxsize=4096)
def parse_region(display_name: str) -> tuple[str | None, str | None, str | None]:
    """display_name → (省, 市, 区县)。

    兼容两种格式: OSM 逗号链 (向左窗口扫描, 容忍重复/缺失/邮编/中国大陆)
    和旧版连写 "广东省深圳市龙岗区坂田街道"。解析不出省 = 无地区信息。
    """
    if not display_name:
        return (None, None, None)
    if "," not in display_name:
        m = _LEGACY_RE.match(display_name)
        g = m.groups() if m else (None, None, None)
        return (g[0] or None, g[1] or None, g[2] or None)
    parts = [p.strip() for p in display_name.split(",") if p.strip()]
    i = len(parts) - 1
    while i >= 0 and (parts[i] in ("中国", "中国大陆") or parts[i].isdigit()):
        i -= 1
    if i < 0 or not _suffixed(parts[i], _PROV_SUF):
        return (None, None, None)
    prov = parts[i]
    city = dist = None
    cj = _scan_left(parts, i, _CITY_SUF)
    if cj >= 0:
        city = parts[cj]
        dj = _scan_left(parts, cj, _DIST_SUF)
        if dj >= 0:
            dist = parts[dj]
    else:                       # 省直辖县: 没有市级, 区县提升到市层
        dj = _scan_left(parts, i, _DIST_SUF)
        if dj >= 0:
            city = parts[dj]
    return (prov, city, dist)


def region_address_ids(session: Session, path: str) -> list[int]:
    """省市区路径 → 命中的地址 id 列表 (段数即精确到哪一级)。

    空路径返回 []; 无命中返回 [] (调用方 in_([]) 自然过滤成空列表)。
    """
    segs = [s for s in (p.strip() for p in path.split("/")) if s]
    if not segs:
        return []
    ids: list[int] = []
    for aid, name in session.execute(select(Address.id, Address.display_name)).all():
        prov, city, dist = parse_region(name or "")
        if (prov == segs[0]
                and (len(segs) < 2 or city == segs[1])
                and (len(segs) < 3 or dist == segs[2])):
            ids.append(aid)
    return ids


class _RegionAcc:
    """建树用的临时累加器: 数 count, children 最后统一排序转 RegionNode。"""

    def __init__(self, name: str) -> None:
        """建一个 0 计数的空节点。"""
        self.name = name
        self.count = 0
        self.children: dict[str, _RegionAcc] = {}

    def child(self, name: str) -> "_RegionAcc":
        """取子节点 (没有就建)。"""
        node = self.children.get(name)
        if node is None:
            node = self.children[name] = _RegionAcc(name)
        return node

    def node(self) -> RegionNode:
        """转出定型的 RegionNode (children 按次数降序)。"""
        return RegionNode(
            name=self.name, count=self.count,
            children=[c.node() for c in
                      sorted(self.children.values(), key=lambda c: -c.count)])


def _acc_region_tree(names: Iterable[str | None]) -> list[RegionNode]:
    """display_name 序列 → 省→市→区县计数树 (次数降序)。

    无省信息的地址 (解析不出省) 不进树; 有市无区的计入省市两级, 省直辖县
    由 parse_region 把区县提升到市层 (口径见该函数)。
    """
    root = _RegionAcc("")
    for name in names:
        prov, city, dist = parse_region(name or "")
        if not prov:
            continue
        prov_acc = root.child(prov)
        prov_acc.count += 1
        if city:
            city_acc = prov_acc.child(city)
            city_acc.count += 1
            if dist:
                dist_acc = city_acc.child(dist)
                dist_acc.count += 1
    return [c.node() for c in
            sorted(root.children.values(), key=lambda c: -c.count)]
