"""充电城市下钻: 某市内的区/县/镇充电分布 (统计页城市图双击展开的二级)。

与城市维度同源同口径 —— 城市分布把区并进上级市 (2026-09-27), 下钻把
同一批充电按原始区/县重新摊开, 两层加起来对得上账。
"""
from sqlalchemy.orm import Session

from ...models import Address
from ...schemas import DistrictStat
from ..common import _fnum
from .charge_samples import CityAgg, _charge_rows
from .charging_stats import _city_name

_TOWN_SUFFIX = ("区", "县", "旗", "镇", "街道")


def _district_of(address: Address | None, city: str) -> str | None:
    """二级地区: display_name 链里市名的前一段 (…, 龙华区, 深圳市, 广东省);
    解析不出退回原始 city 字段 (东莞这类直筒子市整市一根柱)。"""
    if address is None:
        return None
    parts = [p.strip() for p in (address.display_name or "").replace("，", ",").split(",")]
    for i, part in enumerate(parts):
        if part == city and i > 0 and parts[i - 1].endswith(_TOWN_SUFFIX):
            return parts[i - 1]
    return address.city or city


def district_stats(session: Session, car_id: int | None,
                   city: str) -> list[DistrictStat]:
    """某市的区/县/镇充电分布 (次数降序, 最多 12 档); 没充电的城市给空表。"""
    rows = [r for r in _charge_rows(session, None, None, car_id)
            if _city_name(r.address) == city]
    grouped: dict[str, CityAgg] = {}
    for row in rows:
        cp = row.process
        d = grouped.setdefault(_district_of(row.address, city) or city, CityAgg())
        d.sessions += 1
        d.energy += _fnum(cp.charge_energy_used) or _fnum(cp.charge_energy_added) or 0.0
        d.cost += _fnum(cp.cost) or 0.0
    top = sorted(grouped.items(), key=lambda kv: -kv[1].sessions)[:12]
    return [DistrictStat(district=k, sessions=int(v.sessions),
                         energy=round(v.energy, 1), cost=round(v.cost, 2))
            for k, v in top]
