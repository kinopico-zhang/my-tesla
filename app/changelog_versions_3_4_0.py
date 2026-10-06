"""更新日志归档: 3.4.0 批次 (2026-10-03 拆出 —— 常用地点管理升级批,
y 位新功能批次; 照 3.3.5 的规矩按批次单独拆一个文件; 列表拼接后顺序
不变 (新→老))。2026-10-05 晚全批文案重写: 站在使用者视角报好处, 不再
引对话原话。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_0: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.0", date="2026-10-03", items=[
        ChangelogItem(kind="新增", text="常用地点管理升级: 列表全量列出 (原"
                                       "先只列最常 12 个), 点开能看到这组的"
                                       "每个真实地点、各停过几次; 单个地点和"
                                       "整组都能删。删除只是统计里不显示, 行"
                                       "程数据不动 —— 删错了在底部「已删除」"
                                       "分区里能恢复。"),
    ]),
]
