from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.runtime_profile import (
    DEFAULT_EXECUTION_MODE,
    DEFAULT_OUTPUT_CONTROL,
    DEFAULT_POLICY_REFS,
    DEFAULT_SCENARIO_TOGGLES,
    DEFAULT_STOCHASTIC_DEFAULTS,
    DEFAULT_TIME_CONTROL,
    RuntimeProfile,
)
from app.schemas.runtime_profile import RuntimeProfileCreate, RuntimeProfileRead, RuntimeProfileUpdate

router = APIRouter(prefix="/runtime-profiles", tags=["runtime-profiles"])


# Fetch a runtime profile by its business key, 404 if missing.
def _get_profile_or_404(db: Session, profile_name: str) -> RuntimeProfile:
    profile = db.query(RuntimeProfile).filter_by(profile_name=profile_name).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail=f"runtime profile {profile_name} not found")
    return profile


# List all runtime profiles.
@router.get("", response_model=list[RuntimeProfileRead])
def list_runtime_profiles(db: Session = Depends(get_db)) -> list[RuntimeProfile]:
    return db.query(RuntimeProfile).order_by(RuntimeProfile.id).all()


# Create a runtime profile, rejecting a duplicate profile_name.
@router.post("", response_model=RuntimeProfileRead, status_code=201)
def create_runtime_profile(
    payload: RuntimeProfileCreate, db: Session = Depends(get_db)
) -> RuntimeProfile:
    if db.query(RuntimeProfile).filter_by(profile_name=payload.profile_name).one_or_none():
        raise HTTPException(status_code=409, detail=f"runtime profile {payload.profile_name} already exists")

    # each JSON section falls back to its documented default when the caller omits it
    profile = RuntimeProfile(
        profile_name=payload.profile_name,
        time_control=payload.time_control or dict(DEFAULT_TIME_CONTROL),
        execution_mode=payload.execution_mode or dict(DEFAULT_EXECUTION_MODE),
        scenario_toggles=payload.scenario_toggles or dict(DEFAULT_SCENARIO_TOGGLES),
        policy_refs=payload.policy_refs or dict(DEFAULT_POLICY_REFS),
        stochastic_defaults=payload.stochastic_defaults or dict(DEFAULT_STOCHASTIC_DEFAULTS),
        output_control=payload.output_control or dict(DEFAULT_OUTPUT_CONTROL),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


# Get a single runtime profile by name.
@router.get("/{profile_name}", response_model=RuntimeProfileRead)
def get_runtime_profile(profile_name: str, db: Session = Depends(get_db)) -> RuntimeProfile:
    return _get_profile_or_404(db, profile_name)


# Partial update of a runtime profile; only fields present in the payload change.
@router.patch("/{profile_name}", response_model=RuntimeProfileRead)
def update_runtime_profile(
    profile_name: str, payload: RuntimeProfileUpdate, db: Session = Depends(get_db)
) -> RuntimeProfile:
    profile = _get_profile_or_404(db, profile_name)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


# Delete a runtime profile.
@router.delete("/{profile_name}", status_code=204)
def delete_runtime_profile(profile_name: str, db: Session = Depends(get_db)) -> None:
    profile = _get_profile_or_404(db, profile_name)
    db.delete(profile)
    db.commit()
