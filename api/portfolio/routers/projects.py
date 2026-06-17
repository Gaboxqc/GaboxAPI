from typing import List, Optional
from fastapi import APIRouter, status, HTTPException, Query, Depends
from sqlalchemy.orm import selectinload
from sqlmodel import select

from api.database import SessionDep
from api.portfolio.models import Project, ProjectCreate, ProjectUpdate, ProjectTranslation, ProjectTag, Tag, \
    ProjectReadComplete
from api.security import validate_api_key

router = APIRouter()


@router.post("/projects", response_model=Project, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(validate_api_key)])
async def create_project(project_data: ProjectCreate, db: SessionDep):
    new_project = Project.model_validate(project_data.model_dump())
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project


@router.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: int, db: SessionDep):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project with id {project_id} not found")
    return project


@router.get("/projects", response_model=List[ProjectReadComplete])
def get_projects(
        db: SessionDep,
        is_main: Optional[bool] = Query(None, description="Filtrar solo proyectos destacados"),
        search: Optional[str] = Query(None, description="Buscar por título del proyecto"),
        project_type_id: List[int] = Query(default=[], description="Filtrar por Tipo de Proyecto"),
        difficulty_level_id: List[int] = Query(default=[], description="Filtrar por Nivel de Dificultad"),
        tag_id: List[int] = Query(default=[], description="Filtrar por ID de Tecnología (Tag)"),
        offset: int = 0,
        limit: int = Query(default=10, le=100),
):
    query = select(Project)

    if is_main is not None:
        query = query.where(Project.is_main == is_main)

    if search:
        query = query.where(
            Project.translations.any(ProjectTranslation.title.ilike(f"%{search}%"))
        )

    if project_type_id:
        query = query.where(Project.project_type_id.in_(project_type_id))

    if difficulty_level_id:
        query = query.where(Project.difficulty_level_id.in_(difficulty_level_id))

    if tag_id:
        query = query.where(Project.tags.any(Tag.id.in_(tag_id)))

    query = query.options(
        selectinload(Project.project_type),
        selectinload(Project.difficulty_level),
        selectinload(Project.tags),
        selectinload(Project.translations)
    )

    return db.exec(query.offset(offset).limit(limit)).all()


@router.patch("/projects/{project_id}", response_model=Project, dependencies=[Depends(validate_api_key)])
async def update_project(project_id: int, project_data: ProjectUpdate, db: SessionDep):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project with id {project_id} not found")
    update_dic = project_data.model_dump(exclude_unset=True)
    for key, value in update_dic.items():
        setattr(project, key, value)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(validate_api_key)])
async def delete_project(project_id: int, db: SessionDep):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project with id {project_id} not found")
    db.delete(project)
    db.commit()
    return None
