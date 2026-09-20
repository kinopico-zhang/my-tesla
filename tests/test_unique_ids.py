"""页面 id 唯一门禁 (3.0 单壳改版 P0 立)。

页面内重复 id 会让 getElementById/querySelector 绑到第一个匹配上且不报
错 —— 现在按页隔离还能各自侥幸, 单壳把 9 页并进一张 DOM 后是跨视图雷区。
9 个路由各查一遍 (markup 口径; 脚本注入的动态 id 不在此列)。今天全绿,
P2 起壳内多视图共存, 这条就是硬门禁。
"""
import re
from collections import Counter

from tests.tesla_static_files import PAGES


def test_unique_ids_per_page(auth):
    for path in PAGES:
        ids = re.findall(r'id="([^"]+)"', auth.get(path).text)
        dups = sorted(i for i, c in Counter(ids).items() if c > 1)
        assert not dups, f"{path} 重复 id: {dups}"
