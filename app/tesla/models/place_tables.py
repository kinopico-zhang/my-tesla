"""地点域自有表 (2026-10-03 从 mytesla_tables 拆家: 地点三表占满小半个文件,
再进新表要顶 200 行硬上限): 改名 PlaceAlias / 高德命名缓存 PlaceName /
隐藏名单 HiddenPlace。基类在 model_bases, 调用方照旧 from ..models import …。"""
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .model_bases import OwnBase


class PlaceAlias(OwnBase):
    """常用地点改名 (2026-09-30 用户点名): 键 = 常去地点统计的分组名
    (Address.name, 没有则清洗后的地址链), 值 = 用户起的名。

    统计读侧: 原名替换成别名、同别名并组 (两处原名改成一个名 → 图上并成
    一根柱); alias 空 = 不该存在的行, 删行即还原原名。改名弹层 / 设置页
    常用地点管理共用这一张表。"""

    __tablename__ = "place_aliases"

    place: Mapped[str] = mapped_column(String, primary_key=True)
    alias: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now)


class PlaceName(OwnBase):
    """高德逆地理命名缓存 (2026-10-02 用户点名「用 GPS 坐标结合高德, 不要
    相信 teslamate」): TeslaMate 的地址名来自 OSM 反查, 中国覆盖稀, 三成
    落点只剩「XX街道」兜底名。

    place_worker 拿 Address 行自带的 WGS-84 停车坐标问高德 v3 逆地理, 按
    「最近 POI (≤300m) → 道路名 (≤100m) → 区+街道」取名后落这表 (键 =
    TeslaMate address_id, 一址一行); 读侧 (常去地点) 高德名优先, 没查到
    /境外/失败回退 TeslaMate 名。v=取名策略版本, 策略改了 bump 重查;
    status: ok=有名字 / skip=境外 (不耗配额) —— 两者同 v 都算已处理
    不重查; 空坐标的地址在待办查询侧就排除, 不落行。"""

    __tablename__ = "place_names"

    address_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="ok")
    v: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class HiddenPlace(OwnBase):
    """常用地点隐藏名单 (2026-10-03 用户点名「左滑删除」): 删除 = 从常去
    地点统计里隐藏, 行程数据不动。键 = raw 原名 或 组显示名 —— 隐 raw 该
    地址的停车不再计数 (组次数随之缩), 隐组名整组不显示; 恢复 = 删行
    (设置页管理底部「已删除」分区)。"""

    __tablename__ = "hidden_places"

    place: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
