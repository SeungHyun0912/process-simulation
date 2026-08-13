from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RecipeCreate(BaseModel):
    recipe_id: str
    product_id: str | None = None
    process_id: str | None = None
    process_group_id: str | None = None
    recipe_scope: str = "equipment"
    setup_time: float | None = None
    speed: dict | None = None
    length_factor: dict | None = None
    cable_recipe: dict | None = None


class RecipeUpdate(BaseModel):
    product_id: str | None = None
    process_id: str | None = None
    process_group_id: str | None = None
    recipe_scope: str | None = None
    setup_time: float | None = None
    speed: dict | None = None
    length_factor: dict | None = None
    cable_recipe: dict | None = None


class RecipeRead(BaseModel):
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
