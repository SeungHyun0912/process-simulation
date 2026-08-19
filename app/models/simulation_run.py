from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SimulationRun(TimestampMixin, Base):
    __tablename__ = "simulation_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    compile_run_id: Mapped[int] = mapped_column(ForeignKey("compile_run.id"), index=True)
    runtime_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("runtime_profile.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    material_inbound_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class SimulationResultSummary(TimestampMixin, Base):
    __tablename__ = "simulation_result_summary"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_run.id"), unique=True, index=True
    )
    throughput_total: Mapped[float] = mapped_column(Float)
    throughput_per_day: Mapped[float] = mapped_column(Float)
    avg_wip: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_lead_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    resource_utilization: Mapped[dict] = mapped_column(JSON)
    bottleneck_step_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_qty_by_step: Mapped[dict] = mapped_column(JSON, default=dict)


class SimulationEventLog(Base):
    __tablename__ = "simulation_event_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[int] = mapped_column(ForeignKey("simulation_run.id"), index=True)
    sim_time: Mapped[float] = mapped_column(Float)
    event_type: Mapped[str] = mapped_column(String(32))
    step_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)


class SimulationWipSnapshot(Base):
    __tablename__ = "simulation_wip_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[int] = mapped_column(ForeignKey("simulation_run.id"), index=True)
    sim_time: Mapped[float] = mapped_column(Float)
    total_wip: Mapped[float] = mapped_column(Float)
    by_step: Mapped[dict] = mapped_column(JSON)
