from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.compile_run import CompileRun
from app.models.location import MaterialInboundPlan
from app.models.process_routing import ProcessRouting
from app.models.runtime_profile import DEFAULT_OUTPUT_CONTROL, DEFAULT_TIME_CONTROL, RuntimeProfile
from app.models.simulation_run import (
    SimulationEventLog,
    SimulationResultSummary,
    SimulationRun,
    SimulationWipSnapshot,
)
from app.schemas.simulation_run import (
    SimulationEventLogRead,
    SimulationResultSummaryRead,
    SimulationRunCreate,
    SimulationRunRead,
    SimulationWipSnapshotRead,
)
from app.services.routing_validation import _link_entry_terminal_steps
from app.services.simulation import run_simulation

router = APIRouter(prefix="/simulation-runs", tags=["simulation-runs"])


def _get_simulation_run_or_404(db: Session, simulation_run_id: int) -> SimulationRun:
    run = db.get(SimulationRun, simulation_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"simulation run {simulation_run_id} not found")
    return run


def _get_result_summary_or_404(db: Session, simulation_run_id: int) -> SimulationResultSummary:
    summary = db.query(SimulationResultSummary).filter_by(simulation_run_id=simulation_run_id).one_or_none()
    if summary is None:
        raise HTTPException(status_code=404, detail="no results for this simulation run")
    return summary


@router.post("", response_model=SimulationRunRead, status_code=201)
def create_simulation_run(payload: SimulationRunCreate, db: Session = Depends(get_db)) -> SimulationRun:
    compile_run = db.get(CompileRun, payload.compile_run_id)
    if compile_run is None:
        raise HTTPException(status_code=404, detail=f"compile run {payload.compile_run_id} not found")
    if compile_run.status != "success":
        raise HTTPException(
            status_code=409,
            detail=f"compile run {payload.compile_run_id} is not usable (status={compile_run.status})",
        )

    runtime_profile = None
    if payload.runtime_profile_name is not None:
        runtime_profile = (
            db.query(RuntimeProfile).filter_by(profile_name=payload.runtime_profile_name).one_or_none()
        )
        if runtime_profile is None:
            raise HTTPException(
                status_code=404, detail=f"runtime profile {payload.runtime_profile_name} not found"
            )

    time_control = runtime_profile.time_control if runtime_profile else dict(DEFAULT_TIME_CONTROL)
    output_control = runtime_profile.output_control if runtime_profile else dict(DEFAULT_OUTPUT_CONTROL)

    inbound_plans = [
        {
            "plan_id": p.plan_id,
            "item_id": p.item_id,
            "location_id": p.location_id,
            "inbound_qty": p.inbound_qty,
            "interval_value": p.interval_value,
            "interval_unit": p.interval_unit,
        }
        for p in db.query(MaterialInboundPlan).all()
    ]

    simulation_run = SimulationRun(
        compile_run_id=compile_run.id,
        runtime_profile_id=runtime_profile.id if runtime_profile else None,
        status="running",
        started_at=datetime.now(timezone.utc),
        material_inbound_overrides=payload.material_inbound_overrides,
    )
    db.add(simulation_run)
    db.flush()

    try:
        result = run_simulation(
            compile_run.compiled_graph_object,
            time_control,
            output_control,
            inbound_plans,
            payload.material_inbound_overrides,
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller via error_message, not re-raised
        simulation_run.status = "failed"
        simulation_run.finished_at = datetime.now(timezone.utc)
        simulation_run.error_message = str(exc)
        db.commit()
        db.refresh(simulation_run)
        return simulation_run

    simulation_run.status = "succeeded"
    simulation_run.finished_at = datetime.now(timezone.utc)

    summary = result["summary"]
    db.add(
        SimulationResultSummary(
            simulation_run_id=simulation_run.id,
            throughput_total=summary["throughput_total"],
            throughput_per_day=summary["throughput_per_day"],
            avg_wip=summary["avg_wip"],
            avg_lead_time=summary["avg_lead_time"],
            resource_utilization=summary["resource_utilization"],
            bottleneck_step_no=summary["bottleneck_step_no"],
            exit_qty_by_step=summary["exit_qty_by_step"],
        )
    )
    for event in result["event_log"]:
        db.add(
            SimulationEventLog(
                simulation_run_id=simulation_run.id,
                sim_time=event["sim_time"],
                event_type=event["event_type"],
                step_no=event.get("step_no"),
                resource_key=event.get("resource_key"),
                item_id=event.get("item_id"),
                qty=event.get("qty"),
            )
        )
    for snapshot in result["wip_snapshots"]:
        db.add(
            SimulationWipSnapshot(
                simulation_run_id=simulation_run.id,
                sim_time=snapshot["sim_time"],
                total_wip=snapshot["total_wip"],
                by_step=snapshot["by_step"],
            )
        )

    db.commit()
    db.refresh(simulation_run)
    return simulation_run


@router.get("/{simulation_run_id}", response_model=SimulationRunRead)
def get_simulation_run(simulation_run_id: int, db: Session = Depends(get_db)) -> SimulationRun:
    return _get_simulation_run_or_404(db, simulation_run_id)


@router.get("/{simulation_run_id}/results/summary", response_model=SimulationResultSummaryRead)
def get_simulation_summary(
    simulation_run_id: int, product_id: str | None = None, db: Session = Depends(get_db)
) -> SimulationResultSummary | dict:
    run = _get_simulation_run_or_404(db, simulation_run_id)
    summary = _get_result_summary_or_404(db, simulation_run_id)
    if product_id is None:
        return summary

    compile_run = db.get(CompileRun, run.compile_run_id)
    routing = db.get(ProcessRouting, compile_run.routing_id)
    link = next((link for link in routing.product_links if link.product_id == product_id), None)
    if link is None:
        raise HTTPException(
            status_code=404, detail=f"product {product_id} is not linked to this simulation's routing"
        )

    _, terminal_step_nos = _link_entry_terminal_steps(routing, link)
    filtered_total = sum(summary.exit_qty_by_step.get(step_no, 0.0) for step_no in terminal_step_nos)
    # Scale proportionally rather than re-deriving duration_days here -- same ratio either way.
    scale = (summary.throughput_per_day / summary.throughput_total) if summary.throughput_total else 0.0

    return {
        "throughput_total": filtered_total,
        "throughput_per_day": filtered_total * scale,
        # avg_wip/avg_lead_time aren't tracked per-product (WIP isn't attributed to a specific
        # product's items) -- these stay network-wide, same as resource_utilization below.
        "avg_wip": summary.avg_wip,
        "avg_lead_time": summary.avg_lead_time,
        "resource_utilization": summary.resource_utilization,
        "bottleneck_step_no": summary.bottleneck_step_no,
        "exit_qty_by_step": {step_no: summary.exit_qty_by_step.get(step_no, 0.0) for step_no in terminal_step_nos},
    }


@router.get("/{simulation_run_id}/results/events", response_model=list[SimulationEventLogRead])
def get_simulation_events(
    simulation_run_id: int,
    step_no: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[SimulationEventLog]:
    _get_simulation_run_or_404(db, simulation_run_id)
    query = db.query(SimulationEventLog).filter_by(simulation_run_id=simulation_run_id)
    if step_no is not None:
        query = query.filter_by(step_no=step_no)
    if event_type is not None:
        query = query.filter_by(event_type=event_type)
    return query.order_by(SimulationEventLog.sim_time).offset(offset).limit(limit).all()


@router.get("/{simulation_run_id}/results/wip-snapshots", response_model=list[SimulationWipSnapshotRead])
def get_simulation_wip_snapshots(
    simulation_run_id: int, db: Session = Depends(get_db)
) -> list[SimulationWipSnapshot]:
    _get_simulation_run_or_404(db, simulation_run_id)
    return (
        db.query(SimulationWipSnapshot)
        .filter_by(simulation_run_id=simulation_run_id)
        .order_by(SimulationWipSnapshot.sim_time)
        .all()
    )


@router.get("/{simulation_run_id}/results/resource-utilization")
def get_simulation_resource_utilization(
    simulation_run_id: int, db: Session = Depends(get_db)
) -> dict:
    _get_simulation_run_or_404(db, simulation_run_id)
    summary = _get_result_summary_or_404(db, simulation_run_id)
    return summary.resource_utilization
