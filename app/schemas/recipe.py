from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RecipeCreate(BaseModel):
    # request body for creating a recipe (process/equipment-specific run parameters)
    recipe_id: str
    product_id: str | None = None
    process_id: str | None = None  # set when recipe_scope targets a single process step
    process_group_id: str | None = None  # set when recipe_scope targets a process group instead
    recipe_scope: str = "equipment"
    setup_time: float | None = None
    speed: dict | None = None  # free-form speed parameters, shape depends on recipe_scope
    length_factor: dict | None = None  # free-form length-adjustment parameters (JSON)
    cable_recipe: dict | None = None  # free-form cable-specific recipe parameters (JSON)


class RecipeUpdate(BaseModel):
    # partial update -- every field optional, only fields explicitly set are applied
    product_id: str | None = None
    process_id: str | None = None
    process_group_id: str | None = None
    recipe_scope: str | None = None
    setup_time: float | None = None
    speed: dict | None = None
    length_factor: dict | None = None
    cable_recipe: dict | None = None


class RecipeRead(BaseModel):
    # response shape returned to the client
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipe_id: str
    product_id: str | None
    process_id: str | None
    process_group_id: str | None
    recipe_scope: str
    setup_time: float | None
    speed: dict | None
    length_factor: dict | None
    cable_recipe: dict | None
    created_at: datetime
    updated_at: datetime
