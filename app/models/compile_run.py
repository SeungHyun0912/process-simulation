from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CompileRun(TimestampMixin, Base):
    """One compile attempt: ProcessRouting (+ RuntimeProfile) -> compiled_graph_object.

    Persisted even when status="blocked" so a failed compile attempt is auditable
    (see docs/planning/04-rdb-design.md section 2-5). Compare to /publish, which raises
    on failure without leaving a row -- a compile attempt is expected to fail
    sometimes (e.g. before all steps have resolved timing) and that's worth keeping.
    """

    __tablename__ = "compile_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    routing_id: Mapped[int] = mapped_column(ForeignKey("process_routing.id"), index=True)
    routing_version: Mapped[str] = mapped_column(String(32))
    bound_product_ids: Mapped[list[str]] = mapped_column(JSON)  # snapshot of routing.product_links at compile time
    runtime_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("runtime_profile.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16))
    compiled_graph_object: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # SimPy-ready graph; null unless compile succeeded
    validation_report: Mapped[dict] = mapped_column(JSON)  # structured errors/warnings surfaced regardless of pass/fail
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
