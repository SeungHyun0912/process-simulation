def test_transport_route_derives_time_from_distance_and_speed(client) -> None:
    client.post("/locations", json={"location_id": "WH-1", "location_type": "warehouse"})
    client.post("/locations", json={"location_id": "LINE-1", "location_type": "line_buffer"})

    response = client.post(
        "/transport-routes",
        json={
            "route_id": "RT-1",
            "from_location_id": "WH-1",
            "to_location_id": "LINE-1",
            "transport_distance": 100.0,
            "transport_speed": 50.0,
        },
    )
    assert response.status_code == 201
    assert response.json()["transport_time"] == 2.0


def test_transport_route_keeps_explicit_raw_time(client) -> None:
    client.post("/locations", json={"location_id": "WH-1", "location_type": "warehouse"})
    client.post("/locations", json={"location_id": "LINE-1", "location_type": "line_buffer"})

    response = client.post(
        "/transport-routes",
        json={
            "route_id": "RT-2",
            "from_location_id": "WH-1",
            "to_location_id": "LINE-1",
            "transport_distance": 100.0,
            "transport_speed": 50.0,
            "transport_time": 5.0,
        },
    )
    assert response.json()["transport_time"] == 5.0


def test_transport_route_requires_existing_locations(client) -> None:
    response = client.post(
        "/transport-routes",
        json={"route_id": "RT-3", "from_location_id": "NOPE", "to_location_id": "ALSO-NOPE"},
    )
    assert response.status_code == 404
