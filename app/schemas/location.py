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
