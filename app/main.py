"""FastAPI app entry point: builds the app and mounts the single aggregated router."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()  # forces config/env validation to happen at import time, not lazily

app = FastAPI(title="LS Process Simulation API", version="0.1.0")
app.include_router(api_router)
