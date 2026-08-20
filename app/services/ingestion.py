"""LLM-assisted ingestion: raw tabular data -> canonical draft records.

Pipeline (docs/planning/03-llm-ingestion.md): parse -> classify each table
against a fixed set of promotable entities -> build that entity's extraction
schema from meta_field_mapping -> LLM structured extraction -> store as a
provisional draft for human review -> /approve promotes into the real tables.

Schema generation matches on path_pattern PREFIX (e.g. "products[]."), not on
FIELD_META_REGISTRY's entity_scope tag. Those two don't always agree -- e.g.
FM_PRODUCT_PRODUCT_ID is tagged entity_scope="product_context" but its
path_patterns also include "recipes[].product_id", because product_id is
shared across entities. Matching by path prefix picks up every field that
actually belongs to the target table regardless of which entity_scope label
the registry entry happens to carry.

Only entities with a simple 1:1 target table are supported end-to-end here.
process_step is deliberately excluded: promoting a step needs a target
ProcessRouting version, which a generic upload has no context for.
"""

from sqlalchemy.orm import Session

from app.models.equipment import EquipmentGroup
from app.models.ingestion import UploadFieldAlias, UploadFieldMapping, UploadJob, UploadJobDraft
from app.models.location import Location, TransportRoute
from app.models.meta_schema import MetaCommonField, MetaFieldMapping
from app.models.product import Product
from app.models.recipe import Recipe
from app.services.llm_client import extract_structured

MAX_ROWS_PER_EXTRACTION = 500
ALIAS_CONFIDENCE_THRESHOLD = 0.6

PROMOTABLE_ENTITIES: dict[str, str] = {
    "product": "products[].",
    "equipment_group": "equipments[].",
    "location": "locations[].",
    "transport_route": "transport_routes[].",
    "recipe": "recipes[].",
}

NATURAL_KEY_FIELD = {
    "product": "product_id",
    "equipment_group": "group_id",
    "location": "location_id",
    "transport_route": "route_id",
    "recipe": "recipe_id",
}

PROMOTION_MODEL = {
    "product": Product,
    "equipment_group": EquipmentGroup,
    "location": Location,
    "transport_route": TransportRoute,
    "recipe": Recipe,
}

# (field_on_record, referenced_model, referenced_model_natural_key, required)
FK_CHECKS: dict[str, list[tuple[str, type, str, bool]]] = {
    "transport_route": [
        ("from_location_id", Location, "location_id", True),
        ("to_location_id", Location, "location_id", True),
    ],
    "recipe": [("product_id", Product, "product_id", False)],
}

_JSON_TYPE = {"string": "string", "number": "number", "integer": "integer", "boolean": "boolean"}


def _is_flat_field(path: str, prefix: str) -> bool:
    """True for "products[].product_name", false for "products[].cable_design.conductor.material".

    The promotable models here (Product, EquipmentGroup, ...) only expose flat scalar
    columns, not the nested cable_design/recipe sub-objects -- and canonical_key isn't
    even unique across those nested paths (e.g. "material" appears for conductor,
    insulation, and sheath alike), so including them would silently collide in the
    flat {canonical_key: json_schema_property} dict built below.
    """
    return path.startswith(prefix) and "." not in path[len(prefix) :]


def _fields_for_entity(db: Session, entity_key: str) -> list[MetaFieldMapping]:
    """Every registered field whose path_patterns include at least one flat path under this
    entity's prefix (see module docstring for why this matches by path prefix, not entity_scope)."""
    prefix = PROMOTABLE_ENTITIES[entity_key]
    return [
        m for m in db.query(MetaFieldMapping).all() if any(_is_flat_field(p, prefix) for p in m.path_patterns)
    ]


def build_extraction_schema(db: Session, entity_key: str) -> dict:
    """Build the json_schema handed to the LLM for one entity: a `column_mappings` array (which
    raw header maps to which canonical field, and how confidently) plus a `records` array typed
    from that entity's actual field registry. The natural key field is forced non-nullable/
    non-optional-enum so the LLM can't silently omit the field promote_draft() dedupes on."""
    fields = _fields_for_entity(db, entity_key)
    natural_key = NATURAL_KEY_FIELD[entity_key]

    record_properties = {}
    for field in fields:
        base_type = _JSON_TYPE.get(field.canonical_type, "string")
        is_key = field.canonical_key == natural_key
        prop: dict = {"type": base_type if is_key else [base_type, "null"]}
        if field.enum_domain:
            prop["enum"] = list(field.enum_domain) if is_key else [*field.enum_domain, None]
        record_properties[field.canonical_key] = prop

    return {
        "type": "object",
        "properties": {
            "column_mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "raw_header": {"type": "string"},
                        "mapped_canonical_key": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["raw_header", "mapped_canonical_key", "confidence"],
                    "additionalProperties": False,
                },
            },
            "records": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": record_properties,
                    "required": list(record_properties.keys()),
                    "additionalProperties": False,
                },
            },
        },
        "required": ["column_mappings", "records"],
        "additionalProperties": False,
    }


def classify_entity(table_name: str, headers: list[str]) -> str | None:
    """Which promotable entity a raw table represents, or None if it doesn't fit any.
    Cheap substring match on the table name first; only falls through to an LLM call when
    the name itself doesn't already give it away."""
    normalized = table_name.lower().replace("_", "").replace(" ", "")
    for entity_key in PROMOTABLE_ENTITIES:
        if entity_key.replace("_", "") in normalized:
            return entity_key

    schema = {
        "type": "object",
        "properties": {
            "entity_key": {"type": ["string", "null"], "enum": [*PROMOTABLE_ENTITIES.keys(), None]}
        },
        "required": ["entity_key"],
        "additionalProperties": False,
    }
    result = extract_structured(
        system_prompt=(
            "You classify a spreadsheet/table as one of a fixed set of manufacturing master-data "
            "entities based on its name and column headers. If none plausibly fit, return null."
        ),
        user_content=f"Table name: {table_name}\nColumns: {', '.join(headers)}",
        json_schema=schema,
    )
    return result.get("entity_key")


def extract_table(db: Session, entity_key: str, headers: list[str], rows: list[list]) -> dict:
    """Run the LLM extraction for one already-classified table, capping how many rows are sent
    in a single call (MAX_ROWS_PER_EXTRACTION) to keep the prompt/response within budget."""
    schema = build_extraction_schema(db, entity_key)
    sample_rows = rows[:MAX_ROWS_PER_EXTRACTION]
    dropped = len(rows) - len(sample_rows)

    user_content = (
        f"Extract every row below into the target schema.\nColumns: {headers}\n"
        f"Rows (arrays aligned to columns): {sample_rows}"
    )
    if dropped > 0:
        user_content += f"\n\n({dropped} additional rows were truncated and are not included here.)"

    return extract_structured(
        system_prompt=(
            f"You map raw spreadsheet columns to the canonical fields of a '{entity_key}' record and "
            "extract every row given. Use null for values you can't confidently map or that are missing. "
            "Normalize free-text values (including non-English text) to the schema's enum values where given."
        ),
        user_content=user_content,
        json_schema=schema,
    )


def run_ingestion_job(db: Session, upload_job: UploadJob, tables: list[dict]) -> None:
    """Classify + extract every table in one upload, writing one UploadJobDraft (for human
    review) and its column mappings per successfully-classified table. Unclassifiable tables
    are silently skipped rather than failing the whole job -- a single upload can legitimately
    mix recognizable master-data sheets with unrelated ones."""
    drafts_created = 0
    for table in tables:
        entity_key = classify_entity(table["name"], table["headers"])
        if entity_key is None:
            continue

        result = extract_table(db, entity_key, table["headers"], table["rows"])

        db.add(
            UploadJobDraft(
                upload_job_id=upload_job.id,
                entity_key=entity_key,
                source_label=table["name"],
                records=result["records"],
            )
        )
        drafts_created += 1
        for mapping in result["column_mappings"]:
            common_field = None
            if mapping["mapped_canonical_key"]:
                common_field = (
                    db.query(MetaCommonField)
                    .filter_by(canonical_key=mapping["mapped_canonical_key"])
                    .first()
                )
            db.add(
                UploadFieldMapping(
                    upload_job_id=upload_job.id,
                    source_label=table["name"],
                    raw_header_text=mapping["raw_header"],
                    mapped_common_field_id=common_field.id if common_field else None,
                    mapped_canonical_key=mapping["mapped_canonical_key"],
                    confidence=mapping["confidence"],
                    decided_by="llm",
                )
            )

    # The job only fails outright if literally nothing could be classified; any successful
    # draft is enough to hand the job to a human reviewer.
    upload_job.status = "awaiting_review" if drafts_created > 0 else "failed"
    if drafts_created == 0:
        upload_job.error_message = "no table could be classified into a known entity"


def record_field_aliases(db: Session, upload_job: UploadJob) -> None:
    """Learn raw-header -> canonical-field mappings from this job's confident LLM decisions."""
    mappings = db.query(UploadFieldMapping).filter_by(upload_job_id=upload_job.id).all()
    for mapping in mappings:
        if mapping.mapped_common_field_id is None:
            continue
        if (mapping.confidence or 0) < ALIAS_CONFIDENCE_THRESHOLD:
            continue

        normalized = mapping.raw_header_text.strip().lower()
        alias = db.query(UploadFieldAlias).filter_by(raw_header_text_normalized=normalized).one_or_none()
        if alias is None:
            db.add(
                UploadFieldAlias(
                    raw_header_text_normalized=normalized,
                    common_field_id=mapping.mapped_common_field_id,
                    hit_count=1,
                )
            )
        else:
            alias.common_field_id = mapping.mapped_common_field_id
            alias.hit_count += 1


def promote_draft(db: Session, draft: UploadJobDraft) -> dict:
    """Insert a reviewed draft's records into their real master-data table. Best-effort per
    record, not all-or-nothing: a record missing its natural key, colliding with an existing
    row, or failing an FK check is skipped (with a reason) rather than aborting the whole
    draft, since one bad row in an LLM-extracted batch shouldn't block the rest."""
    model = PROMOTION_MODEL[draft.entity_key]
    natural_key = NATURAL_KEY_FIELD[draft.entity_key]
    fk_checks = FK_CHECKS.get(draft.entity_key, [])

    created: list[str] = []
    skipped: list[dict] = []

    for record in draft.records:
        key_value = record.get(natural_key)
        if not key_value:
            skipped.append({"record": record, "reason": f"missing {natural_key}"})
            continue

        if db.query(model).filter_by(**{natural_key: key_value}).one_or_none() is not None:
            skipped.append({"record": record, "reason": f"{natural_key} {key_value} already exists"})
            continue

        # Verify every declared FK-like field (FK_CHECKS) actually resolves before inserting --
        # the LLM extracted these as plain strings, so nothing enforces referential integrity
        # until this point.
        fk_failure = None
        for field_name, ref_model, ref_key, required in fk_checks:
            value = record.get(field_name)
            if value is None:
                if required:
                    fk_failure = f"missing {field_name}"
                continue
            if db.query(ref_model).filter_by(**{ref_key: value}).one_or_none() is None:
                fk_failure = f"{field_name} {value} not found"
                break
        if fk_failure:
            skipped.append({"record": record, "reason": fk_failure})
            continue

        # Drop nulls rather than passing them through: lets the model's own column defaults
        # apply instead of explicitly overwriting them with None.
        clean = {k: v for k, v in record.items() if v is not None}
        db.add(model(**clean))
        created.append(key_value)

    draft.status = "approved"
    return {"created": created, "skipped": skipped}
