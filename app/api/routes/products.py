from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])


def _get_product_or_404(db: Session, product_id: str) -> Product:
    product = db.query(Product).filter_by(product_id=product_id).one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    status: str | None = None,
    product_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[Product]:
    query = db.query(Product)
    if status is not None:
        query = query.filter_by(status=status)
    if product_type is not None:
        query = query.filter_by(product_type=product_type)
    return query.order_by(Product.id).all()


@router.post("", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    existing = db.query(Product).filter_by(product_id=payload.product_id).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"product {payload.product_id} already exists")

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: str, db: Session = Depends(get_db)) -> Product:
    return _get_product_or_404(db, product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: str, payload: ProductUpdate, db: Session = Depends(get_db)
) -> Product:
    product = _get_product_or_404(db, product_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", response_model=ProductRead)
def deactivate_product(product_id: str, db: Session = Depends(get_db)) -> Product:
    """Soft delete: mark inactive rather than hard-deleting the row (see docs/planning/04-rdb-design.md)."""
    product = _get_product_or_404(db, product_id)
    product.status = "inactive"
    db.commit()
    db.refresh(product)
    return product
