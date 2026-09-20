"""Tesla 页面资产拼装助手 (3.0 单壳改版 P0 立, 仿 music_static_files.py)。

整页断言的口径: served_page(auth, path) = 路由吐的 HTML + 页面引用的全部
本地样式/脚本按出现序拼回。断言不关心片段落在 html 还是哪个拆分文件里,
也不随单壳改版 (P7 起 9 个路由同吐一个壳) 再改口径 —— 解析的是路由实际
吐出的引用, 路由指哪拼哪。

echarts.min.js 不拼: 1MB 压缩包, 里面 "touchstart" 之类的词会毒化
"not in" 回潮守卫, 断言只针对自家代码。
"""
import re

# 本地静态挂载点 (menu-user.js / changelog-page.js 在根挂载, 其余在 tesla 挂载)
_LOCAL_PREFIXES = ("/static/", "/tesla/static/")
_REF_RE = re.compile(r'<link rel="stylesheet" href="([^"]+)"'
                     r'|<script src="([^"]+)"')

# 3.0 单壳: /tesla 一个页面 (P7 切换后旧路由全 302 回这)
PAGES = ["/tesla"]

# 进程内缓存: 页面是纯 FileResponse (静态), 一次拼装全会话复用
# (不少测试文件同页断言四五个用例, 不缓存每条都走几十个 HTTP get)
_page_cache: dict[str, str] = {}
_js_cache: dict[str, str] = {}
_paths_cache: dict[str, list[str]] = {}


def page_refs(html: str) -> list[str]:
    """HTML 里按出现序引用的本地资源路径 (剥 ?v= 版本参数)。

    外链 (CDN) 与 echarts.min.js 不收 (见模块头)。"""
    refs = []
    for link, script in _REF_RE.findall(html):
        ref = link or script
        if not ref.startswith(_LOCAL_PREFIXES):
            continue                      # 高德等 CDN 脚本
        if ref.split("?")[0].endswith("echarts.min.js"):
            continue                      # 压缩包不进断言口径
        refs.append(ref.split("?")[0])
    return refs


def _assemble(auth, path: str) -> tuple[str, list[str]]:
    """路由 HTML + 引用资源文本 (拼装一次, 供 page/js 两种口径复用)。"""
    html = auth.get(path).text
    return html, page_refs(html)


def served_page(auth, path: str) -> str:
    """整页口径: HTML + 全部本地 css/js 按引用序 (整页断言用这个)。"""
    if path not in _page_cache:
        html, refs = _assemble(auth, path)
        _page_cache[path] = html + "\n" + "".join(
            auth.get(ref).text for ref in refs)
    return _page_cache[path]


def page_js(auth, path: str) -> str:
    """只拼页面引用的 <script> (守卫类断言要分清 html 与脚本时用)。"""
    if path not in _js_cache:
        _, refs = _assemble(auth, path)
        _js_cache[path] = "".join(
            auth.get(ref).text for ref in refs if not ref.endswith(".css"))
    return _js_cache[path]


def page_asset_paths(auth, path: str) -> list[str]:
    """页面引用的本地资源路径清单 (命名普查 / 结构断言用)。"""
    if path not in _paths_cache:
        _paths_cache[path] = page_refs(auth.get(path).text)
    return _paths_cache[path]
