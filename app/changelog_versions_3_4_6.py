"""更新日志归档: 3.4.6 批次 (2026-10-06 —— 地图设置「测试」钮手机端翻车根
修; 同日第二批, 照 3.4.2 的规矩按批次单独拆文件, 列表拼接后顺序不变
(新→老))。文案照 3.3.3 起的重写规矩: 使用者视角, 报好处。"""
from typing import Final

from .schemas import ChangelogItem, ChangelogVersion

VERSIONS_3_4_6: Final[list[ChangelogVersion]] = [
    ChangelogVersion(version="3.4.6", date="2026-10-06", items=[
        ChangelogItem(kind="修复", text="地图设置的「测试」在手机上总转成失"
                                       "败: 换成直接问高德接口验 Key, 几秒就"
                                       "出结果, 手机电脑一个准。Key 填错、安"
                                       "全码配错、Key 类型选错, 各报各的明"
                                       "白话, 不用再干等到超时猜原因。"),
    ]),
]
