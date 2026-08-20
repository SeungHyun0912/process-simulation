from pydantic import BaseModel, ConfigDict


class CommonFieldRead(BaseModel):
    # response describing one canonical field definition from the meta-schema dictionary (read-only)
    model_config = ConfigDict(from_attributes=True)

    common_field_code: str
    canonical_key: str
    description_ko: str | None
    canonical_type: str
    value_role: str
    schema_status: str
    path_sensitive: bool  # whether this field's meaning/handling depends on the path it appears at
    enum_domain: list | None  # allowed values, if this field is enum-constrained
    unit_family: str | None
    derived_from: list | None  # source canonical_keys this field is computed from, if derived
    formula_id: str | None  # reference to the formula used when derived_from is set
    schema_version: str


class FieldMappingRead(BaseModel):
    # response describing how a raw source path pattern maps to a canonical field
    model_config = ConfigDict(from_attributes=True)

    field_mapping_code: str
    canonical_key: str
    path_patterns: list[str]  # source path/header patterns recognized as this canonical field
    entity_scope: str
    canonical_type: str
    editable: bool  # whether users may edit this field, or it's always server-derived
    value_role: str
    schema_status: str
    enum_domain: list | None
    reference_target_paths: list[str] | None  # paths this field references/looks up, if any
    schema_version: str
