from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StepTransitionIn(BaseModel):
    step_no: str
    condition: str = ""


class StepTransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    to_step_no: str
    condition: str
    interpreted_condition: str


class ProcessStepCreate(BaseModel):
    step_no: str
    process_id: str | None = None
    process_group_id: str | None = None
    process_name: str | None = None
    input_item_id: str | None = None
    output_item_id: str | None = None
    input_qty_per: float | None = None
    equipment_group: str | None = None
    std_speed: float | None = None
    # std_time_per is intentionally absent: FM_ROUTING_STD_TIME_PER.editable=false, always derived from std_speed.
    setup_time: float | None = None
    flow_type: str = "sequential"
    parallel_group_id: str | None = None
    join_condition: str | None = None
    production_type: str = "continuous"
    input_location_id: str | None = None
    output_location_id: str | None = None
    inbound_route_id: str | None = None
    process_specific: dict | None = None
    schema_status: str = "provisional"
    next_steps: list[StepTransitionIn] = []


class ProcessStepUpdate(BaseModel):
    process_id: str | None = None
    process_group_id: str | None = None
    process_name: str | None = None
    input_item_id: str | None = None
    output_item_id: str | None = None
    input_qty_per: float | None = None
    equipment_group: str | None = None
    std_speed: float | None = None
    setup_time: float | None = None
    flow_type: str | None = None
    parallel_group_id: str | None = None
    join_condition: str | None = None
    production_type: str | None = None
    input_location_id: str | None = None
    output_location_id: str | None = None
    inbound_route_id: str | None = None
    process_specific: dict | None = None
    schema_status: str | None = None
    next_steps: list[StepTransitionIn] | None = None


class ProcessStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_no: str
    process_id: str | None
    process_group_id: str | None
    process_name: str | None
    input_item_id: str | None
    output_item_id: str | None
    input_qty_per: float | None
    equipment_group: str | None
    std_speed: float | None
    std_time_per: float | None
    setup_time: float | None
    flow_type: str
    parallel_group_id: str | None
    join_condition: str | None
    production_type: str
    input_location_id: str | None
    output_location_id: str | None
    inbound_route_id: str | None
    process_specific: dict | None
    schema_status: str
    reference_status: dict | None
    next_steps: list[StepTransitionRead]


class ProcessRoutingCreate(BaseModel):
    version: str | None = None


class ProcessRoutingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    version: str
    status: str
    graph_completeness_status: str
    is_active: bool
    steps: list[ProcessStepRead]
    created_at: datetime
    updated_at: datetime


class ValidationIssue(BaseModel):
    rule_id: str
    path: str | None = None
    message: str


class ValidationReport(BaseModel):
    graph_completeness_status: str
    blocking_errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
