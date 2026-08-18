from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeCreate, RecipeRead, RecipeUpdate

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _get_recipe_or_404(db: Session, recipe_id: str) -> Recipe:
    recipe = db.query(Recipe).filter_by(recipe_id=recipe_id).one_or_none()
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"recipe {recipe_id} not found")
    return recipe


@router.get("", response_model=list[RecipeRead])
def list_recipes(
    product_id: str | None = None, process_id: str | None = None, db: Session = Depends(get_db)
) -> list[Recipe]:
    query = db.query(Recipe)
    if product_id is not None:
        query = query.filter_by(product_id=product_id)
    if process_id is not None:
        query = query.filter_by(process_id=process_id)
    return query.order_by(Recipe.id).all()


@router.post("", response_model=RecipeRead, status_code=201)
def create_recipe(payload: RecipeCreate, db: Session = Depends(get_db)) -> Recipe:
    if db.query(Recipe).filter_by(recipe_id=payload.recipe_id).one_or_none():
        raise HTTPException(status_code=409, detail=f"recipe {payload.recipe_id} already exists")
    recipe = Recipe(**payload.model_dump())
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.get("/{recipe_id}", response_model=RecipeRead)
def get_recipe(recipe_id: str, db: Session = Depends(get_db)) -> Recipe:
    return _get_recipe_or_404(db, recipe_id)


@router.patch("/{recipe_id}", response_model=RecipeRead)
def update_recipe(recipe_id: str, payload: RecipeUpdate, db: Session = Depends(get_db)) -> Recipe:
    recipe = _get_recipe_or_404(db, recipe_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(recipe, field, value)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: str, db: Session = Depends(get_db)) -> None:
    recipe = _get_recipe_or_404(db, recipe_id)
    db.delete(recipe)
    db.commit()
