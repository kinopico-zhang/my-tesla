"""首启引导的缺口判定 (独立仓变体): 数据源与地图两步查 Tesla 设置。

账号一步在 session_api 里判 (那里就有账号库会话); 这里只补本应用特有
的两步 —— TeslaMate 连接与高德 Key。组合仓的变体走 mytesla 前缀懒加载,
两个非 Tesla 子应用仓则恒空 (它们的引导只有账号一步)。"""
from .. import database
from ..tesla import settings_store


def wizard_missing() -> list[str]:
    """还差的配置步 ("teslamate" / "amap", 全配齐 = 空表)。"""
    with database.own_session_factory()() as own:  # pylint: disable=not-callable
        return settings_store.wizard_missing(own)
