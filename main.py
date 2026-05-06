from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.project_one.router import router as project_one_router

app = FastAPI(
    title="Gabox API",
    description="A centralized serverless backend for all my portfolio projects.",
    version="1.0.0"
)

# 1. Configure CORS
# In production, replace "*" with your specific frontend domains for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Include Project Routers
app.include_router(project_one_router, prefix="/api")

# 3. Global Root Endpoint
@app.get("/")
async def global_root():
    return {
        "status": "online",
        "message": "Welcome to the Gabox API. Navigate to /docs for interactive documentation."
    }