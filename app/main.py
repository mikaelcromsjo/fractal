# main.py
"""
Application entrypoint. Includes routers and mounts.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.telegram.bot import start_polling
import asyncio

#from app.api.routers import fractals, users, groups, proposals, comments, votes, admin
from app.config.settings import settings

app = FastAPI(title="Fractal Governance Backend")

# Basic CORS (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# include routers
#app.include_router(fractals.router, prefix="/api/v1/fractals", tags=["fractals"])

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_polling())

@app.get("/")
async def index():
    """Health / basic info endpoint."""
    return {"status": "ok", "service": "fractal-backend", "env": settings.ENV}
