from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    original_filename: str | None
    status: str
    error_message: str | None
    created_at: datetime


class UploadJobDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_key: str
    source_label: str | None
    records: list
    status: str


class UploadFieldMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_label: str | None
    raw_header_text: str
    mapped_canonical_key: str | None
    confidence: float | None
    decided_by: str


class UploadDraftUpdate(BaseModel):
    records: list[dict]


class PromoteResult(BaseModel):
    created: list[str]
    skipped: list[dict]


class JsonPayloadUpload(BaseModel):
    source_type: str
    payload: list[dict]
    table_name: str = "table1"
