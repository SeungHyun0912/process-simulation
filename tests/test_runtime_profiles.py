def test_create_runtime_profile_fills_in_defaults(client) -> None:
    response = client.post("/runtime-profiles", json={"profile_name": "baseline"})
    assert response.status_code == 201
    body = response.json()
    assert body["time_control"]["duration_days"] == 30
    assert body["scenario_toggles"]["enable_breakdown"] is False


def test_create_runtime_profile_accepts_overrides(client) -> None:
    response = client.post(
        "/runtime-profiles",
        json={"profile_name": "short-run", "time_control": {"duration_days": 7, "time_unit": "day"}},
    )
    assert response.json()["time_control"]["duration_days"] == 7


def test_update_and_delete_runtime_profile(client) -> None:
    client.post("/runtime-profiles", json={"profile_name": "baseline"})

    patch_response = client.patch(
        "/runtime-profiles/baseline", json={"scenario_toggles": {"enable_breakdown": True}}
    )
    assert patch_response.json()["scenario_toggles"]["enable_breakdown"] is True

    assert client.delete("/runtime-profiles/baseline").status_code == 204
    assert client.get("/runtime-profiles/baseline").status_code == 404


def test_duplicate_profile_name_conflicts(client) -> None:
    client.post("/runtime-profiles", json={"profile_name": "baseline"})
    assert client.post("/runtime-profiles", json={"profile_name": "baseline"}).status_code == 409
