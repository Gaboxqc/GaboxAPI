import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.database import create_db_and_tables
from api.portfolio.routers import portfolio_router
from api.statpitch.routers import statpitch_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Gabox API",
    description=(
        "Centralized serverless backend for all my projects. "
        "Navigate to /docs for interactive documentation."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
        "https://gabrielmayorga.dev",
        "https://www.gabrielmayorga.dev",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio_router, prefix="/portfolio")
app.include_router(statpitch_router, prefix="/statpitch")


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "projects": {
            "portfolio": "/portfolio",
            "statpitch": "/statpitch",
        },
    }
