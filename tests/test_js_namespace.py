"""全局命名普查棘轮 (3.0 单壳改版 P0 立, P7 单壳切换后只剩壳一个页面)。

单壳改版把 9 个页面的脚本并进同一个全局作用域, 现在按页隔离的同名顶层
声明会互相覆盖。对页面 (/tesla) 引用脚本的并集做一次顶层名普查 (口径见
js_namespace_census, 撞名全景 ALLOWED 数据在 js_namespace_allowed):

- 撞名必须出现在 ALLOWED 且文件集合分毫不差 —— 新文件加入撞名家族、
  或冒出新撞名, 都红;
- ALLOWED 不许烂尾: 撞名收编进 tesla-common / tesla-time-range 等
  公共件后要同步删条目 (棘轮只收紧)。P7 删尽旧页后家族整体消失,
  ALLOWED 清偿为空 —— 普查与壳侧点名扫描 (下) 继续守着不回潮。

普查口径: 列首顶层声明 (function/class/const/let/var, 含解构与
"const a = 1, b = 2" 多声明符)。IIFE 内部与缩进声明是文件私有的,
不算撞名 —— gcj02/trackutil 这类整文件包裹的因此天然干净。

**安全不变式**: 壳内一个顶层名只许一个文件声明 (test_shell_runtime_
names_unique 按加载清单逐个点名, const+let 跨文件是 SyntaxError 直接
杀整个后加载文件, P5 真踩过 detailCache)。

**悬空名守卫** (test_exported_and_writable_names_have_bodies): 名字进了
某文件的 /* exported */ 清单或 /* global */ 的可写标注, 却没有任何脚本
给出真身 —— eslint 把导出清单当"本文件已定义"闭嘴, 这类雷只有普查抓
得住 (2026-09-22 routePrefix: 3.0 拆 trips.js 时函数体没跟着搬, 首播
带断档的行程一进断档步当场 ReferenceError 掐死帧循环)。
"""
import re

from tests.js_namespace_allowed import ALLOWED
from tests.js_namespace_census import _census, top_level_names
from tests.tesla_static_files import page_refs, served_page


def test_global_collisions_within_allowlist(auth):
    """撞名家族只许在 ALLOWED 之内, 且成员分毫不差 (新撞名/扩员都红)。"""
    census = _census(auth)
    colliding = {n: fs for n, fs in census.items() if len(fs) > 1}
    bad = {n: sorted(fs) for n, fs in colliding.items() if fs != ALLOWED.get(n)}
    assert not bad, "出现 ALLOWED 之外的撞名 (单壳会互相覆盖):\n" + "\n".join(
        f"  {n}: {fs}" for n, fs in sorted(bad.items()))


def test_allowlist_has_no_stale_entries(auth):
    """ALLOWED 条目必须仍与现实吻合: 收编公共件后撞名消失要及时删条目。"""
    census = _census(auth)
    colliding = {n: fs for n, fs in census.items() if len(fs) > 1}
    stale = {n: sorted(colliding.get(n, [])) for n, fs in ALLOWED.items()
             if fs != colliding.get(n)}
    assert not stale, "ALLOWED 棘轮松了 (撞名已消失或成员变动, 删/改条目):\n" \
        + "\n".join(f"  {n}: 现实是 {fs}" for n, fs in sorted(stale.items()))


def test_shell_runtime_names_unique(auth):
    """壳运行时撞名扫描: app.html 实际加载的脚本共享一个全局作用域,
    任何顶层名都不许被两个壳侧文件同时声明 (后加载者静默覆盖, const+let
    跨文件更是 SyntaxError 直接杀整个后加载文件)。跨页普查的 basename
    折叠看不出不同名壳文件间的撞, 这里按加载清单逐个点名 (P5 起成为
    门禁, P7 后是撞名问题仅剩的现役门禁)。"""
    html = served_page(auth, "/tesla")
    scripts = [r for r in page_refs(html) if r.endswith(".js")]
    owners: dict[str, str] = {}
    dups: list[str] = []
    for ref in scripts:
        base = ref.rsplit("/", 1)[-1]
        for name in top_level_names(auth.get(ref).text):
            if name in owners and owners[name] != base:
                dups.append(f"{name}: {owners[name]} <-> {base}")
            else:
                owners[name] = base
    assert not dups, "壳侧顶层名撞名 (后加载者覆盖):\n" + "\n".join(sorted(dups))


def test_exported_and_writable_names_have_bodies(auth):
    """悬空名守卫: 名字进了 /* exported */ 清单或 /* global */ 的可写标注,
    却没有任何脚本给出真身 (routePrefix 雷, 2026-09-22)。eslint 把导出
    清单当"本文件已定义"闭嘴; 真雷长这样 —— 3.0 拆 trips.js 时名字进了
    overlays 的导出清单、函数体没搬, 引用处悬空: 首播带断档的行程一进
    断档步当场 ReferenceError 掐死帧循环 (2233 实报: 播到六成停住, 补路
    回传存档后断档消失才像"自愈")。普查列首口径为主, 续行声明/多声明符
    census 看不见的, 用声明或赋值痕迹兜底认领。"""
    html = served_page(auth, "/tesla")
    sources = {r: auth.get(r).text for r in page_refs(html) if r.endswith(".js")}
    top = set()
    for text in sources.values():
        top |= top_level_names(text)
    bad: list[str] = []
    for ref, text in sources.items():
        names = set()
        m = re.search(r"/\*\s*exported\s+(.*?)\*/", text, re.S)
        if m:
            names |= {n for n in re.split(r"[,\s]+", m.group(1).strip()) if n}
        g = re.search(r"/\*\s*global\s+(.*?)\*/", text, re.S)
        if g:   # 可写全局 (如 "animRaf: writable"): 跨文件赋值目标, 没真身必炸
            names |= {e.split(":")[0].strip() for e in g.group(1).split(",")
                      if e.strip().endswith("writable")}
        missing = sorted(
            n for n in names if n not in top and not any(
                re.search(rf"function\s+{n}\s*\(|class\s+{n}\b|\b{n}\s*=(?!=)", t)
                for t in sources.values()))
        if missing:
            bad.append(f"{ref.rsplit('/', 1)[-1]}: {missing}")
    assert not bad, "导出清单/可写全局悬空 (引用处 ReferenceError):\n" \
        + "\n".join(bad)
