from typing import List, Optional
from fastapi import APIRouter, status, HTTPException, Query, Depends
from sqlmodel import select

from api.database import SessionDep
from api.portfolio.models import CourseTranslation, CourseTranslationCreate, CourseTranslationUpdate
from api.security import validate_api_key

router = APIRouter()


@router.post("/course_translations", status_code=status.HTTP_201_CREATED, dependencies=[Depends(validate_api_key)])
async def create_course_translation(translation_data: CourseTranslationCreate, db: SessionDep):
    existing = db.exec(
        select(CourseTranslation).where(
            CourseTranslation.language_code == translation_data.language_code,
            CourseTranslation.course_id == translation_data.course_id
        )
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Translation for this course and language already exists.")

    new_translation = CourseTranslation.model_validate(translation_data.model_dump())
    db.add(new_translation)
    db.commit()
    db.refresh(new_translation)
    return new_translation


@router.get("/course_translations", response_model=List[CourseTranslation])
async def list_course_translations(db: SessionDep, offset: int = 0, limit: int = Query(default=10)):
    return db.exec(select(CourseTranslation).offset(offset).limit(limit)).all()


@router.get("/course_translations/{course_id}/{language_code}", response_model=CourseTranslation)
async def get_course_translation(course_id: int, language_code: str, db: SessionDep):
    translation = db.exec(
        select(CourseTranslation).where(
            CourseTranslation.course_id == course_id,
            CourseTranslation.language_code == language_code
        )
    ).first()
    if not translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Translation for course {course_id} in '{language_code}' not found")
    return translation


@router.patch("/course_translations/{course_id}/{language_code}", response_model=CourseTranslation,
              dependencies=[Depends(validate_api_key)])
async def update_course_translation(course_id: int, language_code: str, translation_data: CourseTranslationUpdate,
                                    db: SessionDep):
    translation = db.exec(
        select(CourseTranslation).where(
            CourseTranslation.course_id == course_id,
            CourseTranslation.language_code == language_code
        )
    ).first()
    if not translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Translation for course {course_id} in '{language_code}' not found")

    update_dic = translation_data.model_dump(exclude_unset=True)
    for key, value in update_dic.items():
        setattr(translation, key, value)

    db.add(translation)
    db.commit()
    db.refresh(translation)
    return translation


@router.delete("/course_translation/{course_id}/{language_code}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(validate_api_key)])
async def delete_course_translation(course_id: int, language_code: str, db: SessionDep):
    translation = db.exec(
        select(CourseTranslation).where(
            CourseTranslation.course_id == course_id,
            CourseTranslation.language_code == language_code
        )
    ).first()
    if not translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Translation for course {course_id} in '{language_code}' not found")
    db.delete(translation)
    db.commit()
    return None
