from typing import List
from fastapi import APIRouter, status, HTTPException, Query, Depends
from sqlmodel import select

from api.database import SessionDep
from api.portfolio.models import ProjectType, ProjectTypeBase
from api.security import validate_api_key

router = APIRouter()


@router.post("/project_types", status_code=status.HTTP_201_CREATED, dependencies=[Depends(validate_api_key)])
async def create_project_type(type_data: ProjectTypeBase, db: SessionDep):
    new_type = ProjectType.model_validate(type_data.model_dump())
    db.add(new_type)
    db.commit()
    db.refresh(new_type)
    return new_type


@router.get("/project_types", response_model=List[ProjectType])
async def list_project_types(db: SessionDep, offset: int = 0, limit: int = Query(default=10)):
    return db.exec(select(ProjectType).offset(offset).limit(limit)).all()


@router.delete("/project_types/{type_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(validate_api_key)])
async def delete_project_type(type_id: int, db: SessionDep):
    project_type = db.get(ProjectType, type_id)
    if not project_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project Type with id {type_id} not found")
    db.delete(project_type)
    db.commit()
    return None
