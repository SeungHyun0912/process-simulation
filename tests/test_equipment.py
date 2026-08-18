def test_create_equipment_requires_existing_group(client) -> None:
    response = client.post(
        "/equipments", json={"equipment_id": "EXT-LINE-A", "group_id": "GRP-EXT"}
    )
    assert response.status_code == 404

    assert client.post("/equipment-groups", json={"group_id": "GRP-EXT", "capacity": 2}).status_code == 201

    response = client.post(
        "/equipments", json={"equipment_id": "EXT-LINE-A", "group_id": "GRP-EXT"}
    )
    assert response.status_code == 201
    assert response.json()["group_id"] == "GRP-EXT"


def test_list_equipments_filtered_by_group(client) -> None:
    client.post("/equipment-groups", json={"group_id": "GRP-A"})
    client.post("/equipment-groups", json={"group_id": "GRP-B"})
    client.post("/equipments", json={"equipment_id": "EQ-A1", "group_id": "GRP-A"})
    client.post("/equipments", json={"equipment_id": "EQ-B1", "group_id": "GRP-B"})

    response = client.get("/equipments", params={"group_id": "GRP-A"})
    assert [e["equipment_id"] for e in response.json()] == ["EQ-A1"]
