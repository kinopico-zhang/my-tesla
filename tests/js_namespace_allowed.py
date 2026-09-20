"""今日撞名全景 ALLOWED (test_js_namespace 的门槛数据)。
拆自 js_namespace_census (200 行上限, 数据单独成模块)。集合成员按引用路径
的 basename 记 (view/foo.js 与旧页 js/foo.js 折叠成一项)。

2026-09-19 P7 清偿为空: 旧页 44 件 js 全删后普查测得 0 族 (57 族 → 0,
历次收编: $/esc/getJSON/toast/日历五件套进 tesla-common /
tesla-time-range, 页内函数随旧页退役, VIEWS/setCar/setTimeRange 撞名
在视图迁移时改口)。空表保留: 普查仍在跑, 单壳里冒出新撞名 (改版漏收编
或新视图起名撞了别人) 一样红; 想再加条目先想清楚 —— 那多半是欠收编。
"""
ALLOWED: dict[str, set[str]] = {}
