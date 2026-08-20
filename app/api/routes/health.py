from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


# Liveness check: the API process is up.
@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Readiness check: confirms the DB connection actually works.
@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return {"status": "unavailable", "detail": str(exc)}
    return {"status": "ok"}
