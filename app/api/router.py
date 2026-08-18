from fastapi import APIRouter

from app.api.routes import (
    compile_runs,
    equipment,
    health,
    ingestion,
    location,
    meta_schema,
    process_routings,
    products,
    recipes,
    runtime_profiles,
    simulation_runs,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(products.router)
api_router.include_router(equipment.router)
api_router.include_router(location.router)
api_router.include_router(recipes.router)
api_router.include_router(process_routings.router)
api_router.include_router(runtime_profiles.router)
api_router.include_router(compile_runs.router)
api_router.include_router(simulation_runs.router)
api_router.include_router(ingestion.router)
api_router.include_router(meta_schema.router)
