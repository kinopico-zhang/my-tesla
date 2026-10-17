"""充电列表: 条目组装/排序/过滤/分页 (SessionFilter 为查询条件载体)。

名/省市区/城市三口径高德优先 (2026-10-14 地名高德化: TeslaMate 的 OSM
反查语言/覆盖不可信), 没刷到的逐址回退 TeslaMate —— 后台慢慢刷, 刷好
一址换一址。围栏名 (家/公司) 是用户手定的, 仍最高优先 (模板也不盖它)。
"""
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ...place_tpl_store import place_tpl_values
from ...place_naming import render_place
from .charge_samples import ChargeRow, _charge_rows
from .charging_regions import _match_region
from ..common import DateRange, _clean_addr, _fnum, fdate, ftime
from ..place_names import PlaceInfo
from ..region_tree import amap_chain, amap_full, region_chain
from ...models import Address
from ...schemas import ChargingSession

_DISTRICT_SUFFIX = ("区", "县", "旗")


def _location_name(row: ChargeRow) -> str:
    if row.geofence is not None and row.geofence.name:
        return row.geofence.name
    if row.amap is not None and row.amap.name:
        return row.amap.name          # 高德名优先 (TeslaMate 名兜底在下一档)
    if row.address is not None and row.address.name:
        return row.address.name
    return "未知位置"


def _city_name(address: Address | None) -> str | None:
    """TeslaMate 兜底的城市口径: 区/县写进 city 列时, 从 display_name
    完整链 (…, 龙华区, 深圳市, 广东省) 找回上级市; 找不到保持原值。"""
    if address is None:
        return None
    city = address.city
    if not city or not city.endswith(_DISTRICT_SUFFIX):
        return city
    for part in (address.display_name or "").replace("，", ",").split(","):
        if part.strip().endswith("市"):
            return part.strip()
    return city


def _city_of(row: ChargeRow) -> str | None:
    """城市口径 (列表城市字段/城市分布图/下钻同源): 高德市优先, 直辖市
    市层缺位并省层 (北京市); 没刷到回退 TeslaMate 兜底解析。"""
    if row.amap is not None and row.amap.province:
        return row.amap.city or row.amap.province
    return _city_name(row.address)


def _region_of(address: Address | None,
               info: PlaceInfo | None = None) -> str | None:
    """省市区链 (大→小, " · " 连), 列表与详情同一口径 (用户点名信息量
    对齐 + 大到小排); 高德区划优先, 没刷到回退 TeslaMate 链解析;
    解析不出省 = None, 前端退化到市字段。"""
    if address is None:
        return None
    return amap_chain(info) or region_chain(address.display_name or "")


def _session_item(row: ChargeRow, tpl: str = "") -> ChargingSession:
    """条目组装。tpl (设置页「地点显示」) 非空时 place 带模板渲染的整行;
    围栏名 (家/公司) 是用户手定的, 有它就不套 (location 已经是围栏名)。"""
    cp = row.process
    energy_used = _fnum(cp.charge_energy_used)
    energy_added = _fnum(cp.charge_energy_added)
    cost = _fnum(cp.cost)
    base = energy_used or energy_added
    address = (amap_full(row.amap)
               or (_clean_addr(row.address.display_name) if row.address else None))
    fenced = row.geofence is not None and bool(row.geofence.name)
    return ChargingSession(
        id=cp.id,
        start=ftime(cp.start_date),
        end=ftime(cp.end_date) if cp.end_date else None,
        date=fdate(cp.start_date),
        location=_location_name(row),
        city=_city_of(row),
        address=address,
        region=_region_of(row.address, row.amap),
        place=(None if fenced else render_place(tpl, row.amap) or None),
        start_soc=cp.start_battery_level,
        end_soc=cp.end_battery_level,
        energy_added=energy_added,
        energy_used=energy_used,
        cost=cost,
        price_per_kwh=round(cost / base, 3) if cost and base else None,
        duration_min=cp.duration_min,
        outside_temp=_fnum(cp.outside_temp_avg),
        power_max=row.agg.power_max,
        is_fast=row.agg.is_fast,
        tesla_supercharger=row.agg.tesla_dc)


def _cost_of(row: ChargeRow) -> float | None:
    return row.process.cost


def _has_energy(row: ChargeRow) -> bool:
    """卡片口径的充入电量 (energy_added ?? energy_used) 不为 0: 刚插枪就
    断/记录缺口留下的 0 kWh 幽灵会话不进列表 (用户点名「充电电量 0 的
    默认不显示」)。added 有值 (哪怕是 0) 就以它为准, 与卡片显示同口径。"""
    added = _fnum(row.process.charge_energy_added)
    used = _fnum(row.process.charge_energy_used)
    return bool(added if added is not None else used)


def _energy_of(row: ChargeRow) -> float | None:
    return row.process.charge_energy_used


def _duration_of(row: ChargeRow) -> int | None:
    return row.process.duration_min


def _power_of(row: ChargeRow) -> float | None:
    return row.agg.power_max


_SORT_FIELDS = {
    "cost_desc": _cost_of, "cost_asc": _cost_of,
    "energy_desc": _energy_of, "energy_asc": _energy_of,
    "duration_desc": _duration_of, "power_desc": _power_of,
}


SORT_OPTIONS = set(_SORT_FIELDS) | {"date_desc", "date_asc"}


def _sorted_charge_rows(rows: list[ChargeRow], sort: str) -> list[ChargeRow]:
    """排序; None 值排最后 (等价 Postgres NULLS LAST)。

    元组键的第一位保证 None 之间不再比较数值位 (None < None 会抛 TypeError)。
    """
    if sort == "date_desc":
        return sorted(rows, key=lambda r: r.process.start_date, reverse=True)
    if sort == "date_asc":
        return sorted(rows, key=lambda r: r.process.start_date)
    field = _SORT_FIELDS[sort]
    if sort.endswith("_asc"):
        return sorted(rows, key=lambda r: (field(r) is None, field(r)))
    return sorted(rows, key=lambda r: (field(r) is not None, field(r)),
                  reverse=True)


class SessionFilter(BaseModel):
    """充电列表查询条件 (路由与仓库之间避免长参数列表)。"""

    model_config = ConfigDict(frozen=True)

    date_range: DateRange | None
    charge_type: str        # all / fast / slow
    query: str | None       # 地址模糊搜索
    sort: str               # SORT_OPTIONS 之一
    offset: int
    limit: int
    region: str | None = None    # 充电地点 "/" 路径 (1~3 段 = 省/市/区县, 空 = 全部)
    cost: str | None = None      # 费用记录: recorded / missing (None = 全部)
    car_id: int | None = None    # 车辆 (多车切换, None = 全部)


def list_charging_sessions(session: Session, own: Session,
                           flt: SessionFilter) -> tuple[int, list[ChargingSession]]:
    """充电列表: 0 kWh 幽灵会话剔除 → 日期/类型/搜索/车辆过滤 → 排序 →
    分页; total 为过滤后总数。"""
    rows = _charge_rows(session, own, flt.date_range, flt.query, flt.car_id)
    rows = [row for row in rows if _has_energy(row)]
    if flt.charge_type == "fast":
        rows = [row for row in rows if row.agg.is_fast]
    elif flt.charge_type == "slow":
        rows = [row for row in rows if not row.agg.is_fast]
    if flt.region:
        # 地点筛选与地点树同源同解析 (高德优先, 没刷到逐址回退), 段数即
        # 精确到哪一级
        rows = [row for row in rows
                if _match_region(row.address, flt.region, row.amap)]
    if flt.cost == "recorded":   # 已记录费用 / 未记录费用 (费用记 0 也算已记录)
        rows = [row for row in rows if row.process.cost is not None]
    elif flt.cost == "missing":
        rows = [row for row in rows if row.process.cost is None]
    total = len(rows)
    rows = _sorted_charge_rows(rows, flt.sort)
    page = rows[flt.offset:flt.offset + flt.limit]
    tpl = place_tpl_values(own)[1]   # 充电地点模板 (空 = 不套)
    return total, [_session_item(row, tpl) for row in page]
