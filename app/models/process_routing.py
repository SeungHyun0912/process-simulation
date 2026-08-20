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
    product_links: Mapped[list["RoutingProductLink"]] = relationship(
        back_populates="routing", cascade="all, delete-orphan"
    )

    @property
    def linked_product_ids(self) -> list[str]:
        """Every product (primary + forked) that consumes some subgraph of this routing."""
        return [link.product_id for link in self.product_links]


class RoutingProductLink(TimestampMixin, Base):
    """N:M link letting several products share one ProcessRouting network, each consuming a
    different entry/terminal subgraph of it (docs/planning/07-schema-gap-review.md section 6).

    The primary link (created automatically alongside the routing) always represents the
    routing's full graph: its entry/terminal steps are computed live from the graph's actual
    topology (see app.services.routing_validation._live_entry_terminal_steps) rather than
    stored here, since they can't be known yet at routing-creation time (zero steps exist).
    Only non-primary (forked) links store explicit entry_step_nos/terminal_step_nos.
    """

    __tablename__ = "routing_product_link"
    __table_args__ = (UniqueConstraint("routing_id", "product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    routing_id: Mapped[int] = mapped_column(
        ForeignKey("process_routing.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("product.product_id"), index=True)
    entry_step_nos: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    terminal_step_nos: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    routing: Mapped["ProcessRouting"] = relationship(back_populates="product_links")


class ProcessStep(TimestampMixin, Base):
    """One node in a ProcessRouting graph: a single processing operation with its timing,
    equipment, location, and flow-control settings."""

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
    process_specific: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # free-form fields not yet promoted to the common schema
    schema_status: Mapped[str] = mapped_column(String(32), default="provisional")  # "provisional" until confirmed/reviewed data
    reference_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # per-field validation/reference-resolution results (e.g. dangling FK checks)

    routing: Mapped["ProcessRouting"] = relationship(back_populates="steps")
    next_steps: Mapped[list["ProcessStepTransition"]] = relationship(
        back_populates="from_step", cascade="all, delete-orphan"
    )
    outputs: Mapped[list["ProcessStepOutput"]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )


class ProcessStepOutput(Base):
    """A named co-product a step can yield, and its ratio relative to qty processed.

    A step with a single output still gets exactly one row here (output_ratio=1.0) --
    this replaces the old scalar ProcessStep.output_item_id so no special-casing is
    needed for single- vs. multi-output steps (docs/planning/07-schema-gap-review.md).
    """

    __tablename__ = "process_step_output"
    __table_args__ = (UniqueConstraint("step_id", "output_item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("process_step.id", ondelete="CASCADE"), index=True)
    output_item_id: Mapped[str] = mapped_column(String(64))
    output_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)

    step: Mapped["ProcessStep"] = relationship(back_populates="outputs")


class ProcessStepTransition(Base):
    """A directed edge in a ProcessRouting graph: from_step -> to_step_no, optionally gated by a
    condition and carrying a specific output item forward (supports branching/parallel flows)."""

    __tablename__ = "process_step_transition"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_step_id: Mapped[int] = mapped_column(
        ForeignKey("process_step.id", ondelete="CASCADE"), index=True
    )
    to_step_no: Mapped[str] = mapped_column(String(32))
    condition: Mapped[str] = mapped_column(String(256), default="")  # raw user-authored condition expression
    interpreted_condition: Mapped[str] = mapped_column(String(32), default="always_true")  # compiler's normalized reading of `condition`
    output_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consumption_ratio: Mapped[float] = mapped_column(Float, default=1.0)

    from_step: Mapped["ProcessStep"] = relationship(back_populates="next_steps")
