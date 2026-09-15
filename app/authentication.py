"""会话鉴权: HMAC 签名 cookie 的签发与校验 + 登录限速。

多用户版: cookie 值 "<过期时间戳>.<用户uuid>.<HMAC>", 会话只认 uuid
(改名不掉线); 密钥持久化在 .session_secret (重启不失效)。单用户时代的
旧 cookie 是两段式, 校验通过后按管理员会话处理 (升级不强制重登 Tesla
侧; 旧 cookie 的 path 限定 /tesla, 进记账还是要重登一次)。
"""
import hashlib
import hmac
import secrets
import time

from . import config


def _compute_secret(raw: bytes) -> bytes:
    """会话签名密钥 = 原始密钥 (多用户下账号密码各自可改, 不掺进密钥)。"""
    return hashlib.sha256(raw).digest()


def _compute_legacy_secret(raw: bytes) -> bytes:
    """单用户时代的签名密钥 (掺了账密): 只用于认旧 cookie, 不再签发。"""
    return hashlib.sha256(
        raw + b"|" + config.AUTH_USER.encode() + b"|" + config.AUTH_PASS.encode()
    ).digest()


class _SecretHolder:
    """签名密钥持有者 (避免 global 语句; 登出轮换、测试替换都改 value)。"""

    def __init__(self, value: bytes) -> None:
        self.value = value




def _load_secret() -> bytes:
    """读取/生成会话签名密钥 (>=32 字节, 权限 0600)。"""
    try:
        data = config.SECRET_FILE.read_bytes().strip()
        if len(data) >= 32:
            return data
    except OSError:
        pass
    data = secrets.token_hex(32).encode()
    config.SECRET_FILE.write_bytes(data)
    try:
        config.SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return data


# 会话签名密钥 + 旧版密钥 (测试里被替换成固定值)
_raw_secret = _load_secret()
_secret = _SecretHolder(_compute_secret(_raw_secret))
_legacy_secret = _SecretHolder(_compute_legacy_secret(_raw_secret))

# 旧版 (单用户时代) cookie 认出的"虚拟身份": 解析到管理员账号
LEGACY_ADMIN = "legacy-admin"

# 单 IP 失败记录: ip -> (连续失败次数, 锁定截止时间戳, 0=未锁)
_login_fails: dict[str, tuple[int, float]] = {}


def make_token(user_uuid: str) -> str:
    """签发会话 cookie 值: "<过期时间戳>.<用户uuid>.<HMAC 签名>"。"""
    exp = str(int(time.time()) + config.SESSION_DAYS * 86400)
    payload = f"{exp}.{user_uuid}"
    sig = hmac.new(_secret.value, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def check_token(token: str) -> str | None:
    """校验 cookie → 用户 uuid (旧版 cookie → LEGACY_ADMIN; 无效 → None)。"""
    try:
        parts = token.split(".")
        if len(parts) == 3:                      # 新版: exp.uuid.sig
            exp, user_uuid, sig = parts
            expect = hmac.new(_secret.value,
                              f"{exp}.{user_uuid}".encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(expect, sig) and int(exp) > time.time():
                return user_uuid
        elif len(parts) == 2:                    # 旧版: exp.sig (单用户=管理员)
            exp, sig = parts
            expect = hmac.new(_legacy_secret.value,
                              exp.encode(), hashlib.sha256).hexdigest()
            if hmac.compare_digest(expect, sig) and int(exp) > time.time():
                return LEGACY_ADMIN
    except (ValueError, TypeError):
        pass
    return None


def ip_locked(ip: str) -> bool:
    """该 IP 是否处于登录锁定期。"""
    rec = _login_fails.get(ip)
    return bool(rec and rec[1] > time.time())


def record_fail(ip: str) -> None:
    """记一次登录失败; 连续失败达到上限则锁定该 IP 一段时间。"""
    if len(_login_fails) > 10000:  # 防扫描器撑爆内存
        _login_fails.clear()
    fails, _ = _login_fails.get(ip, (0, 0))
    if fails + 1 >= config.LOGIN_MAX_FAILS:
        _login_fails[ip] = (0, time.time() + config.LOGIN_LOCK_S)
    else:
        _login_fails[ip] = (fails + 1, 0)


def clear_fails(ip: str) -> None:
    """登录成功后清除失败记录。"""
    _login_fails.pop(ip, None)
