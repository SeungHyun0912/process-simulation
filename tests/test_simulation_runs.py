def _compiled_routing(client) -> int:
    client.post("/products", json={"product_id": "CV-3C-240", "product_name": "CV Cable"})
    client.post("/equipment-groups", json={"group_id": "GRP-DRAW", "capacity": 1})
    client.post("/locations", json={"location_id": "WH-RAW", "location_type": "warehouse"})
    client.post(
        "/material-inbound-plans",
        json={
            "plan_id": "PLAN-ROD",
            "item_id": "ROD-CU-8MM",
            "location_id": "WH-RAW",
            "inbound_qty": 100_000,
        },
    )
    client.post("/products/CV-3C-240/routings", json={})
    client.post(
        "/products/CV-3C-240/routings/v1/steps",
        json={
            "step_no": "1",
            "input_item_id": "ROD-CU-8MM",
            "output_item_id": "WIRE-CU-DRAWN",
            "input_location_id": "WH-RAW",
            "std_speed": 60.0,
            "equipment_group": "GRP-DRAW",
            "schema_status": "official",
        },
    )
    response = client.post("/compile-runs", json={"product_id": "CV-3C-240", "version": "v1"})
    return response.json()["id"]


def test_simulation_run_requires_successful_compile_run(client) -> None:
    client.post("/products", json={"product_id": "CV-3C-240", "product_name": "CV Cable"})
    client.post("/products/CV-3C-240/routings", json={})
    client.post("/products/CV-3C-240/routings/v1/steps", json={"step_no": "1"})
    blocked_compile = client.post("/compile-runs", json={"product_id": "CV-3C-240", "version": "v1"})

    response = client.post("/simulation-runs", json={"compile_run_id": blocked_compile.json()["id"]})
    assert response.status_code == 409


def test_simulation_run_missing_compile_run_returns_404(client) -> None:
    response = client.post("/simulation-runs", json={"compile_run_id": 999})
    assert response.status_code == 404


def test_simulation_run_succeeds_and_exposes_results(client) -> None:
    compile_run_id = _compiled_routing(client)

    run_response = client.post("/simulation-runs", json={"compile_run_id": compile_run_id})
    assert run_response.status_code == 201
    body = run_response.json()
    assert body["status"] == "succeeded"
    run_id = body["id"]

    summary = client.get(f"/simulation-runs/{run_id}/results/summary")
    assert summary.status_code == 200
    assert summary.json()["throughput_total"] > 0

    events = client.get(f"/simulation-runs/{run_id}/results/events")
    assert events.status_code == 200
    assert len(events.json()) > 0

    utilization = client.get(f"/simulation-runs/{run_id}/results/resource-utilization")
    assert "GRP-DRAW" in utilization.json()


def test_simulation_run_with_inbound_override(client) -> None:
    compile_run_id = _compiled_routing(client)
    # Pin duration to exactly one delivery interval (1440 min) so the override quantity
    # is consumed exactly once -- see tests/test_simulation_service.py for why the second
    # scheduled delivery at t=1440 never fires within this window.
    client.post("/runtime-profiles", json={"profile_name": "one-day", "time_control": {"duration_days": 1}})

    run_response = client.post(
        "/simulation-runs",
        json={
            "compile_run_id": compile_run_id,
            "runtime_profile_name": "one-day",
            "material_inbound_overrides": {"PLAN-ROD": 10},
        },
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    summary = client.get(f"/simulation-runs/{run_id}/results/summary").json()
    assert summary["throughput_total"] == 10


def test_results_for_missing_simulation_run_returns_404(client) -> None:
    assert client.get("/simulation-runs/999").status_code == 404
    assert client.get("/simulation-runs/999/results/summary").status_code == 404
