"""设置域接口模型: TeslaMate/高德连接现值与保存, 驾驶员条目。"""
from pydantic import BaseModel, Field


class TeslaMateSettings(BaseModel):
    """TeslaMate 连接现值 (密码不回显, 只报是否在用)。"""

    host: str
    port: str
    user: str
    name: str
    password_set: bool


class AmapSettings(BaseModel):
    """高德 Key 现值 (打码回显 + 安全码是否在用) + 地图样式现值。"""

    key_masked: str
    security_code_set: bool
    style: str


class SettingsState(BaseModel):
    """设置页状态: 各字段现值 (回落 env 后的效果)。"""

    tmdb: TeslaMateSettings
    amap: AmapSettings


class SettingsUpdate(BaseModel):
    """保存设置: 字段留空 = 保持现值 (密码/Key 不回显, 前端重填才算改)。"""

    tmdb_host: str = ""
    tmdb_port: str = ""
    tmdb_user: str = ""
    tmdb_password: str = ""
    tmdb_name: str = ""
    amap_key: str = ""
    amap_security_code: str = ""
    amap_style: str = ""   # 官方样式名或 amap://styles/<自定义ID> (空 = 保持现值)


class DriverInfo(BaseModel):
    """驾驶员条目。"""

    id: int
    name: str
    is_default: bool


class DriverIn(BaseModel):
    """添加驾驶员。"""

    name: str = Field(min_length=1, max_length=30)


class DriverUpdate(BaseModel):
    """改驾驶员: 改名 / 设默认 (设默认会清掉其他人的默认)。"""

    name: str | None = Field(None, min_length=1, max_length=30)
    is_default: bool | None = None
