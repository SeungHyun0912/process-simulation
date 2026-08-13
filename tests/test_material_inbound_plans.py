def test_create_material_inbound_plan_requires_existing_location(client) -> None:
    response = client.post(
        "/material-inbound-plans",
        json={
            "plan_id": "PLAN-CU-ROD",
            "item_id": "ROD-CU-8MM",
            "location_id": "WH-RAW",
            "inbound_qty": 5000,
            "inbound_unit": "m",
        },
    )
    assert response.status_code == 404

    client.post("/locations", json={"location_id": "WH-RAW", "location_type": "warehouse"})

    response = client.post(
        "/material-inbound-plans",
        json={
            "plan_id": "PLAN-CU-ROD",
            "item_id": "ROD-CU-8MM",
            "location_id": "WH-RAW",
            "inbound_qty": 5000,
            "inbound_unit": "m",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["interval_value"] == 1
    assert body["interval_unit"] == "day"


def test_list_material_inbound_plans_filtered_by_item(client) -> None:
    client.post("/locations", json={"location_id": "WH-RAW", "location_type": "warehouse"})
    client.post(
        "/material-inbound-plans",
        json={"plan_id": "PLAN-A", "item_id": "ITEM-A", "location_id": "WH-RAW", "inbound_qty": 100},
    )
    client.post(
        "/material-inbound-plans",
        json={"plan_id": "PLAN-B", "item_id": "ITEM-B", "location_id": "WH-RAW", "inbound_qty": 200},
    )

    response = client.get("/material-inbound-plans", params={"item_id": "ITEM-A"})
    assert [p["plan_id"] for p in response.json()] == ["PLAN-A"]


def test_update_and_delete_material_inbound_plan(client) -> None:
    client.post("/locations", json={"location_id": "WH-RAW", "location_type": "warehouse"})
    client.post(
        "/material-inbound-plans",
        json={"plan_id": "PLAN-A", "item_id": "ITEM-A", "location_id": "WH-RAW", "inbound_qty": 100},
    )

    patch_response = client.patch("/material-inbound-plans/PLAN-A", json={"inbound_qty": 80})
    assert patch_response.json()["inbound_qty"] == 80

    assert client.delete("/material-inbound-plans/PLAN-A").status_code == 204
    assert client.get("/material-inbound-plans/PLAN-A").status_code == 404
