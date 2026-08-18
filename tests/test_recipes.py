def test_create_and_filter_recipes(client) -> None:
    client.post("/products", json={"product_id": "CV-3C-240", "product_name": "CV Cable 3C 240sq"})

    create_response = client.post(
        "/recipes",
        json={
            "recipe_id": "REC-1",
            "product_id": "CV-3C-240",
            "process_id": "PROC-INS-A",
            "setup_time": 15,
            "speed": {"fixed": 60.0},
        },
    )
    assert create_response.status_code == 201

    response = client.get("/recipes", params={"process_id": "PROC-INS-A"})
    assert [r["recipe_id"] for r in response.json()] == ["REC-1"]


def test_get_missing_recipe_returns_404(client) -> None:
    assert client.get("/recipes/NOPE").status_code == 404
