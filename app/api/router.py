from fastapi import APIRouter

from app.api.routes import (
    equipment,
    health,
    location,
    meta_schema,
    process_routings,
    products,
    recipes,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(products.router)
api_router.include_router(equipment.router)
api_router.include_router(location.router)
api_router.include_router(recipes.router)
api_router.include_router(process_routings.router)
api_router.include_router(meta_schema.router)
