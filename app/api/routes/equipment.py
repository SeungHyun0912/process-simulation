from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.equipment import Equipment, EquipmentGroup
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentGroupCreate,
    EquipmentGroupRead,
    EquipmentGroupUpdate,
    EquipmentRead,
    EquipmentUpdate,
)

router = APIRouter(tags=["equipment"])


def _get_group_or_404(db: Session, group_id: str) -> EquipmentGroup:
    group = db.query(EquipmentGroup).filter_by(group_id=group_id).one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail=f"equipment group {group_id} not found")
    return group


def _get_equipment_or_404(db: Session, equipment_id: str) -> Equipment:
    equipment = db.query(Equipment).filter_by(equipment_id=equipment_id).one_or_none()
    if equipment is None:
        raise HTTPException(status_code=404, detail=f"equipment {equipment_id} not found")
    return equipment


@router.get("/equipment-groups", response_model=list[EquipmentGroupRead])
def list_equipment_groups(db: Session = Depends(get_db)) -> list[EquipmentGroup]:
    return db.query(EquipmentGroup).order_by(EquipmentGroup.id).all()


@router.post("/equipment-groups", response_model=EquipmentGroupRead, status_code=201)
def create_equipment_group(
    payload: EquipmentGroupCreate, db: Session = Depends(get_db)
) -> EquipmentGroup:
    if db.query(EquipmentGroup).filter_by(group_id=payload.group_id).one_or_none():
        raise HTTPException(status_code=409, detail=f"equipment group {payload.group_id} already exists")
    group = EquipmentGroup(**payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("/equipment-groups/{group_id}", response_model=EquipmentGroupRead)
def get_equipment_group(group_id: str, db: Session = Depends(get_db)) -> EquipmentGroup:
    return _get_group_or_404(db, group_id)


@router.patch("/equipment-groups/{group_id}", response_model=EquipmentGroupRead)
def update_equipment_group(
    group_id: str, payload: EquipmentGroupUpdate, db: Session = Depends(get_db)
) -> EquipmentGroup:
    group = _get_group_or_404(db, group_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    db.commit()
    db.refresh(group)
    return group


@router.delete("/equipment-groups/{group_id}", status_code=204)
def delete_equipment_group(group_id: str, db: Session = Depends(get_db)) -> None:
    group = _get_group_or_404(db, group_id)
    db.delete(group)
    db.commit()


@router.get("/equipments", response_model=list[EquipmentRead])
def list_equipments(group_id: str | None = None, db: Session = Depends(get_db)) -> list[Equipment]:
    query = db.query(Equipment)
    if group_id is not None:
        query = query.filter_by(group_id=group_id)
    return query.order_by(Equipment.id).all()


@router.post("/equipments", response_model=EquipmentRead, status_code=201)
def create_equipment(payload: EquipmentCreate, db: Session = Depends(get_db)) -> Equipment:
    if db.query(Equipment).filter_by(equipment_id=payload.equipment_id).one_or_none():
        raise HTTPException(status_code=409, detail=f"equipment {payload.equipment_id} already exists")
    _get_group_or_404(db, payload.group_id)
    equipment = Equipment(**payload.model_dump())
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


@router.get("/equipments/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: str, db: Session = Depends(get_db)) -> Equipment:
    return _get_equipment_or_404(db, equipment_id)


@router.patch("/equipments/{equipment_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_id: str, payload: EquipmentUpdate, db: Session = Depends(get_db)
) -> Equipment:
    equipment = _get_equipment_or_404(db, equipment_id)
    updates = payload.model_dump(exclude_unset=True)
    if "group_id" in updates:
        _get_group_or_404(db, updates["group_id"])
    for field, value in updates.items():
        setattr(equipment, field, value)
    db.commit()
    db.refresh(equipment)
    return equipment


@router.delete("/equipments/{equipment_id}", status_code=204)
def delete_equipment(equipment_id: str, db: Session = Depends(get_db)) -> None:
    equipment = _get_equipment_or_404(db, equipment_id)
    db.delete(equipment)
    db.commit()
