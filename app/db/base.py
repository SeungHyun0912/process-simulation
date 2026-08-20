from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base every ORM model inherits from; also what Alembic's
    autogenerate diffs metadata against."""


class TimestampMixin:
    """Mixin adding created_at/updated_at columns set by the DB itself (server_default/
    onupdate), not the application, so they stay correct regardless of which code path writes."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
