import app.services.ingestion as ingestion_module


def _stub_product_extraction(records):
    return {
        "column_mappings": [
            {"raw_header": "ID", "mapped_canonical_key": "product_id", "confidence": 0.95},
            {"raw_header": "Name", "mapped_canonical_key": "product_name", "confidence": 0.9},
        ],
        "records": records,
    }


def test_upload_payload_end_to_end_through_approve(client, seeded_meta_schema, monkeypatch):
    monkeypatch.setattr(ingestion_module, "classify_entity", lambda name, headers: "product")
    monkeypatch.setattr(
        ingestion_module,
        "extract_structured",
        lambda **kwargs: _stub_product_extraction([{"product_id": "CV-1", "product_name": "Cable One"}]),
    )

    response = client.post(
        "/ingestion/jobs/payload",
        json={"source_type": "array", "payload": [{"ID": "CV-1", "Name": "Cable One"}]},
    )
    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "awaiting_review"

    drafts = client.get(f"/ingestion/jobs/{job['id']}/drafts").json()
    assert len(drafts) == 1
    assert drafts[0]["records"] == [{"product_id": "CV-1", "product_name": "Cable One"}]
    draft_id = drafts[0]["id"]

    mappings = client.get(f"/ingestion/jobs/{job['id']}/field-mappings").json()
    assert {m["raw_header_text"] for m in mappings} == {"ID", "Name"}

    approve = client.post(f"/ingestion/jobs/{job['id']}/drafts/{draft_id}/approve")
    assert approve.status_code == 200
    assert approve.json()["created"] == ["CV-1"]
    assert client.get("/products/CV-1").status_code == 200


def test_upload_unclassifiable_table_marks_job_failed(client, seeded_meta_schema, monkeypatch):
    monkeypatch.setattr(ingestion_module, "classify_entity", lambda name, headers: None)

    response = client.post("/ingestion/jobs/payload", json={"source_type": "array", "payload": [{"a": 1}]})

    assert response.status_code == 201
    assert response.json()["status"] == "failed"


def test_update_draft_before_approve(client, seeded_meta_schema, monkeypatch):
    monkeypatch.setattr(ingestion_module, "classify_entity", lambda name, headers: "product")
    monkeypatch.setattr(
        ingestion_module,
        "extract_structured",
        lambda **kwargs: _stub_product_extraction([{"product_id": "WRONG-ID", "product_name": "Typo"}]),
    )

    response = client.post("/ingestion/jobs/payload", json={"source_type": "array", "payload": [{"a": "b"}]})
    job_id = response.json()["id"]
    draft_id = client.get(f"/ingestion/jobs/{job_id}/drafts").json()[0]["id"]

    patched = client.patch(
        f"/ingestion/jobs/{job_id}/drafts/{draft_id}",
        json={"records": [{"product_id": "CV-9", "product_name": "Fixed"}]},
    )
    assert patched.json()["records"] == [{"product_id": "CV-9", "product_name": "Fixed"}]

    approve = client.post(f"/ingestion/jobs/{job_id}/drafts/{draft_id}/approve")
    assert approve.json()["created"] == ["CV-9"]


def test_approving_twice_conflicts(client, seeded_meta_schema, monkeypatch):
    monkeypatch.setattr(ingestion_module, "classify_entity", lambda name, headers: "product")
    monkeypatch.setattr(
        ingestion_module,
        "extract_structured",
        lambda **kwargs: _stub_product_extraction([{"product_id": "CV-1", "product_name": "X"}]),
    )

    response = client.post("/ingestion/jobs/payload", json={"source_type": "array", "payload": [{"a": 1}]})
    job_id = response.json()["id"]
    draft_id = client.get(f"/ingestion/jobs/{job_id}/drafts").json()[0]["id"]

    assert client.post(f"/ingestion/jobs/{job_id}/drafts/{draft_id}/approve").status_code == 200
    assert client.post(f"/ingestion/jobs/{job_id}/drafts/{draft_id}/approve").status_code == 409


def test_missing_job_returns_404(client) -> None:
    assert client.get("/ingestion/jobs/999").status_code == 404
