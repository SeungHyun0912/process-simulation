from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductCreate(BaseModel):
    # request body for creating a product
    product_id: str
    product_name: str
    product_type: str = "finished"
    unit: str = "m"
    status: str = "active"
    cable_design: dict | None = None  # free-form cable design spec (JSON)


class ProductUpdate(BaseModel):
    # partial update -- every field optional, only fields explicitly set are applied
    product_name: str | None = None
    product_type: str | None = None
    unit: str | None = None
    status: str | None = None
    cable_design: dict | None = None


class ProductRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: str
    product_name: str
    product_type: str
    unit: str
    status: str
    cable_design: dict | None
    created_at: datetime
    updated_at: datetime
