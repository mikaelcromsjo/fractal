# main.py
"""
Application entrypoint. Includes routers and mounts.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from routers import fractal_routers
from config.settings import settings
from mako.lookup import TemplateLookup
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Fractal Governance Backend")

STATIC_DIR = "/app/static"  # inside your Docker container

# make sure the folder exists
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Basic CORS (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# include routers
app.include_router(fractal_routers.router, prefix="/api/v1/fractals", tags=["fractals"])

@app.get("/")
async def index():
    """Health / basic info endpoint."""
    return {"status": "ok", "service": "fractal-backend", "env": settings.ENV}


