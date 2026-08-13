def _create_product(client, product_id: str = "CV-3C-240") -> None:
    response = client.post(
        "/products", json={"product_id": product_id, "product_name": "CV Cable 3C 240sq"}
    )
    assert response.status_code == 201


def test_create_routing_starts_incomplete_with_no_steps(client) -> None:
    _create_product(client)

    response = client.post("/products/CV-3C-240/routings", json={})
    assert response.status_code == 201
    body = response.json()
    assert body["version"] == "v1"
    assert body["status"] == "draft"
    assert body["graph_completeness_status"] == "incomplete"
    assert body["steps"] == []


def test_add_step_derives_std_time_per_and_ignores_direct_input(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})

    response = client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "std_speed": 80.0, "equipment_group": "GRP-DRAW"},
    )
    assert response.status_code == 201
    step = response.json()
    assert step["std_time_per"] == 0.0125
    assert step["schema_status"] == "provisional"


def test_validate_blocks_on_missing_equipment_group_master(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "std_speed": 80.0, "equipment_group": "GRP-DRAW"},
    )

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert report["graph_completeness_status"] == "blocked"
    assert any(e["rule_id"] == "BLOCK_MISSING_RESOURCE_MASTER" for e in report["blocking_errors"])

    routing = client.get("/products/CV-3C-240/routings/v1").json()
    assert routing["status"] == "draft"  # not promoted to validated while blocked


def test_validate_passes_once_equipment_group_exists_but_stays_provisional(client) -> None:
    _create_product(client)
    client.post("/equipment-groups", json={"group_id": "GRP-DRAW"})
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "std_speed": 80.0, "equipment_group": "GRP-DRAW"},
    )

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert report["blocking_errors"] == []
    assert report["graph_completeness_status"] == "provisional"  # step schema_status still provisional

    routing = client.get("/products/CV-3C-240/routings/v1").json()
    assert routing["status"] == "validated"


def test_validate_blocks_on_dangling_next_step(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "next_steps": [{"step_no": "2"}]},
    )

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert report["graph_completeness_status"] == "blocked"
    assert any(e["rule_id"] == "BLOCK_DANGLING_NEXT_STEP" for e in report["blocking_errors"])


def test_publish_requires_non_blocked_graph_then_activates(client) -> None:
    _create_product(client)
    client.post("/equipment-groups", json={"group_id": "GRP-DRAW"})
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "std_speed": 80.0, "equipment_group": "GRP-DRAW", "schema_status": "official"},
    )

    publish_response = client.post("/products/CV-3C-240/routings/v1/publish")
    assert publish_response.status_code == 200
    body = publish_response.json()
    assert body["status"] == "published"
    assert body["is_active"] is True
    assert body["graph_completeness_status"] == "complete"


def test_cannot_edit_published_routing_without_cloning(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post("/products/CV-3C-240/routings/v1/steps", json={"step_no": "1"})
    client.post("/products/CV-3C-240/routings/v1/publish")

    response = client.post(
        "/products/CV-3C-240/routings/v1/steps", json={"step_no": "2"}
    )
    assert response.status_code == 409


def test_clone_creates_new_draft_version_with_copied_steps(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "std_speed": 80.0, "next_steps": [{"step_no": "1"}]},
    )
    client.post("/products/CV-3C-240/routings/v1/publish")

    clone_response = client.post("/products/CV-3C-240/routings/v1/clone")
    assert clone_response.status_code == 201
    clone = clone_response.json()
    assert clone["version"] == "v2"
    assert clone["status"] == "draft"
    assert len(clone["steps"]) == 1
    assert clone["steps"][0]["std_time_per"] == 0.0125
    assert clone["steps"][0]["next_steps"][0]["to_step_no"] == "1"
