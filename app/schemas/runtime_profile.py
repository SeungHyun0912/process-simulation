from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RuntimeProfileCreate(BaseModel):
    # request body defining a reusable named simulation runtime configuration;
    # each dict field below is a free-form config block consumed by the SimPy runtime engine
    profile_name: str
    time_control: dict | None = None  # sim clock settings (e.g. duration, warm-up period)
    execution_mode: dict | None = None  # run-mode toggles (e.g. deterministic vs stochastic)
    scenario_toggles: dict | None = None  # feature/scenario flags applied for this profile
    policy_refs: dict | None = None  # references to dispatch/allocation policies to use
    stochastic_defaults: dict | None = None  # default distributions for randomized parameters
    output_control: dict | None = None  # controls which outputs/granularity are recorded


class RuntimeProfileUpdate(BaseModel):
    # partial update -- every field optional, only fields explicitly set are applied
    time_control: dict | None = None
    execution_mode: dict | None = None
    scenario_toggles: dict | None = None
    policy_refs: dict | None = None
    stochastic_defaults: dict | None = None
    output_control: dict | None = None


class RuntimeProfileRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_name: str
    time_control: dict
    execution_mode: dict
    scenario_toggles: dict
    policy_refs: dict
    stochastic_defaults: dict
    output_control: dict
    created_at: datetime
    updated_at: datetime
