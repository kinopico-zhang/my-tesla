"""环境变量配置 (见 .env.example), 集中读取避免散落各处。"""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "tesla" / "static"
# 账号体系页面 (登录/注册/账号管理) + 全站小件 (menu-user / changelog-page)
# 的静态目录, 挂在 /static
SHARED_STATIC_DIR = APP_DIR / "static"

# 时间: 库内为 UTC 裸时间戳, 对外输出本地时间
LOCAL_TZ = ZoneInfo(os.environ.get("TZ_NAME", "Asia/Shanghai"))
CUR_SYMBOL = os.environ.get("CUR_SYMBOL", "¥")

# 鉴权 (env 可覆盖)
AUTH_USER = os.environ.get("AUTH_USER", "admin")
AUTH_PASS = os.environ.get("AUTH_PASS", "daozi1994")
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "90"))
SECRET_FILE = PROJECT_DIR / ".session_secret"

# 登录限速: 单 IP 连续失败 5 次锁定 60 秒
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_S = 60

# 自有库 (SQLite): 轨迹断档补路等 My Tesla 自己产生、不愿写进
# TeslaMate 原库的数据 (原库始终只读不动)
OWN_DB_URL = (os.environ.get("MYTESLA_DB")
              or f"sqlite:///{PROJECT_DIR / 'data' / 'mytesla.db'}")

# 账号库 (SQLite, 与业务库分开的独立文件): 用户 + 注册邀请
USERS_DB_URL = (os.environ.get("MYTESLA_USERS_DB")
                or f"sqlite:///{PROJECT_DIR / 'data' / 'users.db'}")
