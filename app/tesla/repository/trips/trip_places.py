"""常去地点统计与改名 (2026-09-30 从 trip_stats 拆家: 那边顶到 200 行硬上
限)。口径 2026-09-30 用户点名换停车事件 —— 「只看我停车是在哪, 而不是路
过哪」: 挪车微程不计, 同一次停车只计一次 (详见 trip_locations)。"""
import re
from datetime import datetime
from typing import Any, Iterable, Final

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import Address, HiddenPlace, PlaceAlias
from ...schemas import TripLocRaw, TripLocSpot, TripLocStat
from ..common import PlaceCoords, _clean_addr
from ..place_names import place_name_map
from .trip_stats import _trip_rows

# 常去地点认定的最短行程 (km): 短于此算挪车不计 (2026-09-30 用户报「4栋
# 我都没去过, 为什么被标记去过很多次」—— 4栋 的 40 次实锤几乎全是 0.0-
# 0.3 公里、一两分钟的停车坪小挪动, 在 4栋/6栋 之间把车挪来挪去)。全库
# <0.5km 共 317 程、0.5-1km 只 65 程 —— 0.5 是干净的分界。
PLACE_MIN_KM: Final = 0.5

# 地址链形状: 省级前缀开头的完整反查地址 (_clean_addr 洗过的 display_name,
# Address.name 为空时才露脸)。裸地名没有这套前缀 —— 同名并组闸门靠它区分
# 「同一处的两种写法」与「碰巧同尾串的两条路」(环城东路 vs 城东路、
# G248;G326 vs G326 都不是一个地方)。
_ADDR_CHAIN: Final = re.compile(
    r"^(..?.?省(?!道)|.{2,6}自治区|.{2,6}特别行政区|(北京|上海|天津|重庆)市)")


def _same_name_canon(names: Iterable[str]) -> dict[str, str]:
    """同名并组的折入表 (2026-09-30 用户点名「如果两个地名是一样的, 就合
    并进行统计」): 显示名集合 → 组名。地址链折进「以它结尾的最长既有名」
    —— 长串与裸地名指同一处; 只认链折入, 裸名间碰巧的尾串不折。短在前处
    理, 折到的目标若自己也折过就跟着到底。"""
    canon: dict[str, str] = {}
    for name in sorted(names, key=len):
        hit = None
        if _ADDR_CHAIN.match(name):
            hit = max((m for m in canon if len(m) < len(name)
                       and name.endswith(m)), key=len, default=None)
        canon[name] = canon[hit] if hit else name
    return canon


def _count_parkings(
    trips: list[tuple[str | None, str | None, Address | None, Address | None]],
    aliases: dict[str, str],
    canon: dict[str, str],
) -> tuple[dict[str, int], dict[str, PlaceCoords]]:
    """停车事件计数: 到达 (行程终点) 记一次; 下一程的起点还是同一停车不再
    计 (按折入后的组名比 —— 同一处地名在地址库里的两种写法/地理编码漂移
    不拆账), 首程与断链 (上一程无终点) 后的起点照记。coords 各名记最近一
    次出现的坐标 (trips 按出发升序, 后写覆盖)。"""
    def group(name: str) -> str:
        return canon[aliases.get(name, name)]

    counts: dict[str, int] = {}
    coords: dict[str, PlaceCoords] = {}
    prev: str | None = None    # 上一程终点的组名: 同一停车不二计
    for sn, en, saddr, eaddr in trips:    # 名与地址同源: 有名才有址 (构造侧保证)
        if saddr is not None and sn and group(sn) != prev:
            counts[sn] = counts.get(sn, 0) + 1
            coords[sn] = PlaceCoords(lat=saddr.latitude, lng=saddr.longitude)
        if eaddr is not None and en:
            counts[en] = counts.get(en, 0) + 1
            coords[en] = PlaceCoords(lat=eaddr.latitude, lng=eaddr.longitude)
            prev = group(en)
        else:
            prev = None
    return counts, coords


def _group_spots(raws: list[str],
                 coords: dict[str, PlaceCoords],
                 ) -> list[TripLocSpot]:
    """组内各原名各自的坐标全录去重 (按 raws 次数降序, 主坐标在前):
    并组里有多个停车位置时改名弹层小地图一一点出 (2026-09-30 用户点名
    「如果一个地点, 包含多个地方, 那么打开地图, 就要显示多个地点」)。"""
    spots: list[TripLocSpot] = []
    seen: set[PlaceCoords] = set()
    for raw in raws:
        rc = coords.get(raw)
        if rc is not None and rc.lat is not None and rc.lng is not None \
                and rc not in seen:
            seen.add(rc)
            spots.append(TripLocSpot(lat=rc.lat, lng=rc.lng))
    return spots


def _loc_name(addr: Address | None, amap: dict[int, str]) -> str | None:
    """地点名: 高德逆地理名优先 (2026-10-02 用户点名「用 GPS 坐标结合高
    德, 不要相信 teslamate」—— TeslaMate 的 OSM 反查中国覆盖稀, 三成落点
    只剩「XX街道」兜底), 没查到/境外/失败回退 TeslaMate 名 (旧行为)。"""
    if addr is None:
        return None
    return amap.get(addr.id) or addr.name or _clean_addr(addr.display_name)


def _trip_stops(rows: list[Any],
                amap: dict[int, str],
                hidden: set[str]) -> list[tuple[str | None, str | None,
                                                 Address | None, Address | None]]:
    """行程停点名对 (名与地址同源: 有名才有址): 挪车微程整程不计
    (PLACE_MIN_KM 闸门, 4栋↔6栋 的停车坪小挪动); 隐藏名 (左滑删除,
    2026-10-03) 置 None —— 计数侧有名才计, 隐掉的地址停车不再计数。"""
    trips = []
    for d, start, end in rows:
        if (d.distance or 0) < PLACE_MIN_KM:
            continue
        sn, en = _loc_name(start, amap), _loc_name(end, amap)
        trips.append((None if sn in hidden else sn,
                      None if en in hidden else en, start, end))
    return trips


def trip_locations(session: Session, own: Session,
                   car_id: int | None = None) -> list[TripLocStat]:
    """常去地点: 按停车事件计 (2026-09-30 用户点名「你应该只看我停车是在
    哪, 而不是路过哪」) —— 挪车微程 (短于 PLACE_MIN_KM) 整程不计; 同一次
    停车只计一次 (见 _count_parkings)。次数就是真正停过几回, 不再是「起终
    点地址并计」的翻倍账。全量回不截帽 (旧 [:12] 帽把副题也带成谎话),
    画几张是前端的事, 总数前端自己数。

    改名 (place_aliases): 原名替换成别名, 同别名并组; 同名并组 (地址链
    折入裸地名) 见 _same_name_canon。组主坐标取组内次数最多那名 (兼容
    lat/lng 旧字段), spots 把组内各原名的坐标全录 (弹层多点标记);
    raws 把并组原名带上 (改名接口的键)。

    删除 (hidden_places, 2026-10-03 用户点名「左滑删除」): 隐 raw 原名
    → 该地址停车不计数, 组次数随之缩; 隐组显示名 → 整组不回 (组名 ==
    别名或折入后的组名, 别名并组时删任一显示名都隐得住整组)。"""
    rows = _trip_rows(session, car_id)
    aliases = {a.place: a.alias for a in own.scalars(select(PlaceAlias)).all()}
    hidden = place_hidden_set(own)
    amap = place_name_map(
        own, {a.id for _, s, e in rows for a in (s, e) if a is not None})
    trips = _trip_stops(rows, amap, hidden)
    canon = _same_name_canon({aliases.get(n, n)
                              for t in trips for n in t[:2] if n})
    counts, coords = _count_parkings(trips, aliases, canon)
    groups: dict[str, list[str]] = {}
    for raw in counts:
        groups.setdefault(canon[aliases.get(raw, raw)], []).append(raw)
    out = []
    for shown, raws in groups.items():
        if shown in hidden:
            continue
        raws.sort(key=lambda r: -counts[r])
        # 各真实地点带各自坐标 (管理页详情层点行跳地图, 2026-10-04)
        det = [TripLocRaw(name=r, trips=counts[r],
                          lat=(rc := coords.get(r) or PlaceCoords()).lat,
                          lng=rc.lng) for r in raws]
        # orig = 组里被改过名的最常 raw (2026-10-04): 前端「原名」行的数据
        # 源, 直接进构造不落局部 (trip_locations 局部数已顶满)。旧前端判据
        # 「组名不在 raws 里」被撞名组打穿 —— raw 本身就叫天玑公馆, 两处
        # 别名改到它名下后照样显示不出「原名」行
        out.append(TripLocStat(name=shown, trips=sum(counts[r] for r in raws),
                               lat=det[0].lat, lng=det[0].lng,   # 主坐标跟次数最多的原名走
                               raws=raws, details=det,
                               spots=_group_spots(raws, coords),
                               orig=next((r for r in raws if aliases.get(r)),
                                          None)))
    return sorted(out, key=lambda s: (-s.trips, s.name))


def place_hidden_set(own: Session) -> set[str]:
    """隐藏名单 (常用地点删除, 2026-10-03): raw 原名或组显示名, 管理页
    「已删除」分区照单全列。"""
    return set(own.scalars(select(HiddenPlace.place)).all())


def set_place_hidden(own: Session, places: list[str], hidden: bool) -> None:
    """删/恢复常用地点: hidden=True 落行 (统计读侧消失), False 删行恢复。
    行程数据不动 —— 删除只是统计视图的开关。"""
    if hidden:
        for place in places:
            own.merge(HiddenPlace(place=place))
    else:
        for place in places:
            own.execute(delete(HiddenPlace).where(HiddenPlace.place == place))
    own.commit()


def set_place_alias(own: Session, places: list[str], alias: str) -> None:
    """改/还原常用地点名 (统计读侧见 trip_locations; 并组多名一起改,
    空 alias = 删行还原原名)。"""
    if alias:
        for place in places:
            own.merge(PlaceAlias(place=place, alias=alias,
                                 updated_at=datetime.now()))
    else:
        for place in places:
            own.execute(delete(PlaceAlias).where(PlaceAlias.place == place))
    own.commit()
