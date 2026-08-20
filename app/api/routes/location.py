from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.location import Location, MaterialInboundPlan, TransportRoute
from app.schemas.location import (
    LocationCreate,
    LocationRead,
    LocationUpdate,
    MaterialInboundPlanCreate,
    MaterialInboundPlanRead,
    MaterialInboundPlanUpdate,
    TransportRouteCreate,
    TransportRouteRead,
    TransportRouteUpdate,
)

router = APIRouter(tags=["locations"])


# Fetch a location by its business key, 404 if missing.
def _get_location_or_404(db: Session, location_id: str) -> Location:
    location = db.query(Location).filter_by(location_id=location_id).one_or_none()
    if location is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return location


# Fetch a transport route by its business key, 404 if missing.
def _get_route_or_404(db: Session, route_id: str) -> TransportRoute:
    route = db.query(TransportRoute).filter_by(route_id=route_id).one_or_none()
    if route is None:
        raise HTTPException(status_code=404, detail=f"transport route {route_id} not found")
    return route


def _apply_derived_transport_time(route: TransportRoute) -> None:
    """CF_TRANSPORT_TIME: raw value wins if given, otherwise derive distance/speed (docs/planning/01)."""
    if route.transport_time is None and route.transport_distance is not None and route.transport_speed:
        route.transport_time = round(route.transport_distance / route.transport_speed, 6)


# List locations, optionally filtered by type.
@router.get("/locations", response_model=list[LocationRead])
def list_locations(location_type: str | None = None, db: Session = Depends(get_db)) -> list[Location]:
    query = db.query(Location)
    if location_type is not None:
        query = query.filter_by(location_type=location_type)
    return query.order_by(Location.id).all()


# Create a location, rejecting a duplicate location_id.
@router.post("/locations", response_model=LocationRead, status_code=201)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)) -> Location:
    if db.query(Location).filter_by(location_id=payload.location_id).one_or_none():
        raise HTTPException(status_code=409, detail=f"location {payload.location_id} already exists")
    location = Location(**payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


# Get a single location by id.
@router.get("/locations/{location_id}", response_model=LocationRead)
def get_location(location_id: str, db: Session = Depends(get_db)) -> Location:
    return _get_location_or_404(db, location_id)


# Partial update of a location; only fields present in the payload change.
@router.patch("/locations/{location_id}", response_model=LocationRead)
def update_location(
    location_id: str, payload: LocationUpdate, db: Session = Depends(get_db)
) -> Location:
    location = _get_location_or_404(db, location_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(location, field, value)
    db.commit()
    db.refresh(location)
    return location


# Delete a location.
@router.delete("/locations/{location_id}", status_code=204)
def delete_location(location_id: str, db: Session = Depends(get_db)) -> None:
    location = _get_location_or_404(db, location_id)
    db.delete(location)
    db.commit()


# List all transport routes.
@router.get("/transport-routes", response_model=list[TransportRouteRead])
def list_transport_routes(db: Session = Depends(get_db)) -> list[TransportRoute]:
    return db.query(TransportRoute).order_by(TransportRoute.id).all()


# Create a transport route, rejecting a duplicate route_id.
@router.post("/transport-routes", response_model=TransportRouteRead, status_code=201)
def create_transport_route(
    payload: TransportRouteCreate, db: Session = Depends(get_db)
) -> TransportRoute:
    if db.query(TransportRoute).filter_by(route_id=payload.route_id).one_or_none():
        raise HTTPException(status_code=409, detail=f"transport route {payload.route_id} already exists")
    # both endpoints are FK-backed; check up front so an unknown location yields a clean 404
    _get_location_or_404(db, payload.from_location_id)
    _get_location_or_404(db, payload.to_location_id)
    route = TransportRoute(**payload.model_dump())
    _apply_derived_transport_time(route)
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


# Get a single transport route by id.
@router.get("/transport-routes/{route_id}", response_model=TransportRouteRead)
def get_transport_route(route_id: str, db: Session = Depends(get_db)) -> TransportRoute:
    return _get_route_or_404(db, route_id)


# Partial update of a transport route; re-derives transport_time if inputs changed.
@router.patch("/transport-routes/{route_id}", response_model=TransportRouteRead)
def update_transport_route(
    route_id: str, payload: TransportRouteUpdate, db: Session = Depends(get_db)
) -> TransportRoute:
    route = _get_route_or_404(db, route_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(route, field, value)
    _apply_derived_transport_time(route)
    db.commit()
    db.refresh(route)
    return route


# Delete a transport route.
@router.delete("/transport-routes/{route_id}", status_code=204)
def delete_transport_route(route_id: str, db: Session = Depends(get_db)) -> None:
    route = _get_route_or_404(db, route_id)
    db.delete(route)
    db.commit()


# Fetch a material inbound plan by its business key, 404 if missing.
def _get_inbound_plan_or_404(db: Session, plan_id: str) -> MaterialInboundPlan:
    plan = db.query(MaterialInboundPlan).filter_by(plan_id=plan_id).one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail=f"material inbound plan {plan_id} not found")
    return plan


# List material inbound plans, optionally filtered by item and/or location.
@router.get("/material-inbound-plans", response_model=list[MaterialInboundPlanRead])
def list_material_inbound_plans(
    item_id: str | None = None, location_id: str | None = None, db: Session = Depends(get_db)
) -> list[MaterialInboundPlan]:
    query = db.query(MaterialInboundPlan)
    if item_id is not None:
        query = query.filter_by(item_id=item_id)
    if location_id is not None:
        query = query.filter_by(location_id=location_id)
    return query.order_by(MaterialInboundPlan.id).all()


# Create a material inbound plan, rejecting a duplicate plan_id.
@router.post("/material-inbound-plans", response_model=MaterialInboundPlanRead, status_code=201)
def create_material_inbound_plan(
    payload: MaterialInboundPlanCreate, db: Session = Depends(get_db)
) -> MaterialInboundPlan:
    if db.query(MaterialInboundPlan).filter_by(plan_id=payload.plan_id).one_or_none():
        raise HTTPException(status_code=409, detail=f"material inbound plan {payload.plan_id} already exists")
    # location_id is FK-backed; check up front so an unknown location yields a clean 404
    _get_location_or_404(db, payload.location_id)
    plan = MaterialInboundPlan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# Get a single material inbound plan by id.
@router.get("/material-inbound-plans/{plan_id}", response_model=MaterialInboundPlanRead)
def get_material_inbound_plan(plan_id: str, db: Session = Depends(get_db)) -> MaterialInboundPlan:
    return _get_inbound_plan_or_404(db, plan_id)


# Partial update of a material inbound plan; only fields present in the payload change.
@router.patch("/material-inbound-plans/{plan_id}", response_model=MaterialInboundPlanRead)
def update_material_inbound_plan(
    plan_id: str, payload: MaterialInboundPlanUpdate, db: Session = Depends(get_db)
) -> MaterialInboundPlan:
    plan = _get_inbound_plan_or_404(db, plan_id)
    updates = payload.model_dump(exclude_unset=True)
    if "location_id" in updates:
        # re-validate the new location_id since it's FK-backed
        _get_location_or_404(db, updates["location_id"])
    for field, value in updates.items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    return plan


# Delete a material inbound plan.
@router.delete("/material-inbound-plans/{plan_id}", status_code=204)
def delete_material_inbound_plan(plan_id: str, db: Session = Depends(get_db)) -> None:
    plan = _get_inbound_plan_or_404(db, plan_id)
    db.delete(plan)
    db.commit()
