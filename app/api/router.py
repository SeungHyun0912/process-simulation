from fastapi import APIRouter

from app.api.routes import health, meta_schema, products

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(products.router)
api_router.include_router(meta_schema.router)
