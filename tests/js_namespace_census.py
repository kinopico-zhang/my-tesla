"""全局命名普查机 (test_js_namespace 的助手): 列首顶层声明口径的
名字提取 + 跨页撞名普查 (撞名全景 ALLOWED 数据在 js_namespace_allowed)。
拆自 test_js_namespace.py (结构化重构, 代码逐字节未动)。"""
import re
from collections import defaultdict

from tests.tesla_static_files import PAGES, page_asset_paths

# 列首声明: 函数/类直接取名 (只吃到名字 —— 参数/花括号在行尾, 2026-09-19
# 修: 原版整行匹配漏掉一切带参数的函数声明, toast/closeSheet 三页撞名
# 全数漏网); const/let/var 取声明符列表再细分。
# function(?=[\s*]) 防把 functionCall() 误当声明。
_DECL_RE = re.compile(
    r'^(?:async\s+)?(?:function(?=[\s*])\s*\*?\s*(?P<fn>[A-Za-z_$][\w$]*)'
    r'|class\s+(?P<cls>[A-Za-z_$][\w$]*)'
    r'|(?:const|let|var)\s+(?P<decls>.+?)\s*(?://.*)?$)')


def _split_top(text: str) -> list[str]:
    """顶层逗号切分 (括号/引号内的逗号不切; 反引号模板当引号)。"""
    parts, buf, depth, quote = [], [], 0, None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(text):   # 转义连吞一个
                buf.append(text[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
            buf.append(ch)
        elif ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _declarator_names(part: str) -> set[str]:
    """单个声明符的名字: 普通取头名, 解构取绑定名 ({a, b: c = 1} → a, c)。"""
    part = part.strip()
    if part.startswith(("{", "[")):        # 解构声明
        close = "}" if part[0] == "{" else "]"
        inner = part[1:part.find(close, 1)]
        names = []
        for item in _split_top(inner):
            m = re.match(r'\s*(?:[A-Za-z_$][\w$]*)\s*(?::\s*([A-Za-z_$][\w$]*))?',
                         item)
            if m:
                names.append(m.group(1) or item.strip())
        return {n for n in names if re.match(r"^[A-Za-z_$][\w$]*$", n)}
    m = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
    return {m.group(1)} if m else set()


def top_level_names(source: str) -> set[str]:
    """一份脚本的顶层名集合 (列首口径, 见 test_js_namespace 模块头)。"""
    names: set[str] = set()
    for line in source.splitlines():
        m = _DECL_RE.match(line)
        if not m:
            continue
        if m.group("fn"):
            names.add(m.group("fn"))
        elif m.group("cls"):
            names.add(m.group("cls"))
        else:
            for part in _split_top(m.group("decls")):
                names |= _declarator_names(part)
    return names


def _census(auth) -> dict[str, set[str]]:
    """全部页面引用脚本并集的 顶层名 → 文件名 集合。"""
    scripts: dict[str, str] = {}
    for page in PAGES:
        for ref in page_asset_paths(auth, page):
            if not ref.endswith(".css"):
                scripts.setdefault(ref, auth.get(ref).text)
    census: dict[str, set[str]] = defaultdict(set)
    for ref, text in scripts.items():
        for name in top_level_names(text):
            census[name].add(ref.rsplit("/", 1)[-1])
    return census


# ALLOWED 撞名全景数据拆到 js_namespace_allowed (200 行上限)。
