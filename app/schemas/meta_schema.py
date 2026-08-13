from pydantic import BaseModel, ConfigDict


class CommonFieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    common_field_code: str
    canonical_key: str
    description_ko: str | None
    canonical_type: str
    value_role: str
    schema_status: str
    path_sensitive: bool
    enum_domain: list | None
    unit_family: str | None
    derived_from: list | None
    formula_id: str | None
    schema_version: str


class FieldMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_mapping_code: str
    canonical_key: str
    path_patterns: list[str]
    entity_scope: str
    canonical_type: str
    editable: bool
    value_role: str
    schema_status: str
    enum_domain: list | None
    reference_target_paths: list[str] | None
    schema_version: str
