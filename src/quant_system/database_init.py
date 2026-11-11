from __future__ import annotations

from .database import Base, create_engine_from_config


def initialize_database(url: str | None = None) -> None:
    """创建当前版本模型对应的数据库表；生产环境增量变更建议使用 Alembic。"""
    engine = create_engine_from_config(url)
    Base.metadata.create_all(engine)
