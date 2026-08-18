"""Seed meta_common_field / meta_field_mapping from docs/schema/process-schema*.json.

Loads the original schema plus any *-extensions.json files layered on top of it
(see docs/planning/01-meta-schema-design.md for why extensions live in a
separate file instead of editing the original).

Usage (run from repo root, with the venv active):
    python -m scripts.seed_meta_schema
"""

import json
from pathlib import Path

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.meta_schema import MetaCommonField, MetaFieldMapping

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "docs" / "schema"
SCHEMA_PATHS = [
    SCHEMA_DIR / "process-schema.json",
    SCHEMA_DIR / "process-schema-extensions.json",
]


def _upsert_common_fields(db, common_field_dict: dict, code_to_id: dict[str, int]) -> None:
    schema_version = common_field_dict["_meta"]["schema_version"]

    for code, field in common_field_dict["fields"].items():
        row = db.query(MetaCommonField).filter_by(common_field_code=code).one_or_none()
        if row is None:
            row = MetaCommonField(common_field_code=code)
            db.add(row)

        row.canonical_key = field["canonical_key"]
        row.description_ko = field.get("description_ko")
        row.canonical_type = field["canonical_type"]
        row.value_role = field["value_role"]
        row.schema_status = field["schema_status"]
        row.path_sensitive = field.get("path_sensitive", False)
        row.enum_domain = field.get("enum_domain")
        row.unit_family = field.get("unit_family")
        row.derived_from = field.get("derived_from")
        row.formula_id = field.get("formula_id")
        row.schema_version = schema_version

        db.flush()
        code_to_id[code] = row.id


def _upsert_field_mappings(db, field_meta_registry: dict, code_to_id: dict[str, int]) -> None:
    schema_version = field_meta_registry["_meta"]["schema_version"]

    for code, entry in field_meta_registry["entries"].items():
        row = db.query(MetaFieldMapping).filter_by(field_mapping_code=code).one_or_none()
        if row is None:
            row = MetaFieldMapping(field_mapping_code=code)
            db.add(row)

        common_field_code = entry.get("common_field_id")
        row.common_field_id = code_to_id.get(common_field_code) if common_field_code else None
        row.canonical_key = entry["canonical_key"]
        row.path_patterns = entry["path_patterns"]
        row.entity_scope = entry["entity_scope"]
        row.canonical_type = entry["canonical_type"]
        row.editable = entry.get("editable", True)
        row.value_role = entry["value_role"]
        row.schema_status = entry["schema_status"]
        row.enum_domain = entry.get("enum_domain")
        row.reference_target_paths = entry.get("reference_target_paths")
        row.schema_version = schema_version


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in SCHEMA_PATHS if path.exists()]

    db = SessionLocal()
    try:
        code_to_id: dict[str, int] = {}
        total_mappings = 0
        for schema in schemas:
            _upsert_common_fields(db, schema["COMMON_FIELD_DICTIONARY"], code_to_id)
        for schema in schemas:
            _upsert_field_mappings(db, schema["FIELD_META_REGISTRY"], code_to_id)
            total_mappings += len(schema["FIELD_META_REGISTRY"]["entries"])
        db.commit()
        print(f"seeded {len(code_to_id)} common fields and {total_mappings} field mappings")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
