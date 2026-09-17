"""密码与名称的校验 (scrypt 哈希): 无数据库依赖, 纯函数。"""
import hashlib
import hmac
import re
import secrets

from .errors import InvalidNameError, PasswordError

# scrypt 参数: n=2^14 / r=8 / p=1 一次哈希 ~16MB 内存 + 几十毫秒,
# NAS 上可承受, 也足够拖慢离线爆破
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2 ** 14, 8, 1, 32

# 名称: 2~20 个字符, 不含空白/控制符 (可中文/字母/数字/常用符号)
_NAME_RE = re.compile(r"^\S(.*\S)?$", re.S)


def hash_password(password: str) -> str:
    """明文 → "scrypt$<salt>$<hash>"。"""
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(),
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                            dklen=_DKLEN).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """验密码 (常数时间比对; 坏格式一律 False)。"""
    try:
        algo, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        expect = hashlib.scrypt(password.encode(), salt=salt.encode(),
                                n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                                dklen=_DKLEN).hex()
        return hmac.compare_digest(expect, digest)
    except (ValueError, AttributeError):
        return False


def _check_name(name: str) -> str:
    """名称规范: 去空白后 2~20 字符且不含内部空白。"""
    name = (name or "").strip()
    if not 2 <= len(name) <= 20 or not _NAME_RE.match(name) or any(c.isspace() for c in name):
        raise InvalidNameError("名称需 2~20 个字符, 且不含空格")
    return name


def _check_password(password: str) -> str:
    if not 6 <= len(password or "") <= 64:
        raise PasswordError("密码需 6~64 个字符")
    return password
