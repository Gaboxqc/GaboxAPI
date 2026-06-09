from fastapi import APIRouter

from .tags import router as tag_router
from .projects import router as project_router
from .project_translation import router as project_translation_router
from .academy import router as academy_router
from .course import router as course_router
from .certification import router as certification_router
from .category import router as category_router
from .certification_translation import router as certification_translation_router
from .course_translation import router as course_translation_router
from .difficulty_level import router as difficulty_level_router
from .language import router as language_router
from .project_type import router as project_type_router

portfolio_router = APIRouter()

portfolio_router.include_router(tag_router, tags=["Portfolio: Tags"])
portfolio_router.include_router(project_router, tags=["Portfolio: Project"])
portfolio_router.include_router(project_translation_router, tags=["Portfolio: Project Translation"])
portfolio_router.include_router(academy_router, tags=["Portfolio: Academy"])
portfolio_router.include_router(course_router, tags=["Portfolio: Course"])
portfolio_router.include_router(certification_router, tags=["Portfolio: Certification"])
portfolio_router.include_router(category_router, tags=["Portfolio: Category"])
portfolio_router.include_router(certification_translation_router, tags=["Portfolio: Certification Translation"])
portfolio_router.include_router(course_translation_router, tags=["Portfolio: Course Translation"])
portfolio_router.include_router(difficulty_level_router, tags=["Portfolio: Difficulty Level"])
portfolio_router.include_router(language_router, tags=["Portfolio: Language"])
portfolio_router.include_router(project_type_router, tags=["Portfolio: Project Type"])
