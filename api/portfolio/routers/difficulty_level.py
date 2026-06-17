from typing import List
from fastapi import APIRouter, status, HTTPException, Query, Depends
from sqlmodel import select

from api.database import SessionDep
from api.portfolio.models import DifficultyLevel, DifficultyLevelBase
from api.security import validate_api_key

router = APIRouter()


@router.post("/difficulty_levels", status_code=status.HTTP_201_CREATED, dependencies=[Depends(validate_api_key)])
async def create_difficulty_level(level_data: DifficultyLevelBase, db: SessionDep):
    new_level = DifficultyLevel.model_validate(level_data.model_dump())
    db.add(new_level)
    db.commit()
    db.refresh(new_level)
    return new_level


@router.get("/difficulty_levels", response_model=List[DifficultyLevel])
async def list_difficulty_levels(db: SessionDep, offset: int = 0, limit: int = Query(default=10)):
    return db.exec(select(DifficultyLevel).offset(offset).limit(limit)).all()


@router.delete("/difficulty_levels/{level_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(validate_api_key)])
async def delete_difficulty_level(level_id: int, db: SessionDep):
    level = db.get(DifficultyLevel, level_id)
    if not level:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Difficulty Level with id {level_id} not found")
    db.delete(level)
    db.commit()
    return None
