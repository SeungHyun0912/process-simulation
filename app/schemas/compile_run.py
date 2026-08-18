from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompileRunCreate(BaseModel):
    product_id: str
    version: str
    runtime_profile_name: str | None = None


class CompileRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    routing_id: int
    routing_version: str
    product_id: str
    runtime_profile_id: int | None
    status: str
    compiled_graph_object: dict | None
    validation_report: dict
    created_at: datetime
