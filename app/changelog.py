"""更新日志数据: 每个版本 = 一批改动的合并, 文案站在使用者视角。

不逐提交记版本 (一个版本可以同时含多个修复和多个功能); 版本号 x.y.z ——
x 大改版 · y 新功能 · z 问题修复, 新批次加在最上面 (新→老)。
只记 My Tesla 自己的版本线; My Music / My Money 的变化在各自应用的
日志页看 (2026-09-14 起各自独立)。
3.2.0 与更老的批次按纪元归档, 拆分史 (2026-09-21 起为 200 行模块上限
所迫, 每顶上限拆一批): pre_3_0 (2026-09-21) / 3_0、3_1 (2026-09-22) /
3_2 (2026-09-24) / 3_2_0 (2026-09-26, 3.2.0 与 3.2.3 同日并入) /
3_2_5 (2026-09-26, 3.2.4 次日并入) / 3_3_0、3_3_1 (2026-09-27) /
3_3_2 (2026-09-28) / 3_3_3 足迹地图批 (2026-09-29) / 3_3_4 足迹地图性
能与播放条布局批 (2026-10-02) / 3_3_5 常去地点改问高德批 (同日) /
3_4_0 常用地点管理升级批 (2026-10-03) / 3_4_1 组详情层批 (2026-10-04) /
3_4_2 屏缘缝条批、3_4_3 交互+异步批、3_4_4 账号三卡+Key 掩码批
(2026-10-05) / 3_4_5 详情右滑全屏页批、3_4_6 测试钮手机端根修批、
3_4_7 说明折叠/掩码/保存闸批 (2026-10-06) / 3_4_8 左缘呼出统一批、
3_5_0 首启引导页批 (2026-10-07) / 3_5_1 行程统计弱网提速批 (2026-10-08)。
2026-10-08 数据/代码分离: 上述批次 .py 全部转成 changelog_data/ 目录下
的同名 .json (纯数据, 文案一字未动), 本文件只留装载逻辑 —— 全局按版本
号降序拼装; 新批次 = 目录里加一个 json, 代码零改动 (拆文件的规矩对数据
文件退役, 与音乐 App 相同的规矩也到此对齐)。"""
import json
from pathlib import Path
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

_DATA_DIR = Path(__file__).parent / "changelog_data"


def _vkey(version: str) -> tuple[int, ...]:
    """「3.5.10」→ (3, 5, 10), 版本号降序的排序键。"""
    return tuple(int(p) for p in version.split("."))


def _load_all() -> list[ChangelogVersion]:
    """读 changelog_data/*.json (每文件一批, 文件内新→老), 全局按版本号
    降序 —— 与拆分时代 changelog.py 的拼接顺序一致 (test_changelog 钉着
    43 版全表)。键名手写取值, json 里写错键当场 KeyError, 不静默吞。"""
    out: list[ChangelogVersion] = []
    for f in sorted(_DATA_DIR.glob("*.json")):
        for raw in json.loads(f.read_text(encoding="utf-8")):
            out.append(ChangelogVersion(
                version=raw["version"], date=raw["date"],
                items=[ChangelogItem(kind=i["kind"], text=i["text"])
                       for i in raw["items"]]))
    out.sort(key=lambda v: _vkey(v.version), reverse=True)
    return out


VERSIONS: Final[list[ChangelogVersion]] = _load_all()


def entries() -> list[ChangelogVersion]:
    """全部版本, 新→老。"""
    return VERSIONS
