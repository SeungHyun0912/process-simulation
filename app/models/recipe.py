from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Recipe(TimestampMixin, Base):
    """A reusable product/process-specific parameter set (timing, yield, cable settings) that
    ProcessStep falls back to when it doesn't specify its own value directly (see compiler's
    _select_recipe matching by product_id/process_id/process_group_id)."""

    __tablename__ = "recipe"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("product.product_id"), nullable=True)
    process_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    process_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recipe_scope: Mapped[str] = mapped_column(String(32), default="equipment")
    setup_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # speed-mode/value overrides; not yet consumed by the compiler
    length_factor: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {input_per_output, loss_rate} -- fallback for ProcessStep.input_qty_per and yield loss
    cable_recipe: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # domain-specific cable process settings (e.g. extrusion temperature profile), mirrors Product.cable_design
