from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ProcessRouting(TimestampMixin, Base):
    """One versioned process graph for a product (docs/planning/02-process-management.md)."""

    __tablename__ = "process_routing"
    __table_args__ = (UniqueConstraint("product_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("product.product_id"), index=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    graph_completeness_status: Mapped[str] = mapped_column(String(32), default="incomplete")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    steps: Mapped[list["ProcessStep"]] = relationship(
        back_populates="routing",
        cascade="all, delete-orphan",
        order_by="ProcessStep.step_no",
    )


class ProcessStep(TimestampMixin, Base):
    __tablename__ = "process_step"
    __table_args__ = (UniqueConstraint("routing_id", "step_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    routing_id: Mapped[int] = mapped_column(
        ForeignKey("process_routing.id", ondelete="CASCADE"), index=True
    )
    step_no: Mapped[str] = mapped_column(String(32))
    process_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    process_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    process_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    input_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_qty_per: Mapped[float | None] = mapped_column(Float, nullable=True)
    equipment_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    std_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_time_per: Mapped[float | None] = mapped_column(Float, nullable=True)  # derived, see FM_ROUTING_STD_TIME_PER
    setup_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    flow_type: Mapped[str] = mapped_column(String(32), default="sequential")
    parallel_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    join_condition: Mapped[str | None] = mapped_column(String(256), nullable=True)
    production_type: Mapped[str] = mapped_column(String(32), default="continuous")
    input_location_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_location_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inbound_route_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    batch_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    batch_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    process_specific: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_status: Mapped[str] = mapped_column(String(32), default="provisional")
    reference_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    routing: Mapped["ProcessRouting"] = relationship(back_populates="steps")
    next_steps: Mapped[list["ProcessStepTransition"]] = relationship(
        back_populates="from_step", cascade="all, delete-orphan"
    )


class ProcessStepTransition(Base):
    __tablename__ = "process_step_transition"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_step_id: Mapped[int] = mapped_column(
        ForeignKey("process_step.id", ondelete="CASCADE"), index=True
    )
    to_step_no: Mapped[str] = mapped_column(String(32))
    condition: Mapped[str] = mapped_column(String(256), default="")
    interpreted_condition: Mapped[str] = mapped_column(String(32), default="always_true")

    from_step: Mapped["ProcessStep"] = relationship(back_populates="next_steps")
