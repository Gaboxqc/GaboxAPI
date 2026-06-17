from typing import List
from fastapi import APIRouter, status, HTTPException, Depends
from sqlmodel import select

from api.portfolio.models import ProjectTranslation, ProjectTranslationCreate, ProjectTranslationUpdate
from api.database import SessionDep
from api.security import validate_api_key

router = APIRouter()

@router.post("/project_translations", response_model=ProjectTranslation, dependencies=[Depends(validate_api_key)])
async def create_project_translation(project_translation_data: ProjectTranslationCreate, db: SessionDep):
    new_project_translation = ProjectTranslation.model_validate(project_translation_data.model_dump())
    db.add(new_project_translation)
    db.commit()
    db.refresh(new_project_translation)
    return new_project_translation

@router.get("/project_translations", response_model=List[ProjectTranslation])
async def list_project_translation(db: SessionDep):
    return db.exec(select(ProjectTranslation)).all()

@router.get("/project_translations/{project_translation_id}", response_model=ProjectTranslation)
async def get_project_translation(project_translation_id: int, db:SessionDep):
    project_translation = db.get(ProjectTranslation, project_translation_id)
    if not project_translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Project Translation with id {project_translation_id} not found")
    return project_translation

@router.patch("/project_translations/{project_translation_id}", response_model=ProjectTranslation, dependencies=[Depends(validate_api_key)])
async def update_project_translation(project_translation_id: int, project_translation_data: ProjectTranslationUpdate,
                                     db: SessionDep):
    project_translation = db.get(ProjectTranslation, project_translation_id)
    if not project_translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Project Translation with id {project_translation_id} not found")
    update_dic = project_translation_data.model_dump(exclude_unset=True)
    for key, value in update_dic.items():
        setattr(project_translation, key, value)
    db.add(project_translation)
    db.commit()
    db.refresh(project_translation)
    return project_translation

@router.delete("/project_translations/{project_translation_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(validate_api_key)])
async def delete_project_translation(project_translation_id: int, db: SessionDep):
    project_translation = db.get(ProjectTranslation, project_translation_id)
    if not project_translation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Project Translation with id {project_translation_id} not found")
    db.delete(project_translation)
    db.commit()
    return None