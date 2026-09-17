"""账号层 (门厅共享层的独立仓副本): 登录/注册/账号管理页面与接口。

账号体系在 My Home 里是全站共享层 (门厅 + 三应用); 独立部署时内嵌
进本仓, 接口路径不变 (/api/*), 会话 cookie 与组合部署同一配方 ——
两层部署可以互换。静态资源在本包自己的目录里。
"""
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"
