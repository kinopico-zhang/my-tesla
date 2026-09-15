"""更新日志 API。"""
from fastapi import APIRouter

from ... import changelog
from ...schemas import ChangelogVersion


changelogapi = APIRouter(prefix="/tesla/changelog/api")


@changelogapi.get("/entries")
def get_changelog_entries() -> list[ChangelogVersion]:
    """更新日志版本 (新→老), 每版是一批改动的合并。"""
    return changelog.entries()
