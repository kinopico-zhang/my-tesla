"""路由共用件: 日期参数解析 (400) 与 HTML 页面应答。"""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from ... import config
from .. import repository


def date_range_or_400(frm: str | None,
                      to: str | None) -> repository.DateRange | None:
    """from/to (本地日期) → 库内 UTC 边界; 坏参数直接 400。"""
    try:
        return repository.parse_date_range(frm, to)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def page_response(file_name: str,
                  directory: Path | None = None) -> FileResponse:
    """HTML 页面: 允许缓存但必须带 ETag 重新校验 (no-cache), 更新即时生效。

    目录缺省 My Tesla 的静态目录。"""
    resp = FileResponse((directory or config.STATIC_DIR) / file_name)
    resp.headers["Cache-Control"] = "no-cache"
    return resp
