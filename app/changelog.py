"""更新日志数据: 每个版本 = 一批改动的合并, 文案站在使用者视角。

不逐提交记版本 (一个版本可以同时含多个修复和多个功能); 版本号 x.y.z ——
x 大改版 · y 新功能 · z 问题修复, 新批次加在最上面 (新→老)。
只记 My Tesla 自己的版本线; My Music / My Money 的变化在各自应用的
日志页看 (2026-09-14 起各自独立)。
3.2.0 与更老的批次按纪元归档: changelog_versions_3_2.py
(2026-09-24 拆; 2026-09-26 纪元归档满, 3.2.0 再拆去 changelog_versions_3_2_0,
同日 3.2.3 也拆过去) / changelog_versions_3_2_5.py (2026-09-26 拆; 2026-09-27 3.2.4 从主文件
并入, 又是 3.3.1 批顶上限) / changelog_versions_3_3_0.py (2026-09-27 拆) /
changelog_versions_3_3_1.py (2026-09-27 拆, 主文件只留拼接与出口 —— 3.3.1 批
修复/新增再进门又顶 200 行上限) / changelog_versions_3_3_2.py (2026-09-28 拆,
3.3.2 批仪表盘等再进门, 3.3.1 文件已 199 行贴顶) / changelog_versions_3_3_3.py
(2026-09-29 拆, 足迹地图「走过的路」批) / changelog_versions_3_3_4.py
(2026-10-02 拆, 足迹地图性能与播放条布局批) / changelog_versions_3_3_5.py
(2026-10-02 拆, 常去地点改问高德批) / changelog_versions_3_4_0.py
(2026-10-03 拆, 常用地点管理升级批) / changelog_versions_3_4_1.py
(2026-10-04 拆, 常用地点组详情层批) / changelog_versions_3_4_2.py
(2026-10-05 拆, 充电地图屏缘缝条批; 同日第二批 3_4_3 常用地点交互+异步, 第三
批 3_4_4 账号三卡+Key 掩码+地点删除搬详情层底; 3_3_3 起各批文案重写为使用
者视角) / changelog_versions_3_4_5.py (2026-10-06 拆, 常用地点详情改右滑
全屏页批) / changelog_versions_3_4_6.py (同日第二批拆, 地图
设置「测试」钮手机端根修批) / changelog_versions_3_4_7.py (同日第三批拆,
地图设置说明折叠/掩码/保存闸 + 足迹地图按 Key 开闸批) /
changelog_versions_3_1.py (2026-09-22 拆) /
changelog_versions_3_0.py (2026-09-22 拆) /
changelog_versions_pre_3_0.py (2026-09-21 拆), 拆家规矩与音乐 App 相同。"""
from typing import Final

from .changelog_versions_3_0 import VERSIONS_3_0
from .changelog_versions_3_1 import VERSIONS_3_1
from .changelog_versions_3_2 import VERSIONS_3_2
from .changelog_versions_3_2_0 import VERSIONS_3_2_0
from .changelog_versions_3_2_5 import VERSIONS_3_2_5
from .changelog_versions_3_3_0 import VERSIONS_3_3_0
from .changelog_versions_3_3_1 import VERSIONS_3_3_1
from .changelog_versions_3_3_2 import VERSIONS_3_3_2
from .changelog_versions_3_3_3 import VERSIONS_3_3_3
from .changelog_versions_3_3_4 import VERSIONS_3_3_4
from .changelog_versions_3_3_5 import VERSIONS_3_3_5
from .changelog_versions_3_4_0 import VERSIONS_3_4_0
from .changelog_versions_3_4_1 import VERSIONS_3_4_1
from .changelog_versions_3_4_4 import VERSIONS_3_4_4
from .changelog_versions_3_4_5 import VERSIONS_3_4_5
from .changelog_versions_3_4_6 import VERSIONS_3_4_6
from .changelog_versions_3_4_7 import VERSIONS_3_4_7
from .changelog_versions_3_4_3 import VERSIONS_3_4_3
from .changelog_versions_3_4_2 import VERSIONS_3_4_2
from .changelog_versions_pre_3_0 import VERSIONS_PRE_3_0
from .schemas import ChangelogVersion

VERSIONS: Final[list[ChangelogVersion]] = (
    VERSIONS_3_4_7 + VERSIONS_3_4_6
    + VERSIONS_3_4_5 + VERSIONS_3_4_4 + VERSIONS_3_4_3 + VERSIONS_3_4_2
    + VERSIONS_3_4_1 + VERSIONS_3_4_0
    + VERSIONS_3_3_5
    + VERSIONS_3_3_4 + VERSIONS_3_3_3
    + VERSIONS_3_3_2 + VERSIONS_3_3_1 + VERSIONS_3_3_0 + VERSIONS_3_2_5
    + VERSIONS_3_2 + VERSIONS_3_2_0 + VERSIONS_3_1 + VERSIONS_3_0
    + VERSIONS_PRE_3_0)


def entries() -> list[ChangelogVersion]:
    """全部版本, 新→老。"""
    return VERSIONS
