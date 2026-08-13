from app.models.meta_schema import MetaCommonField, MetaFieldMapping


def _seed_common_field(db_session) -> MetaCommonField:
    field = MetaCommonField(
        common_field_code="CF_TEST_FIELD",
        canonical_key="test_field",
        description_ko="테스트 필드",
        canonical_type="string",
        value_role="raw",
        schema_status="official",
        path_sensitive=False,
        schema_version="0.1.0-draft",
    )
    db_session.add(field)
    db_session.commit()
    db_session.refresh(field)
    return field


def test_list_common_fields(client, db_session) -> None:
    _seed_common_field(db_session)

    response = client.get("/meta-schema/common-fields")
    assert response.status_code == 200
    codes = [f["common_field_code"] for f in response.json()]
    assert codes == ["CF_TEST_FIELD"]


def test_list_field_mappings_filtered_by_entity_scope(client, db_session) -> None:
    common_field = _seed_common_field(db_session)
    db_session.add_all(
        [
            MetaFieldMapping(
                field_mapping_code="FM_TEST_A",
                common_field_id=common_field.id,
                canonical_key="test_field",
                path_patterns=["products[].test_field"],
                entity_scope="product_master",
                canonical_type="string",
                editable=True,
                value_role="raw",
                schema_status="official",
                schema_version="0.1.0-draft",
            ),
            MetaFieldMapping(
                field_mapping_code="FM_TEST_B",
                common_field_id=common_field.id,
                canonical_key="test_field",
                path_patterns=["locations[].test_field"],
                entity_scope="location_master",
                canonical_type="string",
                editable=True,
                value_role="raw",
                schema_status="provisional",
                schema_version="0.1.0-draft",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/meta-schema/field-mappings", params={"entity_scope": "product_master"})
    assert response.status_code == 200
    codes = [m["field_mapping_code"] for m in response.json()]
    assert codes == ["FM_TEST_A"]
