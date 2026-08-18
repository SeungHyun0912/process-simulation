from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.compile_run import CompileRun
from app.models.process_routing import ProcessRouting
from app.models.runtime_profile import RuntimeProfile
from app.schemas.compile_run import CompileRunCreate, CompileRunRead
from app.services.compiler import compile_routing

router = APIRouter(prefix="/compile-runs", tags=["compile-runs"])


def _get_routing_or_404(db: Session, product_id: str, version: str) -> ProcessRouting:
    routing = (
        db.query(ProcessRouting).filter_by(product_id=product_id, version=version).one_or_none()
    )
    if routing is None:
        raise HTTPException(status_code=404, detail=f"routing {product_id}/{version} not found")
    return routing


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
        product_id=routing.product_id,
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
