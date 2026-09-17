"""通用工具: 时间/日期参数与格式化、地图视野框、下采样、地址清洗 (充电与行程共用)。

省市区解析与地区树在 region_tree.py; 查无数据的 NotFound 也在这里。
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from ... import config


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
