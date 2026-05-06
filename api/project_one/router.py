from fastapi import APIRouter

# We add a tag so this project has its own distinct section in the /docs page
router = APIRouter(prefix="/project-one", tags=["Project One - Test"])

@router.get("/")
async def get_project_one_root():
    return {"message": "Welcome to the GaboxAPI!"}