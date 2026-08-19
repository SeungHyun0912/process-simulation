from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.process_routing import (
    ProcessRouting,
    ProcessStep,
    ProcessStepOutput,
    ProcessStepTransition,
    RoutingProductLink,
)
from app.models.product import Product
from app.schemas.process_routing import (
    ProcessRoutingCreate,
    ProcessRoutingRead,
    ProcessStepCreate,
    ProcessStepRead,
    ProcessStepUpdate,
    RoutingLinkCreate,
    RoutingLinkRead,
    ValidationReport,
)
from app.services.routing_validation import build_validation_report, extract_product_subgraph

router = APIRouter(prefix="/products/{product_id}/routings", tags=["process-routings"])


def _get_product_or_404(db: Session, product_id: str) -> Product:
    product = db.query(Product).filter_by(product_id=product_id).one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return product


def _get_routing_or_404(db: Session, product_id: str, version: str) -> ProcessRouting:
    """Looks up via RoutingProductLink, not ProcessRouting.product_id directly, so a product
    linked (not just the primary owner) to a shared network can reach it under its own path
    (docs/planning/07-schema-gap-review.md section 6)."""
    routing = (
        db.query(ProcessRouting)
        .join(RoutingProductLink, RoutingProductLink.routing_id == ProcessRouting.id)
        .filter(RoutingProductLink.product_id == product_id, ProcessRouting.version == version)
        .one_or_none()
    )
    if routing is None:
        raise HTTPException(status_code=404, detail=f"routing {product_id}/{version} not found")
    return routing


def _get_link_or_404(routing: ProcessRouting, product_id: str) -> RoutingProductLink:
    for link in routing.product_links:
        if link.product_id == product_id:
            return link
    raise HTTPException(status_code=404, detail=f"product {product_id} is not linked to this routing")


def _serialize_routing(routing: ProcessRouting, step_no_filter: set[str] | None = None) -> dict:
    steps = routing.steps if step_no_filter is None else [s for s in routing.steps if s.step_no in step_no_filter]
    return {
        "product_id": routing.product_id,
        "version": routing.version,
        "status": routing.status,
        "graph_completeness_status": routing.graph_completeness_status,
        "is_active": routing.is_active,
        "steps": steps,
        "linked_product_ids": [link.product_id for link in routing.product_links],
        "created_at": routing.created_at,
        "updated_at": routing.updated_at,
    }


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
    outputs_payload = data.pop("outputs", None)
    for field, value in data.items():
        setattr(step, field, value)

    # FM_ROUTING_STD_TIME_PER.editable=false: always recomputed from std_speed, never taken from input.
    step.std_time_per = round(1 / step.std_speed, 6) if step.std_speed else None

    if outputs_payload is not None:
        step.outputs.clear()
        for output in outputs_payload:
            step.outputs.append(
                ProcessStepOutput(
                    output_item_id=output["output_item_id"],
                    output_ratio=output["output_ratio"],
                    unit=output["unit"],
                )
            )

    if next_steps_payload is not None:
        step.next_steps.clear()
        for transition in next_steps_payload:
            condition = transition["condition"]
            step.next_steps.append(
                ProcessStepTransition(
                    to_step_no=transition["step_no"],
                    condition=condition,
                    interpreted_condition="always_true" if not condition else "application_defined_expression",
                    output_item_id=transition["output_item_id"],
                    consumption_ratio=transition["consumption_ratio"],
                )
            )


@router.get("", response_model=list[ProcessRoutingRead])
def list_routings(product_id: str, db: Session = Depends(get_db)) -> list[ProcessRouting]:
    _get_product_or_404(db, product_id)
    return (
        db.query(ProcessRouting)
        .join(RoutingProductLink, RoutingProductLink.routing_id == ProcessRouting.id)
        .filter(RoutingProductLink.product_id == product_id)
        .order_by(ProcessRouting.id)
        .all()
    )


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
    db.flush()
    db.add(RoutingProductLink(routing_id=routing.id, product_id=product_id, is_primary=True))
    db.commit()
    db.refresh(routing)
    return routing


@router.get("/{version}", response_model=ProcessRoutingRead)
def get_routing(
    product_id: str, version: str, scope: str = "product", db: Session = Depends(get_db)
) -> dict:
    if scope not in ("product", "network"):
        raise HTTPException(status_code=400, detail="scope must be 'product' or 'network'")
    routing = _get_routing_or_404(db, product_id, version)
    if scope == "network":
        return _serialize_routing(routing)
    link = _get_link_or_404(routing, product_id)
    return _serialize_routing(routing, extract_product_subgraph(routing, link))


@router.post("/{version}/link", response_model=RoutingLinkRead, status_code=201)
def link_product(
    product_id: str, version: str, payload: RoutingLinkCreate, db: Session = Depends(get_db)
) -> RoutingProductLink:
    """Register another product as sharing this routing's network, consuming its own
    entry/terminal subgraph of it (docs/planning/07-schema-gap-review.md section 6)."""
    routing = _get_routing_or_404(db, product_id, version)
    _get_product_or_404(db, payload.product_id)
    if any(link.product_id == payload.product_id for link in routing.product_links):
        raise HTTPException(
            status_code=409, detail=f"product {payload.product_id} is already linked to this routing"
        )

    link = RoutingProductLink(
        routing_id=routing.id,
        product_id=payload.product_id,
        entry_step_nos=payload.entry_step_nos,
        terminal_step_nos=payload.terminal_step_nos,
        is_primary=False,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


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
    report = build_validation_report(routing, db)
    if not report["blocking_errors"] and routing.status == "draft":
        routing.status = "validated"
    db.commit()
    return report


@router.post("/{version}/publish", response_model=ProcessRoutingRead)
def publish_routing(product_id: str, version: str, db: Session = Depends(get_db)) -> ProcessRouting:
    routing = _get_routing_or_404(db, product_id, version)
    report = build_validation_report(routing, db)
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
    db.add(RoutingProductLink(routing_id=clone.id, product_id=product_id, is_primary=True))

    for step in source.steps:
        new_step = ProcessStep(
            routing_id=clone.id,
            step_no=step.step_no,
            process_id=step.process_id,
            process_group_id=step.process_group_id,
            process_name=step.process_name,
            input_item_id=step.input_item_id,
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
            batch_size=step.batch_size,
            batch_unit=step.batch_unit,
            process_specific=step.process_specific,
            schema_status=step.schema_status,
        )
        for output in step.outputs:
            new_step.outputs.append(
                ProcessStepOutput(
                    output_item_id=output.output_item_id,
                    output_ratio=output.output_ratio,
                    unit=output.unit,
                )
            )
        for transition in step.next_steps:
            new_step.next_steps.append(
                ProcessStepTransition(
                    to_step_no=transition.to_step_no,
                    condition=transition.condition,
                    interpreted_condition=transition.interpreted_condition,
                    output_item_id=transition.output_item_id,
                    consumption_ratio=transition.consumption_ratio,
                )
            )
        db.add(new_step)

    db.commit()
    db.refresh(clone)
    return clone
