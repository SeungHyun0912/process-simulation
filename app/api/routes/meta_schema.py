from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.meta_schema import MetaCommonField, MetaFieldMapping
from app.schemas.meta_schema import CommonFieldRead, FieldMappingRead

router = APIRouter(prefix="/meta-schema", tags=["meta-schema"])


@router.get("/common-fields", response_model=list[CommonFieldRead])
def list_common_fields(db: Session = Depends(get_db)) -> list[MetaCommonField]:
    return db.query(MetaCommonField).order_by(MetaCommonField.common_field_code).all()


@router.get("/field-mappings", response_model=list[FieldMappingRead])
def list_field_mappings(
    entity_scope: str | None = None, db: Session = Depends(get_db)
) -> list[MetaFieldMapping]:
    query = db.query(MetaFieldMapping)
    if entity_scope is not None:
        query = query.filter_by(entity_scope=entity_scope)
    return query.order_by(MetaFieldMapping.field_mapping_code).all()
