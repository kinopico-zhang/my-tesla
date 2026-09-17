"""表映射基类: TeslaMate 库 Base 与自有库 OwnBase。

生产表由 TeslaMate 迁移维护, 应用绝不建表/改表; 建表只发生在测试的
SQLite 里 (Base.metadata.create_all)。数值列统一映射 Float: 库内
numeric 读出是 Decimal, 统一转 float 与旧接口输出一致。

OwnBase 是 My Tesla 自有表的基类 (data/mytesla.db, 与 TeslaMate 库
完全隔离), 由应用自己 create_all 建表。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """TeslaMate 表映射基类。"""


class OwnBase(DeclarativeBase):
    """My Tesla 自有表基类 (data/mytesla.db, 应用自己建表)。"""
