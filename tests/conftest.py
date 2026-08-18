import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers ORM models on Base.metadata)
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/ls_process_simulation_test",
)

test_engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _reset_schema():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture
def db_session():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_meta_schema(db_session):
    """Seed meta_common_field/meta_field_mapping into the test DB for ingestion tests."""
    from scripts.seed_meta_schema import SCHEMA_PATHS, _upsert_common_fields, _upsert_field_mappings

    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in SCHEMA_PATHS if p.exists()]
    code_to_id: dict[str, int] = {}
    for schema in schemas:
        _upsert_common_fields(db_session, schema["COMMON_FIELD_DICTIONARY"], code_to_id)
    for schema in schemas:
        _upsert_field_mappings(db_session, schema["FIELD_META_REGISTRY"], code_to_id)
    db_session.commit()
    return code_to_id


@pytest.fixture
def client():
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
