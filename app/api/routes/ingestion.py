from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ingestion import UploadFieldMapping, UploadJob, UploadJobDraft
from app.schemas.ingestion import (
    JsonPayloadUpload,
    PromoteResult,
    UploadDraftUpdate,
    UploadFieldMappingRead,
    UploadJobDraftRead,
    UploadJobRead,
)
from app.services import file_parsing, ingestion

router = APIRouter(prefix="/ingestion/jobs", tags=["ingestion"])


def _get_job_or_404(db: Session, job_id: int) -> UploadJob:
    job = db.get(UploadJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"upload job {job_id} not found")
    return job


def _get_draft_or_404(db: Session, job_id: int, draft_id: int) -> UploadJobDraft:
    draft = db.query(UploadJobDraft).filter_by(id=draft_id, upload_job_id=job_id).one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail=f"draft {draft_id} not found in job {job_id}")
    return draft


def _run_job(db: Session, job: UploadJob, tables: list[dict]) -> None:
    try:
        ingestion.run_ingestion_job(db, job, tables)
    except Exception as exc:  # noqa: BLE001 -- surfaced via job.error_message, not re-raised
        job.status = "failed"
        job.error_message = str(exc)
    db.commit()


@router.post("/file", response_model=UploadJobRead, status_code=201)
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadJob:
    filename = file.filename or ""
    if filename.lower().endswith(".csv"):
        source_type = "csv"
    elif filename.lower().endswith(".xlsx"):
        source_type = "xlsx"
    else:
        raise HTTPException(
            status_code=400,
            detail="only .csv and .xlsx are supported here; use /ingestion/jobs/payload for JSON/array data",
        )

    raw_bytes = file.file.read()
    job = UploadJob(source_type=source_type, original_filename=filename, status="parsing")
    db.add(job)
    db.flush()

    try:
        tables = file_parsing.parse_source(source_type, raw_bytes=raw_bytes)
    except Exception as exc:  # noqa: BLE001 -- surfaced via job.error_message, not re-raised
        job.status = "failed"
        job.error_message = f"parse error: {exc}"
        db.commit()
        db.refresh(job)
        return job

    _run_job(db, job, tables)
    db.refresh(job)
    return job


@router.post("/payload", response_model=UploadJobRead, status_code=201)
def upload_payload(payload: JsonPayloadUpload, db: Session = Depends(get_db)) -> UploadJob:
    if payload.source_type not in ("json", "array"):
        raise HTTPException(status_code=400, detail="source_type must be 'json' or 'array'")

    job = UploadJob(source_type=payload.source_type, status="parsing")
    db.add(job)
    db.flush()

    tables = file_parsing.parse_source(payload.source_type, payload=payload.payload)
    for table in tables:
        table["name"] = payload.table_name

    _run_job(db, job, tables)
    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=UploadJobRead)
def get_job(job_id: int, db: Session = Depends(get_db)) -> UploadJob:
    return _get_job_or_404(db, job_id)


@router.get("/{job_id}/drafts", response_model=list[UploadJobDraftRead])
def list_drafts(job_id: int, db: Session = Depends(get_db)) -> list[UploadJobDraft]:
    _get_job_or_404(db, job_id)
    return db.query(UploadJobDraft).filter_by(upload_job_id=job_id).all()


@router.get("/{job_id}/field-mappings", response_model=list[UploadFieldMappingRead])
def list_field_mappings(job_id: int, db: Session = Depends(get_db)) -> list[UploadFieldMapping]:
    _get_job_or_404(db, job_id)
    return db.query(UploadFieldMapping).filter_by(upload_job_id=job_id).all()


@router.patch("/{job_id}/drafts/{draft_id}", response_model=UploadJobDraftRead)
def update_draft(
    job_id: int, draft_id: int, payload: UploadDraftUpdate, db: Session = Depends(get_db)
) -> UploadJobDraft:
    draft = _get_draft_or_404(db, job_id, draft_id)
    if draft.status != "awaiting_review":
        raise HTTPException(status_code=409, detail=f"draft is {draft.status}, cannot edit")
    draft.records = payload.records
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/{job_id}/drafts/{draft_id}/approve", response_model=PromoteResult)
def approve_draft(job_id: int, draft_id: int, db: Session = Depends(get_db)) -> dict:
    draft = _get_draft_or_404(db, job_id, draft_id)
    if draft.status != "awaiting_review":
        raise HTTPException(status_code=409, detail=f"draft is {draft.status}, cannot approve")

    result = ingestion.promote_draft(db, draft)
    ingestion.record_field_aliases(db, draft.upload_job)
    db.commit()
    return result
