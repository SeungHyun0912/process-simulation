from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EquipmentGroupCreate(BaseModel):
    group_id: str
    group_name: str | None = None
    capacity: int | None = None


class EquipmentGroupUpdate(BaseModel):
    group_name: str | None = None
    capacity: int | None = None


class EquipmentGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: str
    group_name: str | None
    capacity: int | None
    default_capacity_source: str
    created_at: datetime
    updated_at: datetime


class EquipmentCreate(BaseModel):
    equipment_id: str
    group_id: str
    capacity: int | None = None
    attributes: dict | None = None


class EquipmentUpdate(BaseModel):
    group_id: str | None = None
    capacity: int | None = None
    attributes: dict | None = None


class EquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: str
    group_id: str
    capacity: int | None
    attributes: dict | None
    created_at: datetime
    updated_at: datetime
