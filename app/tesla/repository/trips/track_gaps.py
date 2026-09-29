"""轨迹断档检测 (服务端, 原始密度) 与带断档的下采样。

断档在哪测是道口径题: 前端 splitGaps 的自适应阈值 (每 7 段中位段长 ×10,
下限 160m) 只在原始采样密度上有意义 —— 合并流总预算 12000 点, 长途段
抽稀后中位段长 100~263m, 阈值跟涨到 1~2.6km, 「抽稀间距」与「真实断档」
在抽稀视图里再也分不开 (2026-09-22 用户实报: 分组补出来的轨迹全是直线,
没沿道路补)。检测搬到服务端, 在拼完存档补路的原始点上跑同款阈值, 断档
端点强制保留过下采样, 索引随载荷下发 (含所属行程 id, 供前端回传归档)。
"""
from collections.abc import Sequence

from ..common import _keep_indices
from .gap_fills import _TrackPoint, _wgs_km


MIN_GAP_KM = 0.16   # 洞的下限, 与前端 TrackUtil.MIN_GAP_KM 同值


def detect_gap_pairs(points: Sequence[_TrackPoint]) -> list[tuple[int, int]]:
    """断档对 [(i-1, i)]: 前端 splitGaps 同款阈值 (每 7 段采样的中位段长
    ×10, 下限 160m), 严格大于才断。

    必须在原始密度上跑: 已存档的洞被补路点填平 (采样间隔 ~80m, 远低于
    阈值), 剩下的就是没存档、要前端走高德规划的真洞。"""
    lens = sorted(_wgs_km([points[i - 1].lng, points[i - 1].lat],
                          [points[i].lng, points[i].lat])
                  for i in range(1, len(points), 7))
    med = lens[len(lens) >> 1] if lens else 0.0
    thresh = max(MIN_GAP_KM, med * 10)
    return [(i - 1, i) for i in range(1, len(points))
            if _wgs_km([points[i - 1].lng, points[i - 1].lat],
                       [points[i].lng, points[i].lat]) > thresh]


def keep_with_gaps(n: int, budget: int, fill_idx: set[int],
                   gaps: Sequence[tuple[int, int]]
                   ) -> tuple[list[int], list[tuple[int, int]]]:
    """等间隔下采样 (首末必留, 补路点全保留 —— 旧规矩) + 断档两端也强制
    保留 (抽掉一个岸点, 前端就再也对不上这个洞)。

    返回 (保留下标升序列表, 断档对映射到保留下标空间)。"""
    keep = set(_keep_indices(n, budget)) | set(fill_idx)
    keep.update(i for pair in gaps for i in pair)
    kept = sorted(keep)
    at = {p: j for j, p in enumerate(kept)}
    return kept, [(at[a], at[b]) for a, b in gaps]
