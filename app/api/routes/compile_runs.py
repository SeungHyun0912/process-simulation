from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.compile_run import CompileRun
from app.models.process_routing import ProcessRouting, RoutingProductLink
from app.models.runtime_profile import RuntimeProfile
from app.schemas.compile_run import CompileRunCreate, CompileRunRead
from app.services.compiler import compile_routing

router = APIRouter(prefix="/compile-runs", tags=["compile-runs"])


def _get_routing_or_404(db: Session, product_id: str, version: str) -> ProcessRouting:
    """Looks up via RoutingProductLink, not ProcessRouting.product_id directly, so a product
    linked (not just the primary owner) to a shared network can also compile it (docs/planning/
    07-schema-gap-review.md section 6)."""
    routing = (
        db.query(ProcessRouting)
        .join(RoutingProductLink, RoutingProductLink.routing_id == ProcessRouting.id)
        .filter(RoutingProductLink.product_id == product_id, ProcessRouting.version == version)
        .one_or_none()
    )
    if routing is None:
        raise HTTPException(status_code=404, detail=f"routing {product_id}/{version} not found")
    return routing


# Compile a routing's graph (plus optional runtime profile) into the compiled_graph_object that
# the simulation engine consumes; the compiler itself decides pass/fail (see compile_routing) --
# this endpoint just persists whatever status/report it returns.
@router.post("", response_model=CompileRunRead, status_code=201)
def create_compile_run(payload: CompileRunCreate, db: Session = Depends(get_db)) -> CompileRun:
    routing = _get_routing_or_404(db, payload.product_id, payload.version)

    runtime_profile = None
    if payload.runtime_profile_name is not None:
        runtime_profile = (
            db.query(RuntimeProfile).filter_by(profile_name=payload.runtime_profile_name).one_or_none()
        )
        if runtime_profile is None:
            raise HTTPException(
                status_code=404, detail=f"runtime profile {payload.runtime_profile_name} not found"
            )

    result = compile_routing(routing, runtime_profile, db)

    compile_run = CompileRun(
        routing_id=routing.id,
        routing_version=routing.version,
        # Snapshot every product currently linked to this routing at compile time, since the
        # routing's links can change later while this compile run stays a fixed historical record.
        bound_product_ids=[link.product_id for link in routing.product_links],
        runtime_profile_id=runtime_profile.id if runtime_profile else None,
        status=result["status"],
        compiled_graph_object=result["compiled_graph_object"],
        validation_report=result["validation_report"],
    )
    db.add(compile_run)
    db.commit()
    db.refresh(compile_run)
    return compile_run


@router.get("/{compile_run_id}", response_model=CompileRunRead)
def get_compile_run(compile_run_id: int, db: Session = Depends(get_db)) -> CompileRun:
    compile_run = db.get(CompileRun, compile_run_id)
    if compile_run is None:
        raise HTTPException(status_code=404, detail=f"compile run {compile_run_id} not found")
    return compile_run
