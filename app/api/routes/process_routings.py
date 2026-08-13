from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.equipment import EquipmentGroup
from app.models.process_routing import ProcessRouting, ProcessStep, ProcessStepTransition
from app.models.product import Product
from app.schemas.process_routing import (
    ProcessRoutingCreate,
    ProcessRoutingRead,
    ProcessStepCreate,
    ProcessStepRead,
    ProcessStepUpdate,
    ValidationReport,
)

router = APIRouter(prefix="/products/{product_id}/routings", tags=["process-routings"])


def _get_product_or_404(db: Session, product_id: str) -> Product:
    product = db.query(Product).filter_by(product_id=product_id).one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return product


def _get_routing_or_404(db: Session, product_id: str, version: str) -> ProcessRouting:
    routing = (
        db.query(ProcessRouting).filter_by(product_id=product_id, version=version).one_or_none()
    )
    if routing is None:
        raise HTTPException(status_code=404, detail=f"routing {product_id}/{version} not found")
    return routing


def _get_step_or_404(routing: ProcessRouting, step_no: str) -> ProcessStep:
    for step in routing.steps:
        if step.step_no == step_no:
            return step
    raise HTTPException(status_code=404, detail=f"step {step_no} not found in this routing")


def _next_version(db: Session, product_id: str) -> str:
    count = db.query(ProcessRouting).filter_by(product_id=product_id).count()
    return f"v{count + 1}"


def _require_editable(routing: ProcessRouting) -> None:
    if routing.status not in ("draft", "validated"):
        raise HTTPException(
            status_code=409,
            detail=f"routing {routing.version} is {routing.status}; use /clone to create an editable version",
        )


def _apply_step_fields(step: ProcessStep, data: dict) -> None:
    next_steps_payload = data.pop("next_steps", None)
    for field, value in data.items():
        setattr(step, field, value)

    # FM_ROUTING_STD_TIME_PER.editable=false: always recomputed from std_speed, never taken from input.
    step.std_time_per = round(1 / step.std_speed, 6) if step.std_speed else None

    if next_steps_payload is not None:
        step.next_steps.clear()
        for transition in next_steps_payload:
            condition = transition["condition"]
            step.next_steps.append(
                ProcessStepTransition(
                    to_step_no=transition["step_no"],
                    condition=condition,
                    interpreted_condition="always_true" if not condition else "application_defined_expression",
                )
            )


def _build_validation_report(routing: ProcessRouting, db: Session) -> dict:
    steps = routing.steps
    step_nos = {s.step_no for s in steps}
    blocking_errors = []
    warnings = []

    if not steps:
        blocking_errors.append(
            {"rule_id": "BLOCK_GRAPH_INCOMPLETE", "path": "steps", "message": "routing has no steps"}
        )

    for step in steps:
        for transition in step.next_steps:
            if transition.to_step_no not in step_nos:
                blocking_errors.append(
                    {
                        "rule_id": "BLOCK_DANGLING_NEXT_STEP",
                        "path": f"steps[{step.step_no}].next_steps",
                        "message": (
                            f"{step.step_no} -> {transition.to_step_no} but step "
                            f"{transition.to_step_no} is missing"
                        ),
                    }
                )

        if step.equipment_group:
            resolved = (
                db.query(EquipmentGroup).filter_by(group_id=step.equipment_group).one_or_none()
                is not None
            )
            equipment_group_ref = "resolved" if resolved else "master_missing"
            if not resolved:
                blocking_errors.append(
                    {
                        "rule_id": "BLOCK_MISSING_RESOURCE_MASTER",
                        "path": f"steps[{step.step_no}].equipment_group",
                        "message": f"{step.equipment_group} is not resolved in equipment_group master",
                    }
                )
        else:
            equipment_group_ref = "provisional"

        step.reference_status = {"equipment_group_ref": equipment_group_ref}

        if step.schema_status == "provisional":
            warnings.append(
                {
                    "rule_id": "ALLOW_PROVISIONAL_STEP",
                    "path": f"steps[{step.step_no}]",
                    "message": f"step {step.step_no} is provisional",
                }
            )

    if not steps:
        completeness = "incomplete"
    elif blocking_errors:
        completeness = "blocked"
    elif any(s.schema_status == "provisional" for s in steps):
        completeness = "provisional"
    else:
        completeness = "complete"

    routing.graph_completeness_status = completeness
    return {
        "graph_completeness_status": completeness,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
    }


@router.get("", response_model=list[ProcessRoutingRead])
def list_routings(product_id: str, db: Session = Depends(get_db)) -> list[ProcessRouting]:
    _get_product_or_404(db, product_id)
    return db.query(ProcessRouting).filter_by(product_id=product_id).order_by(ProcessRouting.id).all()


@router.post("", response_model=ProcessRoutingRead, status_code=201)
def create_routing(
    product_id: str, payload: ProcessRoutingCreate, db: Session = Depends(get_db)
) -> ProcessRouting:
    _get_product_or_404(db, product_id)
    version = payload.version or _next_version(db, product_id)
    if db.query(ProcessRouting).filter_by(product_id=product_id, version=version).one_or_none():
        raise HTTPException(status_code=409, detail=f"routing version {version} already exists")

    routing = ProcessRouting(product_id=product_id, version=version)
    db.add(routing)
    db.commit()
    db.refresh(routing)
    return routing


@router.get("/{version}", response_model=ProcessRoutingRead)
def get_routing(product_id: str, version: str, db: Session = Depends(get_db)) -> ProcessRouting:
    return _get_routing_or_404(db, product_id, version)


@router.post("/{version}/steps", response_model=ProcessStepRead, status_code=201)
def add_step(
    product_id: str, version: str, payload: ProcessStepCreate, db: Session = Depends(get_db)
) -> ProcessStep:
    routing = _get_routing_or_404(db, product_id, version)
    _require_editable(routing)
    if any(s.step_no == payload.step_no for s in routing.steps):
        raise HTTPException(status_code=409, detail=f"step {payload.step_no} already exists")

    data = payload.model_dump()
    step = ProcessStep(routing_id=routing.id, step_no=data.pop("step_no"))
    _apply_step_fields(step, data)
    db.add(step)
    routing.status = "draft"
    db.commit()
    db.refresh(step)
    return step


@router.patch("/{version}/steps/{step_no}", response_model=ProcessStepRead)
def update_step(
    product_id: str,
    version: str,
    step_no: str,
    payload: ProcessStepUpdate,
    db: Session = Depends(get_db),
) -> ProcessStep:
    routing = _get_routing_or_404(db, product_id, version)
    _require_editable(routing)
    step = _get_step_or_404(routing, step_no)
    _apply_step_fields(step, payload.model_dump(exclude_unset=True))
    routing.status = "draft"
    db.commit()
    db.refresh(step)
    return step


@router.delete("/{version}/steps/{step_no}", status_code=204)
def delete_step(product_id: str, version: str, step_no: str, db: Session = Depends(get_db)) -> None:
    routing = _get_routing_or_404(db, product_id, version)
    _require_editable(routing)
    step = _get_step_or_404(routing, step_no)
    db.delete(step)
    routing.status = "draft"
    db.commit()


@router.post("/{version}/validate", response_model=ValidationReport)
def validate_routing(product_id: str, version: str, db: Session = Depends(get_db)) -> dict:
    routing = _get_routing_or_404(db, product_id, version)
    report = _build_validation_report(routing, db)
    if not report["blocking_errors"] and routing.status == "draft":
        routing.status = "validated"
    db.commit()
    return report


@router.post("/{version}/publish", response_model=ProcessRoutingRead)
def publish_routing(product_id: str, version: str, db: Session = Depends(get_db)) -> ProcessRouting:
    routing = _get_routing_or_404(db, product_id, version)
    report = _build_validation_report(routing, db)
    if report["graph_completeness_status"] in ("incomplete", "blocked"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "cannot publish: graph is incomplete or blocked",
                "validation_report": report,
            },
        )

    db.query(ProcessRouting).filter_by(product_id=product_id).update({"is_active": False})
    routing.status = "published"
    routing.is_active = True
    db.commit()
    db.refresh(routing)
    return routing


@router.post("/{version}/clone", response_model=ProcessRoutingRead, status_code=201)
def clone_routing(product_id: str, version: str, db: Session = Depends(get_db)) -> ProcessRouting:
    source = _get_routing_or_404(db, product_id, version)
    clone = ProcessRouting(product_id=product_id, version=_next_version(db, product_id), status="draft")
    db.add(clone)
    db.flush()

    for step in source.steps:
        new_step = ProcessStep(
            routing_id=clone.id,
            step_no=step.step_no,
            process_id=step.process_id,
            process_group_id=step.process_group_id,
            process_name=step.process_name,
            input_item_id=step.input_item_id,
            output_item_id=step.output_item_id,
            input_qty_per=step.input_qty_per,
            equipment_group=step.equipment_group,
            std_speed=step.std_speed,
            std_time_per=step.std_time_per,
            setup_time=step.setup_time,
            flow_type=step.flow_type,
            parallel_group_id=step.parallel_group_id,
            join_condition=step.join_condition,
            production_type=step.production_type,
            input_location_id=step.input_location_id,
            output_location_id=step.output_location_id,
            inbound_route_id=step.inbound_route_id,
            process_specific=step.process_specific,
            schema_status=step.schema_status,
        )
        for transition in step.next_steps:
            new_step.next_steps.append(
                ProcessStepTransition(
                    to_step_no=transition.to_step_no,
                    condition=transition.condition,
                    interpreted_condition=transition.interpreted_condition,
                )
            )
        db.add(new_step)

    db.commit()
    db.refresh(clone)
    return clone
