from typing import List
from fastapi import APIRouter, status, HTTPException, Query, Depends
from sqlmodel import select
from sqlalchemy.exc import IntegrityError

from api.database import SessionDep
from api.portfolio.models import Language, LanguageBase
from api.security import validate_api_key

router = APIRouter()


@router.post("/languages", response_model=Language, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(validate_api_key)])
async def create_language(language_data: LanguageBase, db: SessionDep):
    existing = db.get(Language, language_data.code)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Language code already exists.")

    new_language = Language.model_validate(language_data.model_dump())
    db.add(new_language)
    db.commit()
    db.refresh(new_language)
    return new_language


@router.get("/languages", response_model=List[Language])
async def list_languages(db: SessionDep, offset: int = 0, limit: int = Query(default=10)):
    return db.exec(select(Language)).all()


@router.delete("/languages/{code}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(validate_api_key)])
async def delete_language(code: str, db: SessionDep):
    language = db.get(Language, code)
    if not language:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Language '{code}' not found")

    try:
        db.delete(language)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete language because it is currently linked to active translations (RESTRICT constraint)."
        )
    return None
