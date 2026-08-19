def _create_product(client, product_id: str) -> None:
    assert client.post("/products", json={"product_id": product_id, "product_name": product_id}).status_code == 201


def _fork_routing(client) -> None:
    """product X owns a routing: 1 -> (2A, 2B), a plain fan-out (no ratio split needed here)."""
    _create_product(client, "X")
    client.post("/products/X/routings", json={})
    client.post(
        "/products/X/routings/v1/steps",
        json={"step_no": "1", "outputs": [{"output_item_id": "OUT-1"}], "next_steps": [{"step_no": "2A"}, {"step_no": "2B"}]},
    )
    client.post("/products/X/routings/v1/steps", json={"step_no": "2A", "outputs": [{"output_item_id": "FIN-X"}]})
    client.post("/products/X/routings/v1/steps", json={"step_no": "2B", "outputs": [{"output_item_id": "FIN-Y"}]})


def test_create_routing_auto_creates_primary_link(client) -> None:
    _create_product(client, "X")
    response = client.post("/products/X/routings", json={})
    assert response.json()["linked_product_ids"] == ["X"]


def test_link_product_to_shared_routing(client) -> None:
    _fork_routing(client)
    _create_product(client, "Y")

    response = client.post(
        "/products/X/routings/v1/link",
        json={"product_id": "Y", "entry_step_nos": ["1"], "terminal_step_nos": ["2B"]},
    )
    assert response.status_code == 201
    assert response.json() == {
        "product_id": "Y",
        "entry_step_nos": ["1"],
        "terminal_step_nos": ["2B"],
        "is_primary": False,
    }

    routing = client.get("/products/X/routings/v1").json()
    assert set(routing["linked_product_ids"]) == {"X", "Y"}

    # Y can now reach the same routing under its own product path.
    y_routings = client.get("/products/Y/routings").json()
    assert len(y_routings) == 1
    assert y_routings[0]["version"] == "v1"


def test_link_duplicate_product_conflicts(client) -> None:
    _fork_routing(client)
    _create_product(client, "Y")
    client.post(
        "/products/X/routings/v1/link",
        json={"product_id": "Y", "entry_step_nos": ["1"], "terminal_step_nos": ["2B"]},
    )
    response = client.post(
        "/products/X/routings/v1/link",
        json={"product_id": "Y", "entry_step_nos": ["1"], "terminal_step_nos": ["2B"]},
    )
    assert response.status_code == 409


def test_link_unresolved_step_blocks_validation(client) -> None:
    _fork_routing(client)
    _create_product(client, "Y")
    client.post(
        "/products/X/routings/v1/link",
        json={"product_id": "Y", "entry_step_nos": ["1"], "terminal_step_nos": ["NOT-A-STEP"]},
    )

    report = client.post("/products/X/routings/v1/validate").json()
    assert report["graph_completeness_status"] == "blocked"
    assert any(e["rule_id"] == "BLOCK_UNRESOLVED_LINK_STEP" for e in report["blocking_errors"])


def test_get_routing_scope_product_filters_to_forked_subgraph(client) -> None:
    _fork_routing(client)
    _create_product(client, "Y")
    client.post(
        "/products/X/routings/v1/link",
        json={"product_id": "Y", "entry_step_nos": ["1"], "terminal_step_nos": ["2B"]},
    )

    y_view = client.get("/products/Y/routings/v1", params={"scope": "product"}).json()
    assert {s["step_no"] for s in y_view["steps"]} == {"1", "2B"}

    y_network_view = client.get("/products/Y/routings/v1", params={"scope": "network"}).json()
    assert {s["step_no"] for s in y_network_view["steps"]} == {"1", "2A", "2B"}


def test_get_routing_invalid_scope_rejected(client) -> None:
    _fork_routing(client)
    response = client.get("/products/X/routings/v1", params={"scope": "bogus"})
    assert response.status_code == 400
