"""高德逆地理命名缓存的存取 (2026-10-02 用户点名「用 GPS 坐标结合高德,
不要相信 teslamate」): place_worker 回填写, 常去地点统计读; 2026-10-14
地名高德化起, 行程起终点与充电地点的省市区/城市也读这里。

place_names 一址一行 (键 = TeslaMate address_id): 读侧 IN 查只回 ok 的行
—— 有名字 (v1/v2 同策略取名) 或有省市区 (v2 起) 都算可用; v1 老行区划
空, 区划类消费对那址回退 TeslaMate (后台慢慢刷, 刷好一址换一址)。
境外/失败的地址不落 ok 行, 读侧自然回退 TeslaMate 名 (旧行为)。
all_address_coords 是 TeslaMate 侧的全量坐标清单 (worker 的待办面)。"""
# pylint: disable=duplicate-code   # PlaceInfo 的组件段与 place_naming.PlaceFields
# 有意平行 (读侧/写侧同名字段; 判重比的是剥掉注释的代码行, 注释写得再不同
# 也撞) —— 不合并成继承: NamedTuple 继承会把组件排到 name 前面, 读侧构造
# 与 select 顺序全乱; place_worker 对 _State 样板同款处理
from typing import Iterable, NamedTuple

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..place_naming import PlaceFields
from ..models import Address, PlaceName


class PlaceInfo(NamedTuple):
    """读侧形状: 地名 + 省市区区划 (v2 起有) + 结构化组件 (v3 起: 镇/门牌
    街/门牌号/最近道路/最近 POI/推荐串 —— 设置页「地点显示」模板的原料;
    v1/v2 老行组件全空, 模板渲染出空由消费侧回退默认拼装)。"""

    name: str
    province: str
    city: str
    district: str
    township: str = ""    # 镇/街道 (v3 组件, 写侧 PlaceFields 同名)
    street: str = ""      # 门牌所在街
    number: str = ""      # 门牌号
    road: str = ""        # 最近道路名
    poi: str = ""         # 最近 POI 名
    rec: str = ""         # 高德推荐整串


def place_name_map(own: Session, ids: Iterable[int]) -> dict[int, str]:
    """地址 id → 高德名 (只回 ok 且有名字的; 空 ids 短路回空表 ——
    in_() 吃空列表会查成全表)。"""
    keys = list(ids)
    if not keys:
        return {}
    rows = own.execute(
        select(PlaceName.address_id, PlaceName.name)
        .where(PlaceName.address_id.in_(keys),
               PlaceName.status == "ok", PlaceName.name != "")).all()
    return {r[0]: r[1] for r in rows}


def place_info_map(own: Session, ids: Iterable[int]) -> dict[int, PlaceInfo]:
    """地址 id → 高德地名+区划+组件 (ok 且有名或省市区; 空 ids 短路同上)。

    v1/v2 老行 (只有名/区划) 也回 —— 组件列迁移补的默认空, 名字/区划照用;
    组件类消费 (模板) 对那址渲染出空, 逐项回退默认拼装。"""
    keys = list(ids)
    if not keys:
        return {}
    rows = own.execute(
        select(PlaceName.address_id, PlaceName.name, PlaceName.province,
               PlaceName.city, PlaceName.district, PlaceName.township,
               PlaceName.street, PlaceName.number, PlaceName.road,
               PlaceName.poi, PlaceName.rec)
        .where(PlaceName.address_id.in_(keys),
               PlaceName.status == "ok",
               or_(PlaceName.name != "", PlaceName.province != ""))).all()
    return {r[0]: PlaceInfo(*r[1:]) for r in rows}


def sample_place_infos(own: Session, limit: int = 3) -> list[PlaceInfo]:
    """模板示例的样例行 (设置页「地点显示」): 挑组件最全的 ok 行, 取
    2-3 条 —— POI/门牌街/镇都在的先, 每个变量都渲染得出来; 一条都没有
    (还没跑过命名) 回空表, 前端转成「暂无样例」提示。"""
    rows = own.execute(
        select(PlaceName)
        .where(PlaceName.status == "ok", PlaceName.name != "")
        .order_by((PlaceName.poi != "").desc(), (PlaceName.street != "").desc(),
                  (PlaceName.township != "").desc(), PlaceName.address_id)
        .limit(limit)).scalars().all()
    return [PlaceInfo(r.name, r.province, r.city, r.district, r.township,
                      r.street, r.number, r.road, r.poi, r.rec) for r in rows]


def place_search_ids(own: Session, q: str) -> list[int]:
    """搜索词命中高德名/区划/组件的地址 id (充电地址搜索的补充口径: 地名换
    成高德名后, 拿 TeslaMate 原名搜不到的, 得能在缓存里搜到 —— v3 起镇/
    门牌街/POI 也进搜索面, 用户拿小地名找充电记录)。"""
    like = f"%{q.lower()}%"
    return [r[0] for r in own.execute(
        select(PlaceName.address_id).where(or_(
            func.lower(PlaceName.name).like(like),
            func.lower(PlaceName.province).like(like),
            func.lower(PlaceName.city).like(like),
            func.lower(PlaceName.district).like(like),
            func.lower(PlaceName.township).like(like),
            func.lower(PlaceName.street).like(like),
            func.lower(PlaceName.poi).like(like)))).all()]


def done_address_ids(own: Session, ver: int) -> set[int]:
    """已处理水位 (ok/skip 都算, 只按 v): 策略版本没到的重查。"""
    return set(own.scalars(
        select(PlaceName.address_id).where(PlaceName.v == ver)))


def places_progress(session: Session, own: Session, ver: int) -> tuple[int, int]:
    """(已处理数, 总数), roads_progress 同口径: 总数 = 有坐标的全量地址,
    已处理 = 其中当前策略版本有行的 (ok/skip 都算)。后台任务页用 —— 与
    worker 待办严格对齐。"""
    ids = {i for i, _, _ in all_address_coords(session)}
    return len(done_address_ids(own, ver) & ids), len(ids)


def save_place_name(own: Session, row: PlaceName) -> None:
    """命名结果落库: 一址一行, 重写 = 先删后插 (save_road 同款)。"""
    own.execute(delete(PlaceName)
                .where(PlaceName.address_id == row.address_id))
    own.add(row)
    own.commit()


def wipe_place_names(own: Session) -> None:
    """清空全部命名行 (设置「后台任务」页重新命名用): wipe_roads 同款 ——
    成果全撤, worker 水位随行走, 从头回填。"""
    own.execute(delete(PlaceName))
    own.commit()


def all_address_coords(session: Session) -> list[tuple[int, float, float]]:
    """TeslaMate 全量地址坐标 (worker 待办面): 停车点的 WGS-84 GPS,
    空坐标的地址这里就排除 (读侧回退 TeslaMate 名)。"""
    return [(a.id, float(a.latitude), float(a.longitude))
            for a in session.scalars(select(Address))
            if a.latitude is not None and a.longitude is not None]


def place_name_row(address_id: int, status: str, v: int, name: str = "",
                   province: str = "", city: str = "", district: str = "",
                   fields: PlaceFields | None = None) -> PlaceName:
    """工厂 (road_row 同款): name 截 60 字 (与改名接口的 max_length 对齐),
    区划截 24 字 (省市区名最长也就十来字)。v3 结构化组件打包在 fields
    (place_fields 产物) —— 逐个拆传会超参数上限, 截长双保险对齐
    place_fields, 手搓行也进不了超长值。"""
    f = fields or PlaceFields()
    return PlaceName(address_id=address_id, name=name[:60],
                     province=province[:24], city=city[:24],
                     district=district[:24], township=f.township[:24],
                     street=f.street[:48], number=f.number[:24],
                     road=f.road[:60], poi=f.poi[:60], adcode=f.adcode[:12],
                     rec=f.rec[:120], raw=f.raw[:65535], status=status, v=v)
