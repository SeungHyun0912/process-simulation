from app.services import ingestion


def test_classify_entity_uses_heuristic_before_llm(monkeypatch):
    def boom(**kwargs):
        raise AssertionError("LLM should not be called when the heuristic already matches")

    monkeypatch.setattr(ingestion, "extract_structured", boom)

    assert ingestion.classify_entity("Product Master", ["product_id"]) == "product"
    assert ingestion.classify_entity("EquipmentGroups", ["group_id"]) == "equipment_group"


def test_classify_entity_falls_back_to_llm_when_name_is_ambiguous(monkeypatch):
    monkeypatch.setattr(ingestion, "extract_structured", lambda **kwargs: {"entity_key": "recipe"})
    assert ingestion.classify_entity("Sheet1", ["a", "b"]) == "recipe"


def test_build_extraction_schema_matches_fields_by_path_prefix(seeded_meta_schema, db_session):
    schema = ingestion.build_extraction_schema(db_session, "product")
    props = schema["properties"]["records"]["items"]["properties"]

    assert "product_id" in props
    assert "product_name" in props
    assert props["product_id"]["type"] == "string"  # natural key: non-nullable
    assert props["product_name"]["type"] == ["string", "null"]


def test_build_extraction_schema_picks_up_recipe_product_id_despite_different_entity_scope(
    seeded_meta_schema, db_session
):
    # FM_PRODUCT_PRODUCT_ID is tagged entity_scope="product_context" but its path_patterns
    # include "recipes[].product_id" -- prefix matching must still pick it up for "recipe".
    schema = ingestion.build_extraction_schema(db_session, "recipe")
    props = schema["properties"]["records"]["items"]["properties"]
    assert "product_id" in props
    assert "recipe_id" in props


def test_extract_table_calls_llm_with_the_built_schema(seeded_meta_schema, db_session, monkeypatch):
    captured = {}

    def fake_extract(system_prompt, user_content, json_schema):
        captured["schema"] = json_schema
        return {
            "column_mappings": [
                {"raw_header": "ID", "mapped_canonical_key": "product_id", "confidence": 0.95}
            ],
            "records": [{"product_id": "CV-1", "product_name": "Cable"}],
        }

    monkeypatch.setattr(ingestion, "extract_structured", fake_extract)

    result = ingestion.extract_table(db_session, "product", ["ID", "Name"], [["CV-1", "Cable"]])

    assert result["records"] == [{"product_id": "CV-1", "product_name": "Cable"}]
    assert "product_id" in captured["schema"]["properties"]["records"]["items"]["properties"]


def test_promote_draft_creates_and_skips_missing_key(db_session):
    from app.models.ingestion import UploadJob, UploadJobDraft
    from app.models.product import Product

    job = UploadJob(source_type="json", status="awaiting_review")
    db_session.add(job)
    db_session.flush()
    draft = UploadJobDraft(
        upload_job_id=job.id,
        entity_key="product",
        records=[
            {"product_id": "CV-1", "product_name": "Cable One"},
            {"product_id": None, "product_name": "Missing key"},
        ],
    )
    db_session.add(draft)
    db_session.flush()

    result = ingestion.promote_draft(db_session, draft)
    db_session.commit()

    assert result["created"] == ["CV-1"]
    assert len(result["skipped"]) == 1
    assert db_session.query(Product).filter_by(product_id="CV-1").one_or_none() is not None


def test_promote_draft_skips_when_foreign_key_unresolved(db_session):
    from app.models.ingestion import UploadJob, UploadJobDraft

    job = UploadJob(source_type="json", status="awaiting_review")
    db_session.add(job)
    db_session.flush()
    draft = UploadJobDraft(
        upload_job_id=job.id,
        entity_key="transport_route",
        records=[{"route_id": "RT-1", "from_location_id": "NOPE", "to_location_id": "ALSO-NOPE"}],
    )
    db_session.add(draft)
    db_session.flush()

    result = ingestion.promote_draft(db_session, draft)

    assert result["created"] == []
    assert "not found" in result["skipped"][0]["reason"]
