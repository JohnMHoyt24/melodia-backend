from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import artists, health, search
from app.core.config import get_settings

app = FastAPI(title="Melodia API")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(artists.router)
app.include_router(search.router)
