"""速度档直方图 (统计页三卡): 原始 positions 上 SQL 聚合。电耗卡逐条对齐
TeslaMate「不同速度下的能耗」面板 (2026-09-24 用户对账点名: 上一版公式读
岔成 ÷平地均速×1000, 120 档低 ~20%、10 档高 ~7 倍; 口径 SQL 原文从 Grafana
拉回, 生产库逐字重跑对过账); 时间/里程卡是自家口径 (全地形、不过滤行程):
- avg_consumption = Σ(power·speed) ÷ Σ(speed) × 10 (速度加权平均功率 ×10),
  avg_power = AVG(power); 平地 = 相邻海拔差 |Δ| < 1m (首采样 lag 空 → 平地);
- 档沿自然十进 0-9/10-19/… (用户点名; 面板原式单位 CASE 是 numeric 真除
  四舍五入, 档「80」= 75-84): 与面板有意差半档, 公式/平地/≥1km 过滤照旧;
- 电耗卡只收 ≥1km 行程 (面板 min_distance=1), 行过滤 Σspeed>0 且 Σ里程差
  >0; 0 档照画 (用户点名; 面板 min_speed_segment=10 砍掉, 停车采样零贡献,
  0-9 档只剩蠕行不冲天); power×speed 照面板 CAST integer 再乘 (防溢出报错)。

已结束行程 positions 不可变 → 每段聚合原料落自有库缓存 (合并分组聚合原始
点位 ~10s, 不缓存挡不起)。payload v4 = {"v": 4, "rows": [[档, 地形, n功率,
Σpower, Σpw·speed, Σspeed, Σ秒, Σ里程差], ...]}; v2 (同款自然档) 兼容读回, v1/v3 作废。
"""
import json
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from ...models import Drive, DriveHistCache

# 每档原料: n功率/Σpower/Σ(pw·speed)/Σspeed 喂电耗卡 (官方公式), Σ秒/
# Σ里程差喂时间/里程卡; 各档相加就是合并分组同款。dt/档沿按方言二选一
_AGG_SQL = """
SELECT drive_id,
  CASE WHEN ediff >= 1 THEN 1 WHEN ediff <= -1 THEN -1 ELSE 0 END AS terrain,
  {bin} AS speed_bin,
  COUNT(power) AS n_pw,
  SUM(power) AS sum_pw,
  SUM(CAST(power AS INTEGER) * CAST(speed AS INTEGER)) AS sum_ps,
  SUM(speed) AS sum_s,
  SUM(dt) AS secs,
  SUM(odo) AS km
FROM (
  SELECT p.drive_id, p.speed, p.power,
    p.elevation - LAG(p.elevation) OVER w AS ediff,
    p.odometer - LAG(p.odometer) OVER w AS odo,
    {dt} AS dt
  FROM positions p
  JOIN drives d ON d.id = p.drive_id AND d.end_date IS NOT NULL
  WHERE p.drive_id IN :ids
  WINDOW w AS (PARTITION BY p.drive_id ORDER BY p.date)
) t
GROUP BY drive_id, terrain, speed_bin
"""
_DT_PG = "EXTRACT(EPOCH FROM (p.date - LAG(p.date) OVER w))"
_DT_LITE = "(unixepoch(p.date) - unixepoch(LAG(p.date) OVER w)) * 1.0"
# 档沿: 自然十进整除 (0-9→0, 10-19→10 …, 2026-09-24 用户点名; PG smallint
# 整除即 floor, SQLite 速度非负同款)
_BIN_PG = "speed / 10 * 10"
_BIN_LITE = "CAST(speed AS INTEGER) / 10 * 10"


def _agg_sql(dialect: str) -> TextClause:
    """按方言选时长与档沿表达式 (PG: 官方原文; SQLite: 等价模拟)。"""
    pg = dialect == "postgresql"
    return text(_AGG_SQL.format(
        dt=_DT_PG if pg else _DT_LITE,
        bin=_BIN_PG if pg else _BIN_LITE)).bindparams(
        bindparam("ids", expanding=True))


def _dump(rows: list[list[Any]]) -> str:
    return json.dumps({"v": 4, "rows": rows}, separators=(",", ":"))


def _load(payload: str | None) -> list[list[Any]] | None:
    """缓存读回: v4 (自然档) 与 v2 (同款原料) 都有效; v3 (四舍五入档,
    2026-09-24 上午半天版) / v1 (旧公式) 或坏 JSON 作废 → None。"""
    try:
        obj = json.loads(payload or "")
    except (TypeError, ValueError):
        return None
    if isinstance(obj, dict) and obj.get("v") in (2, 4):
        rows = obj.get("rows")
        if isinstance(rows, list):
            return rows
    return None


def _hist_rows(session: Session, ids: list[int]) -> dict[int, list[list[Any]]]:
    """一段一档一地形一行 (缓存 JSON 结构), 没轨迹数据的段不出现。"""
    rows = session.execute(_agg_sql(session.get_bind().dialect.name),
                           {"ids": ids})
    out: dict[int, list[list[Any]]] = {}
    for did, terr, b, n_pw, sum_pw, ps, s, secs, km in rows:
        if b is None:
            continue                    # speed 全空的采样 (理论不出现)
        out.setdefault(int(did), []).append(
            [int(b), int(terr), int(n_pw),
             None if sum_pw is None else round(float(sum_pw), 6),
             None if ps is None else round(float(ps), 6),
             None if s is None else round(float(s), 6),
             None if secs is None else round(float(secs), 3),
             None if km is None else round(float(km), 6)])
    return out


def _rows_by_drive(unique: list[int], cached: dict[int, str],
                   fresh: dict[int, list[list[Any]]],
                   missing: list[int]) -> dict[int, list[list[Any]]]:
    """各段的原料行 (缓存或新算), 没轨迹数据的段不出现。"""
    rows_of: dict[int, list[list[Any]]] = {}
    for i in unique:
        rows = fresh.get(i) if i in missing else _load(cached[i])
        if rows:
            rows_of[i] = rows
    return rows_of


def _merge_bins(rows_of: dict[int, list[list[Any]]],
                eligible: set[int]) -> tuple[dict[int, list[float]],
                                             dict[int, list[Any]]]:
    """各段原料并档: bins (全地形 [Σ秒, Σ里程差]) 喂时间/里程卡; flatpk
    (平地 × ≥1km 行程的 [n功率, Σpower, Σpw·speed, Σspeed, Σ里程差]) 喂
    电耗卡 —— 各档相加就是合并分组同款。"""
    bins: dict[int, list[float]] = {}
    flatpk: dict[int, list[Any]] = {}
    for i, rows in rows_of.items():
        for b, terr, n_pw, sum_pw, ps, s, secs, km in rows:
            agg = bins.setdefault(int(b), [0.0, 0.0])
            if secs is not None:
                agg[0] += secs
            if km is not None:
                agg[1] += km
            if terr != 0 or i not in eligible:
                continue               # 电耗卡: 只平地段, 只 ≥1km 行程
            fp = flatpk.setdefault(int(b), [0, None, None, 0.0, 0.0])
            fp[0] += n_pw
            for k, v in ((3, s), (4, km)):
                if v is not None:
                    fp[k] += v
            if ps is not None:
                fp[2] = (fp[2] or 0.0) + ps
            if sum_pw is not None:
                fp[1] = (fp[1] or 0.0) + sum_pw
    return bins, flatpk


def _series(bins: dict[int, list[float]],
            flatpk: dict[int, list[Any]]) -> dict[str, Any]:
    """三卡数组: t/km 逐档 (自家口径全量); pk/pw 官方面板口径 (平地 ×
    ≥1km, 0 档照画; 行过滤 Σspeed>0 且 Σ里程差>0)。"""
    top = max(bins)
    t: list[float] = []
    km_arr: list[float] = []
    pw: list[float | None] = []
    pk: list[float | None] = []
    for k in range(0, top + 1, 10):
        secs_a, km_a = bins.get(k, (0.0, 0.0))
        t.append(round(secs_a / 60, 2))
        km_arr.append(round(km_a, 2))
        f = flatpk.get(k)
        # n功率>0 由 ps 非空保证; 官方面板: Σ(pw·speed)/Σspeed ×10 与 AVG(power)
        if f and f[2] is not None and f[3] > 0 and f[4] > 0:
            pk.append(round(f[2] / f[3] * 10, 1))
            pw.append(round(f[1] / f[0], 2))
        else:
            pk.append(None)
            pw.append(None)
    return {"step": 10, "t": t, "km": km_arr, "pw": pw, "pk": pk}


def track_hist(session: Session, own: Session,
               ids: list[int]) -> dict[str, Any] | None:
    """速度档直方图 (单条/合并同途): t=各档分钟, km=各档里程 (自家口径);
    pw=平地档平均功率 kW, pk=平地档电耗 Wh/km (官方面板口径: 平地
    Σ(power·speed)/Σ(speed)×10 与 AVG(power), 只收 ≥1km 行程, 0 档照画
    —— 见模块注)。没轨迹数据返回 None。"""
    unique = sorted(set(int(i) for i in ids))
    cached: dict[int, str] = {int(r.drive_id): r.payload for r in
                              own.query(DriveHistCache).filter(
                                  DriveHistCache.drive_id.in_(unique))}
    # 读不回 (没算过 / v3 四舍五入档 / v1 旧原料 / 坏 JSON) 一律重算重写
    missing = [i for i in unique if _load(cached.get(i)) is None]
    fresh: dict[int, list[list[Any]]] = {}
    if missing:
        fresh = _hist_rows(session, missing)
        for did in missing:
            own.merge(DriveHistCache(drive_id=did,
                                     payload=_dump(fresh.get(did, []))))
        own.commit()
    # 电耗卡只收 ≥1km 的行程 (面板 min_distance=1; NULL 距离同面板算不进)
    dist: dict[int, float | None] = {
        int(i): d for i, d in session.query(
            Drive.id, Drive.distance).filter(Drive.id.in_(unique)).all()}
    eligible = {i for i in unique if (dist.get(i) or 0) >= 1}
    rows_of = _rows_by_drive(unique, cached, fresh, missing)
    if not rows_of:
        return None
    bins, flatpk = _merge_bins(rows_of, eligible)
    if not bins:
        return None
    return _series(bins, flatpk)
