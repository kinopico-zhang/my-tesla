"""常去地点的取名策略 (2026-10-02 #171「用 GPS 坐标结合高德, 不要信
teslamate」, 2026-10-15 从 place_worker 拆出 —— worker 只留轮次编排):

regeocode → 展示名: 最近的 POI ≤300m 优先 (送学停校门外也算「到学校」),
其次 ≤100m 的道路名 (停路边), 都没有用 区+街道 兜底。取不出回 ""
(调用方落 skip, 同 v 不再重试)。纯函数无副作用, 测试直喂 Regeocode。

2026-10-17 完整结构化 (用户点名「高德给的地址要完完整整的结构化地存
起来」): place_fields 把应答组件逐项提出 (worker 落库), render_place 把
缓存行按设置页的模板拼成展示行 —— 两头的单一来源, 前端不重抄一份。
"""
import re
from typing import TYPE_CHECKING, NamedTuple

from .roads_amap_wire import AmapSpot, Regeocode

if TYPE_CHECKING:   # 读侧形状只在类型检查要 (纯模块不挂 repository 运行时)
    from .repository.place_names import PlaceInfo

_POI_MAX_M = 300.0        # POI 认定半径: 送学停校门 300m 外也是「到学校」
_ROAD_MAX_M = 100.0       # 没有近 POI 时贴路名 (停路边)

# 空组件留下的悬空粘合: 分隔符池 (空格 + 中点/顿号/逗号/连字符, 模板里
# 用户拿它们组件件), 中间连续两段并回一段
_GLUE = " ·、，,-"
_GLUE_CHAIN = re.compile(r"[ ]*[·、，,\-][ ]*(?:[·、，,\-][ ]*)+")


def _nearest(spots: list[AmapSpot]) -> tuple[str, float] | None:
    """列表里距离最近的一条 (pois/roads 不保证按距离排, 自己挑;
    距离缺/坏的条目跳过)。"""
    best: AmapSpot | None = None
    best_d = float("inf")
    for spot in spots:
        if spot.distance is not None and spot.distance < best_d:
            best_d, best = spot.distance, spot
    return (best.name, best_d) if best is not None else None


def pick_place_name(geo: Regeocode) -> str:
    """regeocode → 展示名 (策略见模块头)。取不出回 "" (落 skip, 同 v 不再
    重试)。"""
    poi = _nearest(geo.pois)
    if poi and poi[0] and poi[1] <= _POI_MAX_M:
        return poi[0][:60]
    road = _nearest(geo.roads)
    if road and road[0] and road[1] <= _ROAD_MAX_M:
        return road[0][:60]
    return (geo.address.district + geo.address.township)[:60]


class PlaceFields(NamedTuple):
    """regeocode → 随行落库的结构化组件 (worker 写侧, v3 起): 空串 = 高德
    没给 / 越门 (POI/道路带距离门, 与取名策略同门 —— 门外不算「这儿有」)。"""

    township: str = ""   # 镇/街道 (区划层第四级)
    street: str = ""     # 门牌所在街 (streetNumber.street)
    number: str = ""     # 门牌号
    road: str = ""       # 最近道路名 (≤100m)
    poi: str = ""        # 最近 POI 名 (≤300m)
    adcode: str = ""     # 区划代码 (省市区三级的行政码)
    rec: str = ""        # 高德拼好的标准整串 (formatted_address, {推荐} 的来源)
    raw: str = ""        # 应答 regeocode 段原文 (完整保底, 新字段不用重查)


def place_fields(geo: Regeocode | None) -> PlaceFields:
    """regeocode → 组件 (与取名同门): POI ≤300m / 道路 ≤100m 才算数,
    门外空串 (模板渲染出空, 不冒充「就在这」); None (境外/失败) 全空。
    截长对齐落库列 (place_name_row 同款)。"""
    if geo is None:
        return PlaceFields()
    poi = _nearest(geo.pois)
    road = _nearest(geo.roads)
    return PlaceFields(
        township=geo.address.township[:24],
        street=geo.address.street_number.street[:48],
        number=geo.address.street_number.number[:24],
        road=road[0][:60] if road and road[0] and road[1] <= _ROAD_MAX_M else "",
        poi=poi[0][:60] if poi and poi[0] and poi[1] <= _POI_MAX_M else "",
        adcode=geo.address.adcode[:12],
        rec=geo.formatted_address[:120],
        raw=geo.raw[:65535])


def render_place(tpl: str, info: "PlaceInfo | None") -> str:
    """模板 → 展示行 (设置页「地点显示」, 2026-10-17): 变量 {名字} {省} {市}
    {区} {镇} {路} {门牌} {POI} {推荐}, 空组件渲染成空串 —— 悬空的分隔符
    (· 顿号 逗号 连字符 空格) 首尾扫掉、中间连排并回一段; 没缓存行 / 渲染
    全空 → "" (调用方走默认拼装)。{路} = 门牌街 || 最近道路 (同概念两个来
    源); 不认识的 {xxx} 原样保留 (写错了看得见)。直辖市 (高德 city 层缺
    位): {市} 并省层, {省} 不再重复 (「北京市北京市」难看, 充电城市口径
    同款) —— 省市算一个部件。"""
    if not tpl or info is None:
        return ""
    city = info.city or info.province
    vals = {"名字": info.name, "省": "" if city == info.province else info.province,
            "市": city, "区": info.district, "镇": info.township,
            "路": info.street or info.road, "门牌": info.number,
            "POI": info.poi, "推荐": info.rec}
    out: list[str] = []
    i = 0
    while i < len(tpl):
        if tpl[i] == "{":
            j = tpl.find("}", i + 1)
            if j > i:
                out.append(vals.get(tpl[i + 1:j], tpl[i:j + 1]))
                i = j + 1
                continue
        out.append(tpl[i])
        i += 1
    text = re.sub(r"\s+", " ", "".join(out)).strip()
    text = _GLUE_CHAIN.sub(lambda m: " " + m.group(0).strip(" ")[0] + " ", text)
    return text.strip(_GLUE).strip()


def place_tpl_map(infos: "dict[int, PlaceInfo]") -> "dict[str, PlaceInfo]":
    """高德名 → 组件行 (常用地点组名渲染的原料): 同名多址取先见 —— 同一
    展示名下的地址都贴着它, 组件近乎相同, 不用挑。"""
    by_name: "dict[str, PlaceInfo]" = {}
    for info in infos.values():
        if info.name:
            by_name.setdefault(info.name, info)
    return by_name


def shown_place_name(shown: str, info: "PlaceInfo | None", tpl: str,
                     hidden: set[str]) -> str | None:
    """常用地点的组显示名套模板 (只动显示层 —— 分组/并组/改名/隐藏的键
    全是 raw 名): 没模板 / 该名没有缓存行 (别名、TeslaMate 兜底名) 原样
    回, 用户起的名永远赢; 渲染空 (老行组件全缺) 也回原名。隐藏名单两头
    都要查 —— 删除动作送来的是屏幕上的行名, 套了模板那头是渲染名,
    raw 名一头查不到; 命中回 None (整组隐)。"""
    if not tpl or info is None:
        return shown
    rendered = render_place(tpl, info)
    if rendered and rendered in hidden:
        return None
    return rendered or shown
