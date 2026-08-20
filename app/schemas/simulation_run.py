from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SimulationRunCreate(BaseModel):
    # request body to launch a simulation run against an existing compiled graph
    compile_run_id: int
    runtime_profile_name: str | None = None
    material_inbound_overrides: dict[str, float] | None = None  # per-item_id inbound qty override, this run only


class SimulationRunRead(BaseModel):
    # response describing a simulation run's lifecycle/status
    model_config = ConfigDict(from_attributes=True)

    id: int
    compile_run_id: int
    runtime_profile_id: int | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class SimulationResultSummaryRead(BaseModel):
    # aggregated KPI summary for a completed simulation run
    model_config = ConfigDict(from_attributes=True)

    throughput_total: float
    throughput_per_day: float
    avg_wip: float | None
    avg_lead_time: float | None
    resource_utilization: dict  # utilization ratio keyed by resource/equipment group
    bottleneck_step_no: str | None  # step identified as the throughput bottleneck, if any
    exit_qty_by_step: dict  # completed quantity keyed by step_no


class SimulationEventLogRead(BaseModel):
    # single discrete event emitted during the simulation run
    model_config = ConfigDict(from_attributes=True)

    sim_time: float
    event_type: str
    step_no: str | None
    resource_key: str | None
    item_id: str | None
    qty: float | None


class SimulationWipSnapshotRead(BaseModel):
    # point-in-time snapshot of work-in-progress levels during the run
    model_config = ConfigDict(from_attributes=True)

    sim_time: float
    total_wip: float
    by_step: dict  # WIP quantity keyed by step_no
