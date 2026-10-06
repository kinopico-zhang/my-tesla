"""更新日志归档: 3.4.4 批次 (2026-10-05 第三批 —— 账号页三卡 + 地图设置
Key 掩码 + 常用地点删除搬详情层底; 照 3.4.2 的规矩按批次单独拆文件, 列表
拼接后顺序不变 (新→老))。文案照 3.3.3 起的重写规矩: 使用者视角, 报好处。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_4: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.4", date="2026-10-05", items=[
        ChangelogItem(kind="修复", text="驾驶员列表加载失败不再装成空列表: "
                                       "有提示、旧数据留着, 重进或下拉即重"
                                       "试。"),
        ChangelogItem(kind="改进", text="账号设置重排成三块: 改名 (点「改名」"
                                       "就地变输入框)、改密码、登出 —— 不再"
                                       "弹窗。"),
        ChangelogItem(kind="改进", text="地图设置每把 Key 配一行获取方式; 已"
                                       "填的 Key 在输入框里掩码显示, 留空保存"
                                       "就是保持不变。"),
        ChangelogItem(kind="改进", text="地图样式固定深色 (幻影黑), 不用再"
                                       "选。"),
        ChangelogItem(kind="改进", text="常用地点列表行显示「N 个地点的汇"
                                       "总」, 不再显示改名前的原名。"),
        ChangelogItem(kind="改进", text="常用地点的删除挪进点开后的页面底部 "
                                       "(红色按钮, 二次确认后解除编组); 列表"
                                       "行不再左滑。"),
        ChangelogItem(kind="改进", text="数据来源与地图设置页的说明文字精"
                                       "简。"),
    ]),
]
