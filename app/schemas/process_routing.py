from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StepOutputIn(BaseModel):
    # nested input shape for one output produced by a step, used inside ProcessStepCreate/Update
    output_item_id: str
    output_ratio: float = 1.0
    unit: str | None = None


class StepOutputRead(BaseModel):
    # response shape for one step output
    model_config = ConfigDict(from_attributes=True)

    output_item_id: str
    output_ratio: float
    unit: str | None


class StepTransitionIn(BaseModel):
    # nested input shape for an outgoing transition (edge) to a next step, used inside ProcessStepCreate/Update
    step_no: str
    condition: str = ""
    output_item_id: str | None = None
    consumption_ratio: float = 1.0


class StepTransitionRead(BaseModel):
    # response shape for a step transition
    model_config = ConfigDict(from_attributes=True)

    to_step_no: str
    condition: str
    interpreted_condition: str  # `condition` normalized/compiled into the form the runtime engine evaluates
    output_item_id: str | None
    consumption_ratio: float


class ProcessStepCreate(BaseModel):
    # request body for creating a process step within a routing
    step_no: str
    process_id: str | None = None
    process_group_id: str | None = None
    process_name: str | None = None
    input_item_id: str | None = None
    input_qty_per: float | None = None
    equipment_group: str | None = None
    std_speed: float | None = None
    # std_time_per is intentionally absent: FM_ROUTING_STD_TIME_PER.editable=false, always derived from std_speed.
    setup_time: float | None = None
    flow_type: str = "sequential"  # "sequential" or "parallel"; parallel steps use parallel_group_id/join_condition
    parallel_group_id: str | None = None
    join_condition: str | None = None
    production_type: str = "continuous"  # "continuous" or "batch"; batch steps use batch_size/batch_unit
    input_location_id: str | None = None
    output_location_id: str | None = None
    inbound_route_id: str | None = None
    batch_size: float | None = None
    batch_unit: str | None = None
    process_specific: dict | None = None  # free-form parameters specific to this process type (JSON)
    schema_status: str = "provisional"  # marks the step as not yet reviewed/confirmed
    outputs: list[StepOutputIn] = []
    next_steps: list[StepTransitionIn] = []


class ProcessStepUpdate(BaseModel):
    # partial update -- every field optional, only fields explicitly set are applied
    process_id: str | None = None
    process_group_id: str | None = None
    process_name: str | None = None
    input_item_id: str | None = None
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
    batch_size: float | None = None
    batch_unit: str | None = None
    process_specific: dict | None = None
    schema_status: str | None = None
    outputs: list[StepOutputIn] | None = None
    next_steps: list[StepTransitionIn] | None = None


class ProcessStepRead(BaseModel):
    # response shape for a process step, including its computed/derived fields
    model_config = ConfigDict(from_attributes=True)

    step_no: str
    process_id: str | None
    process_group_id: str | None
    process_name: str | None
    input_item_id: str | None
    input_qty_per: float | None
    equipment_group: str | None
    std_speed: float | None
    std_time_per: float | None  # server-derived from std_speed (see ProcessStepCreate note)
    setup_time: float | None
    flow_type: str
    parallel_group_id: str | None
    join_condition: str | None
    production_type: str
    input_location_id: str | None
    output_location_id: str | None
    inbound_route_id: str | None
    batch_size: float | None
    batch_unit: str | None
    process_specific: dict | None
    schema_status: str
    reference_status: dict | None  # per-field reference/validation resolution status (e.g. broken links)
    outputs: list[StepOutputRead]
    next_steps: list[StepTransitionRead]


class ProcessRoutingCreate(BaseModel):
    # request body to create a new routing version for a product
    version: str | None = None


class ProcessRoutingRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    version: str
    status: str
    graph_completeness_status: str  # result of structural graph validation (e.g. complete/incomplete)
    is_active: bool
    steps: list[ProcessStepRead]
    linked_product_ids: list[str]  # other products linked to this routing version
    created_at: datetime
    updated_at: datetime


class RoutingLinkCreate(BaseModel):
    # request body linking a product to specific entry/terminal steps of a routing
    product_id: str
    entry_step_nos: list[str]
    terminal_step_nos: list[str]


class RoutingLinkRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    entry_step_nos: list[str] | None
    terminal_step_nos: list[str] | None
    is_primary: bool  # whether this is the product's primary routing link


class ValidationIssue(BaseModel):
    # a single validation finding surfaced during routing compilation/validation
    rule_id: str
    path: str | None = None
    message: str


class ValidationReport(BaseModel):
    # aggregated validation results for a routing graph
    graph_completeness_status: str
    blocking_errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
