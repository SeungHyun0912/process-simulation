from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadJobRead(BaseModel):
    # response describing the status of an ingestion upload job (Excel/CSV/JSON)
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    original_filename: str | None
    status: str
    error_message: str | None
    created_at: datetime


class UploadJobDraftRead(BaseModel):
    # response with one entity's parsed draft rows, pending review before promotion
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_key: str
    source_label: str | None
    records: list  # raw parsed rows (dicts) awaiting field-mapping confirmation
    status: str


class UploadFieldMappingRead(BaseModel):
    # response describing how a raw source column was mapped to a canonical field
    model_config = ConfigDict(from_attributes=True)

    source_label: str | None
    raw_header_text: str
    mapped_canonical_key: str | None
    confidence: float | None  # mapping confidence score (e.g. LLM-suggested); None if user/rule-decided
    decided_by: str  # who/what produced the mapping, e.g. "llm" / "rule" / "user"


class UploadDraftUpdate(BaseModel):
    # request body to correct/edit draft records before promotion into master data
    records: list[dict]


class PromoteResult(BaseModel):
    # response summarizing the outcome of promoting draft records into master data
    created: list[str]
    skipped: list[dict]  # entries skipped (e.g. duplicates/conflicts), with reason


class JsonPayloadUpload(BaseModel):
    # request body to submit a raw JSON payload directly for ingestion
    source_type: str
    payload: list[dict]
    table_name: str = "table1"  # logical table name grouping the payload rows
