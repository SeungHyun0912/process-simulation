from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LocationCreate(BaseModel):
    location_id: str
    location_type: str
    location_name: str | None = None
    storage_capacity: float | None = None


class LocationUpdate(BaseModel):
    location_type: str | None = None
    location_name: str | None = None
    storage_capacity: float | None = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location_id: str
    location_type: str
    location_name: str | None
    storage_capacity: float | None
    created_at: datetime
    updated_at: datetime


class TransportRouteCreate(BaseModel):
    route_id: str
    from_location_id: str
    to_location_id: str
    transport_mode: str | None = None
    transport_distance: float | None = None
    transport_speed: float | None = None
    transport_time: float | None = None
    transport_capacity_per_trip: float | None = None


class TransportRouteUpdate(BaseModel):
    transport_mode: str | None = None
    transport_distance: float | None = None
    transport_speed: float | None = None
    transport_time: float | None = None
    transport_capacity_per_trip: float | None = None


class TransportRouteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: str
    from_location_id: str
    to_location_id: str
    transport_mode: str | None
    transport_distance: float | None
    transport_speed: float | None
    transport_time: float | None
    transport_capacity_per_trip: float | None
    created_at: datetime
    updated_at: datetime


class MaterialInboundPlanCreate(BaseModel):
    plan_id: str
    item_id: str
    location_id: str
    inbound_qty: float
    inbound_unit: str | None = None
    interval_value: float = 1
    interval_unit: str = "day"
    schema_status: str = "provisional"


class MaterialInboundPlanUpdate(BaseModel):
    item_id: str | None = None
    location_id: str | None = None
    inbound_qty: float | None = None
    inbound_unit: str | None = None
    interval_value: float | None = None
    interval_unit: str | None = None
    schema_status: str | None = None


class MaterialInboundPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: str
    item_id: str
    location_id: str
    inbound_qty: float
    inbound_unit: str | None
    interval_value: float
    interval_unit: str
    schema_status: str
    created_at: datetime
    updated_at: datetime
