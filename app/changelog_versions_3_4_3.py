"""更新日志归档: 3.4.3 批次 (2026-10-05 第二批, 常用地点管理交互收尾 +
加载异步化; 照 3.4.2 规矩按批次单独拆文件, 列表拼接后顺序不变 (新→老))。
2026-10-05 晚全批文案重写: 站在使用者视角报好处, 不再引对话原话。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_3: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.3", date="2026-10-05", items=[
        ChangelogItem(kind="改进", text="常用地点点开后在标题行就能改名: "
                                       "点「改名」标题就地变成输入框, 改完点"
                                       "「保存」或按回车生效; 行上不再有别的"
                                       "按钮, 行尾干净。"),
        ChangelogItem(kind="改进", text="常用地点页不再干等: 进页面列表先见"
                                       "面, 没有旧数据时提示读取中, 有旧数据"
                                       "先用着、后台悄悄换新; 数据没变化时不"
                                       "重铺, 滚动位置不跳。"),
    ]),
]
