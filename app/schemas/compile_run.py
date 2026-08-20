from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompileRunCreate(BaseModel):
    # request body to trigger compilation of a product's routing at a given version
    product_id: str
    version: str
    runtime_profile_name: str | None = None


class CompileRunRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    id: int
    routing_id: int
    routing_version: str
    bound_product_ids: list[str]  # products this compiled snapshot is bound to
    runtime_profile_id: int | None
    status: str
    compiled_graph_object: dict | None  # compiler output graph, null until compilation succeeds
    validation_report: dict  # blocking errors / warnings produced during compilation
    created_at: datetime
