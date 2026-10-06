"""直方图域的内部模型 (pydantic): 速度档原料行 (缓存载荷) 与并档累加器,
行车速度分布的盘缓存行。

HistRow 的盘上形态是位置数组 [档, 地形, n功率, Σpower, Σpw·speed,
Σspeed, Σ秒, Σ里程差] (缓存 v4 起就是这个布局), 验形读回按位对字段,
序列化仍按位写回 —— 盘上字节与旧 json.dumps 逐字相同, v2 同款自然档
原料兼容读回 (上午赶在改档沿前算过的段不白算)。"""
from typing import Literal

from pydantic import BaseModel, Field, model_serializer, model_validator


class HistRow(BaseModel):
    """一段一档一地形一行 (直方图原料): 盘上按位存取 (见模块注)。"""

    speed_bin: int
    terrain: int
    n_pw: int
    sum_pw: float | None
    sum_ps: float | None
    sum_speed: float | None
    secs: float | None
    km: float | None

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, value: object) -> object:
        """盘上的位置数组 → 按字段名喂给验形 (v2/v4 同布局)。"""
        if isinstance(value, (list, tuple)):
            return dict(zip(cls.model_fields, value))
        return value

    @model_serializer
    def _as_row(self) -> list[float | int | None]:
        """按位写回 (与旧 json.dumps 的嵌套 list 逐字相同)。"""
        return [self.speed_bin, self.terrain, self.n_pw, self.sum_pw,
                self.sum_ps, self.sum_speed, self.secs, self.km]


class HistPayload(BaseModel):
    """每段原料的自有库缓存载荷: v4 现行, v2 同款自然档兼容读回
    (v1 旧公式裸 list / v3 四舍五入档验不进 → 作废重算)。"""

    v: Literal[2, 4]
    rows: list[HistRow] = Field(default_factory=list)


class TimeKmBin(BaseModel):
    """并档累加器 (时间/里程卡): 全地形不过滤, 逐段原料相加。"""

    secs: float = 0.0
    km: float = 0.0


class PowerBin(BaseModel):
    """并档累加器 (电耗卡): 平地 × ≥1km 行程; Σpower/Σpw·speed 首值空
    (该档没功耗数据时保持 None, 不冒充 0)。"""

    n_pw: int = 0
    sum_pw: float | None = None
    sum_ps: float | None = None
    sum_speed: float = 0.0
    km: float = 0.0


class SpeedHist(BaseModel):
    """一条行程的速度分布: km=各速度段里程, kwh=各速度段电量。"""

    km: list[float]
    kwh: list[float]


class SpeedHistLine(BaseModel):
    """速度分布盘缓存的一行 {id, b, w} (v2 起的键名, 兼容既有盘缓存)。"""

    id: int
    b: list[float]
    w: list[float]

    def hist(self) -> SpeedHist:
        """b/w → SpeedHist (读回侧)。"""
        return SpeedHist(km=self.b, kwh=self.w)

    @classmethod
    def of(cls, drive_id: int, hist: SpeedHist) -> "SpeedHistLine":
        """SpeedHist → 盘上行 (写侧, 键名沿用 b/w)。"""
        return cls(id=drive_id, b=hist.km, w=hist.kwh)
