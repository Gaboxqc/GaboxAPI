from typing import List
from fastapi import APIRouter, status, HTTPException, Query, Depends
from sqlmodel import select

from api.database import SessionDep
from api.portfolio.models import Category, CategoryBase
from api.security import validate_api_key

router = APIRouter()


@router.post("/categories", status_code=status.HTTP_201_CREATED, dependencies=[Depends(validate_api_key)])
async def create_category(category_data: CategoryBase, db: SessionDep):
    new_category = Category.model_validate(category_data.model_dump())
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    return new_category


@router.get("/categories", response_model=List[Category])
async def list_categories(db: SessionDep, offset: int = 0, limit: int = Query(default=10)):
    return db.exec(select(Category)).all()


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(validate_api_key)])
async def delete_category(category_id: int, db: SessionDep):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Category with id {category_id} not found")
    db.delete(category)
    db.commit()
    return None
