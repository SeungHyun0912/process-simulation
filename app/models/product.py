from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Product(TimestampMixin, Base):
    """Mirrors PROCESS_DEFINITION_INTENT.template.product_context (docs/schema/process-schema.json)."""

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_name: Mapped[str] = mapped_column(String(256))
    product_type: Mapped[str] = mapped_column(String(32), default="finished")
    unit: Mapped[str] = mapped_column(String(16), default="m")
    status: Mapped[str] = mapped_column(String(16), default="active")
    cable_design: Mapped[dict | None] = mapped_column(JSON, nullable=True)
