from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Default JSON blueprints for RuntimeProfile's columns below. Each is copied via `dict(...)`
# in a `default=lambda: ...` factory (not passed as a bare dict) so SQLAlchemy doesn't share
# one mutable dict instance across every row that relies on the default.
DEFAULT_TIME_CONTROL = {
    "time_unit": "day",
    "base_time_granularity": "minute",
    "start_date": None,
    "duration_days": 30,
    "warmup_period": 0,
    "replication_count": 1,
    "random_seed": 42,
}
DEFAULT_EXECUTION_MODE = {"speed_mode": "fixed", "deterministic_mode": True, "logging_level": "standard"}
DEFAULT_SCENARIO_TOGGLES = {
    "enable_breakdown": False,
    "enable_preventive_maintenance": False,
    "enable_defect_generation": False,
    "enable_rework_flow": False,
    "enable_shift_calendar": False,
}
DEFAULT_POLICY_REFS = {
    "processing_time_policy_ref": "speed_to_time_v1",
    "queue_policy_ref": "fifo_default_v1",
    "resource_request_policy_ref": "single_primary_resource_v1",
    "batching_policy_ref": "production_type_based_v1",
    "calendar_policy_ref": "disabled_24x7_v1",
}
DEFAULT_STOCHASTIC_DEFAULTS = {
    "distribution_mode": "deterministic",
    "default_distribution_family": None,
    "use_common_random_numbers": False,
}
DEFAULT_OUTPUT_CONTROL = {
    "collect_event_log": True,
    "collect_resource_log": True,
    "collect_wip_snapshot": True,
    "snapshot_interval": 60,
    "snapshot_interval_unit": "minute",
}


class RuntimeProfile(TimestampMixin, Base):
    """Mirrors SIMPY_RUNTIME_META (docs/schema/process-simpy-map.json)."""

    __tablename__ = "runtime_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    time_control: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_TIME_CONTROL))
    execution_mode: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_EXECUTION_MODE))
    scenario_toggles: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_SCENARIO_TOGGLES))
    policy_refs: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_POLICY_REFS))
    stochastic_defaults: Mapped[dict] = mapped_column(
        JSON, default=lambda: dict(DEFAULT_STOCHASTIC_DEFAULTS)
    )
    output_control: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_OUTPUT_CONTROL))
