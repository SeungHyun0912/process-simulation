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


def test_batch_step_carries_batch_size_and_unit(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})

    response = client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "4",
            "production_type": "batch",
            "batch_size": 500,
            "batch_unit": "m",
        },
    )
    assert response.status_code == 201
    step = response.json()
    assert step["batch_size"] == 500
    assert step["batch_unit"] == "m"


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
        json={
            "step_no": "1",
            "std_speed": 80.0,
            "equipment_group": "GRP-DRAW",
            "outputs": [{"output_item_id": "OUT-1"}],
        },
    )

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert report["blocking_errors"] == []
    assert report["graph_completeness_status"] == "provisional"  # step schema_status still provisional

    routing = client.get("/products/CV-3C-240/routings/v1").json()
    assert routing["status"] == "validated"


def test_validate_blocks_on_step_with_no_output(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post("/products/CV-3C-240/routings/v1/steps", json={"step_no": "1"})

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert report["graph_completeness_status"] == "blocked"
    assert any(e["rule_id"] == "BLOCK_STEP_HAS_NO_OUTPUT" for e in report["blocking_errors"])


def test_validate_blocks_on_transition_referencing_unknown_output_item(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "1",
            "outputs": [{"output_item_id": "OUT-1"}],
            "next_steps": [{"step_no": "1", "output_item_id": "NOT-A-REAL-OUTPUT"}],
        },
    )

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert report["graph_completeness_status"] == "blocked"
    assert any(e["rule_id"] == "BLOCK_TRANSITION_OUTPUT_ITEM_UNKNOWN" for e in report["blocking_errors"])


def test_validate_blocks_on_ambiguous_multi_output_transition(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "1",
            "outputs": [
                {"output_item_id": "OUT-1", "output_ratio": 0.6},
                {"output_item_id": "OUT-2", "output_ratio": 0.4},
            ],
            "next_steps": [{"step_no": "1"}],  # ambiguous: doesn't say which of the two outputs
        },
    )

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert any(e["rule_id"] == "BLOCK_TRANSITION_OUTPUT_ITEM_UNKNOWN" for e in report["blocking_errors"])


def test_validate_warns_when_output_ratios_dont_sum_to_one(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "1",
            "outputs": [
                {"output_item_id": "OUT-1", "output_ratio": 0.6},
                {"output_item_id": "OUT-2", "output_ratio": 0.3},
            ],
        },
    )

    report = client.post("/products/CV-3C-240/routings/v1/validate").json()
    assert not any(e["rule_id"] == "BLOCK_STEP_HAS_NO_OUTPUT" for e in report["blocking_errors"])
    assert any(w["rule_id"] == "WARN_OUTPUT_RATIO_SUM" for w in report["warnings"])


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
        json={
            "step_no": "1",
            "std_speed": 80.0,
            "equipment_group": "GRP-DRAW",
            "schema_status": "official",
            "outputs": [{"output_item_id": "OUT-1"}],
        },
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
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "outputs": [{"output_item_id": "OUT-1"}]},
    )
    assert client.post("/products/CV-3C-240/routings/v1/publish").status_code == 200

    response = client.post(
        "/products/CV-3C-240/routings/v1/steps", json={"step_no": "2"}
    )
    assert response.status_code == 409


def test_clone_creates_new_draft_version_with_copied_steps(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "1",
            "std_speed": 80.0,
            "outputs": [{"output_item_id": "OUT-1"}],
            "next_steps": [{"step_no": "1"}],
        },
    )
    assert client.post("/products/CV-3C-240/routings/v1/publish").status_code == 200

    clone_response = client.post("/products/CV-3C-240/routings/v1/clone")
    assert clone_response.status_code == 201
    clone = clone_response.json()
    assert clone["version"] == "v2"
    assert clone["status"] == "draft"
    assert len(clone["steps"]) == 1
    assert clone["steps"][0]["std_time_per"] == 0.0125
    assert clone["steps"][0]["outputs"][0]["output_item_id"] == "OUT-1"
    assert clone["steps"][0]["next_steps"][0]["to_step_no"] == "1"
