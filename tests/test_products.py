def test_create_get_update_deactivate_product(client) -> None:
    create_payload = {
        "product_id": "CV-3C-240",
        "product_name": "CV Cable 3C 240sq",
        "product_type": "finished",
        "unit": "m",
    }
    create_response = client.post("/products", json=create_payload)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["product_id"] == "CV-3C-240"
    assert created["status"] == "active"

    get_response = client.get("/products/CV-3C-240")
    assert get_response.status_code == 200
    assert get_response.json()["product_name"] == "CV Cable 3C 240sq"

    patch_response = client.patch(
        "/products/CV-3C-240", json={"product_name": "CV Cable 3C 240sq (rev2)"}
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["product_name"] == "CV Cable 3C 240sq (rev2)"

    delete_response = client.delete("/products/CV-3C-240")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "inactive"


def test_create_duplicate_product_id_conflicts(client) -> None:
    payload = {"product_id": "DUP-001", "product_name": "Duplicate Test"}
    assert client.post("/products", json=payload).status_code == 201
    assert client.post("/products", json=payload).status_code == 409


def test_get_missing_product_returns_404(client) -> None:
    assert client.get("/products/NOPE").status_code == 404


def test_list_products_filters_by_status(client) -> None:
    client.post("/products", json={"product_id": "P-1", "product_name": "P1"})
    client.post("/products", json={"product_id": "P-2", "product_name": "P2"})
    client.delete("/products/P-2")

    active = client.get("/products", params={"status": "active"}).json()
    inactive = client.get("/products", params={"status": "inactive"}).json()

    assert [p["product_id"] for p in active] == ["P-1"]
    assert [p["product_id"] for p in inactive] == ["P-2"]
