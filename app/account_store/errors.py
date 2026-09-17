"""账号域的异常: 名称/密码/邀请三类, 路由层各转对应的 4xx。"""


class InvalidNameError(ValueError):
    """名称不合法 / 已被占用 (路由转 400)。"""


class PasswordError(ValueError):
    """密码不合法 / 旧密码不对 (路由转 400/403)。"""


class InvitationError(ValueError):
    """邀请不可用: 不存在 / 已用 / 过期 / 已撤销 (路由转 400)。"""
