from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RuntimeProfileCreate(BaseModel):
    profile_name: str
    time_control: dict | None = None
    execution_mode: dict | None = None
    scenario_toggles: dict | None = None
    policy_refs: dict | None = None
    stochastic_defaults: dict | None = None
    output_control: dict | None = None


class RuntimeProfileUpdate(BaseModel):
    time_control: dict | None = None
    execution_mode: dict | None = None
    scenario_toggles: dict | None = None
    policy_refs: dict | None = None
    stochastic_defaults: dict | None = None
    output_control: dict | None = None


class RuntimeProfileRead(BaseModel):
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
