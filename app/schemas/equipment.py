from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EquipmentGroupCreate(BaseModel):
    # request body for creating an equipment group
    group_id: str
    group_name: str | None = None
    capacity: int | None = None


class EquipmentGroupUpdate(BaseModel):
    # partial update -- every field optional, only fields explicitly set are applied
    group_name: str | None = None
    capacity: int | None = None


class EquipmentGroupRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: str
    group_name: str | None
    capacity: int | None
    default_capacity_source: str  # e.g. "explicit" vs "derived" -- where `capacity` value came from
    created_at: datetime
    updated_at: datetime


class EquipmentCreate(BaseModel):
    # request body for creating a single equipment unit within a group
    equipment_id: str
    group_id: str
    capacity: int | None = None
    attributes: dict | None = None  # free-form equipment attributes (JSON)


class EquipmentUpdate(BaseModel):
    # partial update -- every field optional, only fields explicitly set are applied
    group_id: str | None = None
    capacity: int | None = None
    attributes: dict | None = None


class EquipmentRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: str
    group_id: str
    capacity: int | None
    attributes: dict | None
    created_at: datetime
    updated_at: datetime
