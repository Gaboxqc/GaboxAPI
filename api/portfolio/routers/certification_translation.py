from typing import List, Optional
from fastapi import APIRouter, status, HTTPException, Query, Depends
from sqlmodel import select

from api.database import SessionDep
from api.portfolio.models import CertificationTranslation, CertificationTranslationCreate, \
    CertificationTranslationUpdate
from api.security import validate_api_key

router = APIRouter()


@router.post("/certification_translations", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(validate_api_key)])
async def create_certification_translation(translation_data: CertificationTranslationCreate, db: SessionDep):
    existing = db.exec(
        select(CertificationTranslation).where(
            CertificationTranslation.language_code == translation_data.language_code,
            CertificationTranslation.certification_id == translation_data.certification_id
        )
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Translation for this certification and language already exists.")

    new_translation = CertificationTranslation.model_validate(translation_data.model_dump())
    db.add(new_translation)
    db.commit()
    db.refresh(new_translation)
    return new_translation


@router.get("/certification_translations", response_model=List[CertificationTranslation])
async def list_certification_translations(db: SessionDep, offset: int = 0, limit: int = Query(default=10)):
    return db.exec(select(CertificationTranslation).offset(offset).limit(limit)).all()


@router.get("/certification_translations/{certification_id}/{language_code}", response_model=CertificationTranslation)
async def get_certification_translation(certification_id: int, language_code: str, db: SessionDep):
    translation = db.exec(
        select(CertificationTranslation).where(
            CertificationTranslation.certification_id == certification_id,
            CertificationTranslation.language_code == language_code
        )
    ).first()
    if not translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Translation for certification {certification_id} in '{language_code}' not found")
    return translation


@router.patch("/certification_translations/{certification_id}/{language_code}", response_model=CertificationTranslation,
              dependencies=[Depends(validate_api_key)])
async def update_certification_translation(certification_id: int, language_code: str,
                                           translation_data: CertificationTranslationUpdate, db: SessionDep):
    translation = db.exec(
        select(CertificationTranslation).where(
            CertificationTranslation.certification_id == certification_id,
            CertificationTranslation.language_code == language_code
        )
    ).first()
    if not translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Translation for certification {certification_id} in '{language_code}' not found")

    update_dic = translation_data.model_dump(exclude_unset=True)
    for key, value in update_dic.items():
        setattr(translation, key, value)

    db.add(translation)
    db.commit()
    db.refresh(translation)
    return translation


@router.delete("/certification_translations/{certification_id}/{language_code}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(validate_api_key)])
async def delete_certification_translation(certification_id: int, language_code: str, db: SessionDep):
    translation = db.exec(
        select(CertificationTranslation).where(
            CertificationTranslation.certification_id == certification_id,
            CertificationTranslation.language_code == language_code
        )
    ).first()
    if not translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Translation for certification {certification_id} in '{language_code}' not found")
    db.delete(translation)
    db.commit()
    return None
