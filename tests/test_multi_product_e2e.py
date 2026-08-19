"""End-to-end case from docs/planning/07-schema-gap-review.md section 6: raw material through
a shared step 1, forking into two SKUs (X, Y) that never rejoin but share equipment downstream.
"""


def _build_shared_network(client) -> None:
    client.post("/products", json={"product_id": "X", "product_name": "Product X"})
    client.post("/products", json={"product_id": "Y", "product_name": "Product Y"})
    client.post("/equipment-groups", json={"group_id": "E1", "capacity": 1})
    client.post("/equipment-groups", json={"group_id": "E2", "capacity": 1})
    client.post("/locations", json={"location_id": "WH", "location_type": "warehouse"})
    client.post(
        "/material-inbound-plans",
        json={"plan_id": "PLAN-RAW", "item_id": "RAW", "location_id": "WH", "inbound_qty": 100_000},
    )

    client.post("/products/X/routings", json={})
    client.post(
        "/products/X/routings/v1/steps",
        json={
            "step_no": "1",
            "input_item_id": "RAW",
            "input_location_id": "WH",
            "std_speed": 60,
            "equipment_group": "E1",
            "schema_status": "official",
            "outputs": [{"output_item_id": "MID"}],
            "next_steps": [{"step_no": "2A"}, {"step_no": "2B"}],
        },
    )
    client.post(
        "/products/X/routings/v1/steps",
        json={
            "step_no": "2A",
            "input_item_id": "MID",
            "std_speed": 60,
            "equipment_group": "E2",
            "schema_status": "official",
            "outputs": [{"output_item_id": "FINISHED-X"}],
        },
    )
    client.post(
        "/products/X/routings/v1/steps",
        json={
            "step_no": "2B",
            "input_item_id": "MID",
            "std_speed": 60,
            "equipment_group": "E2",
            "schema_status": "official",
            "outputs": [{"output_item_id": "FINISHED-Y"}],
        },
    )
    assert client.post(
        "/products/X/routings/v1/link",
        json={"product_id": "Y", "entry_step_nos": ["1"], "terminal_step_nos": ["2B"]},
    ).status_code == 201


def test_shared_network_compiles_with_both_product_contexts(client) -> None:
    _build_shared_network(client)

    response = client.post("/compile-runs", json={"product_id": "X", "version": "v1"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "success"
    assert set(body["bound_product_ids"]) == {"X", "Y"}

    graph = body["compiled_graph_object"]
    contexts_by_product = {c["product_id"]: c for c in graph["product_contexts"]}
    assert set(contexts_by_product["X"]["terminal_step_nos"]) == {"2A", "2B"}  # primary: whole live graph
    assert contexts_by_product["Y"]["terminal_step_nos"] == ["2B"]  # forked: explicit narrow slice
    assert graph["graph_summary"]["linked_product_ids"] == ["X", "Y"]


def test_shared_equipment_contention_and_per_product_throughput_filtering(client) -> None:
    _build_shared_network(client)

    compile_body = client.post("/compile-runs", json={"product_id": "X", "version": "v1"}).json()
    assert compile_body["status"] == "success"

    sim_body = client.post("/simulation-runs", json={"compile_run_id": compile_body["id"]}).json()
    assert sim_body["status"] == "succeeded"
    run_id = sim_body["id"]

    network_summary = client.get(f"/simulation-runs/{run_id}/results/summary").json()
    # 2A and 2B share E2 (capacity 1): they can't both run at once, so utilization is bounded
    # but nonzero -- the same "combined contention" proof used in test_simulation_service.py.
    assert 0.0 < network_summary["resource_utilization"]["E2"] <= 1.0
    assert network_summary["exit_qty_by_step"]["2A"] > 0
    assert network_summary["exit_qty_by_step"]["2B"] > 0

    x_summary = client.get(f"/simulation-runs/{run_id}/results/summary", params={"product_id": "X"}).json()
    y_summary = client.get(f"/simulation-runs/{run_id}/results/summary", params={"product_id": "Y"}).json()

    # X is the primary link (whole live graph = both branches); Y is forked to just 2B.
    assert set(x_summary["exit_qty_by_step"].keys()) == {"2A", "2B"}
    assert set(y_summary["exit_qty_by_step"].keys()) == {"2B"}
    assert x_summary["throughput_total"] > y_summary["throughput_total"]
    assert y_summary["throughput_total"] == network_summary["exit_qty_by_step"]["2B"]

    # Shared resource utilization is reported identically regardless of which product asks --
    # there's no such thing as a "per-product" utilization of a resource two products contend for.
    assert x_summary["resource_utilization"] == y_summary["resource_utilization"] == network_summary["resource_utilization"]


def test_summary_for_unlinked_product_returns_404(client) -> None:
    _build_shared_network(client)
    client.post("/products", json={"product_id": "Z", "product_name": "unrelated"})

    compile_body = client.post("/compile-runs", json={"product_id": "X", "version": "v1"}).json()
    sim_body = client.post("/simulation-runs", json={"compile_run_id": compile_body["id"]}).json()

    response = client.get(f"/simulation-runs/{sim_body['id']}/results/summary", params={"product_id": "Z"})
    assert response.status_code == 404
