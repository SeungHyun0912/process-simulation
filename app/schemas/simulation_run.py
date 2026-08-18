from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SimulationRunCreate(BaseModel):
    compile_run_id: int
    runtime_profile_name: str | None = None
    material_inbound_overrides: dict[str, float] | None = None


class SimulationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    compile_run_id: int
    runtime_profile_id: int | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class SimulationResultSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    throughput_total: float
    throughput_per_day: float
    avg_wip: float | None
    avg_lead_time: float | None
    resource_utilization: dict
    bottleneck_step_no: str | None


class SimulationEventLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sim_time: float
    event_type: str
    step_no: str | None
    resource_key: str | None
    item_id: str | None
    qty: float | None


class SimulationWipSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sim_time: float
    total_wip: float
    by_step: dict
