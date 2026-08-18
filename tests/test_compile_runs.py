def _create_product(client, product_id: str = "CV-3C-240") -> None:
    assert (
        client.post("/products", json={"product_id": product_id, "product_name": "CV Cable"}).status_code
        == 201
    )


def test_compile_blocks_on_unresolved_processing_time(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post("/products/CV-3C-240/routings/v1/steps", json={"step_no": "1"})

    response = client.post("/compile-runs", json={"product_id": "CV-3C-240", "version": "v1"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "blocked"
    assert body["compiled_graph_object"] is None
    assert any(
        e["rule_id"] == "BLOCK_UNRESOLVED_PROCESSING_TIME" for e in body["validation_report"]["blocking_errors"]
    )


def test_compile_missing_routing_returns_404(client) -> None:
    _create_product(client)
    response = client.post("/compile-runs", json={"product_id": "CV-3C-240", "version": "v1"})
    assert response.status_code == 404


def test_compile_succeeds_and_produces_graph_object(client) -> None:
    _create_product(client)
    client.post("/equipment-groups", json={"group_id": "GRP-DRAW", "capacity": 2})
    client.post("/locations", json={"location_id": "WH-RAW", "location_type": "warehouse"})
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "1",
            "std_speed": 80.0,
            "equipment_group": "GRP-DRAW",
            "input_location_id": "WH-RAW",
            "schema_status": "official",
        },
    )

    response = client.post("/compile-runs", json={"product_id": "CV-3C-240", "version": "v1"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "success"

    graph = body["compiled_graph_object"]
    assert graph["product_context"]["product_id"] == "CV-3C-240"
    assert graph["graph_summary"]["node_count"] == 1
    assert graph["nodes"][0]["step_no"] == "1"
    assert graph["resource_bindings"][0] == {
        "step_no": "1",
        "resource_key": "GRP-DRAW",
        "resource_type": "simpy.Resource",
        "resolved_resource_id": None,
        "capacity": 2,
        "capacity_source": "master_data",
    }
    assert graph["processing_time_plan"][0]["std_time_per"] == 0.0125
    assert graph["queue_plan"][0]["queue_id"] == "Q::CV-3C-240::1"
    assert graph["runtime_echo"]["duration_days"] == 30  # default runtime profile


def test_compile_with_named_runtime_profile_echoes_overrides(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "std_speed": 80.0, "schema_status": "official"},
    )
    client.post(
        "/runtime-profiles",
        json={"profile_name": "short-run", "time_control": {"duration_days": 7}},
    )

    response = client.post(
        "/compile-runs",
        json={"product_id": "CV-3C-240", "version": "v1", "runtime_profile_name": "short-run"},
    )
    body = response.json()
    assert body["status"] == "success"
    assert body["compiled_graph_object"]["runtime_echo"]["duration_days"] == 7


def test_compile_unknown_runtime_profile_returns_404(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={"step_no": "1", "std_speed": 80.0},
    )

    response = client.post(
        "/compile-runs",
        json={"product_id": "CV-3C-240", "version": "v1", "runtime_profile_name": "nope"},
    )
    assert response.status_code == 404


def test_compile_marks_parallel_split_and_merge_transitions(client) -> None:
    _create_product(client)
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "1",
            "std_speed": 80.0,
            "schema_status": "official",
            "next_steps": [{"step_no": "2"}, {"step_no": "3"}],
        },
    )
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "2",
            "std_speed": 60.0,
            "flow_type": "parallel",
            "parallel_group_id": "PG-1",
            "schema_status": "official",
            "next_steps": [{"step_no": "4"}],
        },
    )
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "3",
            "std_speed": 60.0,
            "flow_type": "parallel",
            "parallel_group_id": "PG-1",
            "schema_status": "official",
            "next_steps": [{"step_no": "4"}],
        },
    )
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "4",
            "std_speed": 40.0,
            "flow_type": "merge",
            "join_condition": "all_required_inputs",
            "schema_status": "official",
        },
    )

    response = client.post("/compile-runs", json={"product_id": "CV-3C-240", "version": "v1"})
    body = response.json()
    assert body["status"] == "success"
    graph = body["compiled_graph_object"]

    assert graph["graph_summary"]["has_parallel_branch"] is True
    assert graph["graph_summary"]["has_merge"] is True

    transitions_by_pair = {(t["from_step_no"], t["to_step_no"]): t for t in graph["transitions"]}
    assert transitions_by_pair[("1", "2")]["transition_type"] == "parallel_split"
    assert transitions_by_pair[("1", "3")]["transition_type"] == "parallel_split"
    assert transitions_by_pair[("2", "4")]["transition_type"] == "merge_input"
    assert transitions_by_pair[("3", "4")]["transition_type"] == "merge_input"

    queue_by_step = {q["step_no"]: q for q in graph["queue_plan"]}
    assert queue_by_step["4"]["merge_policy"] == "wait_for_all_required_inputs"
