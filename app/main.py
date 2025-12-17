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


from contextlib import asynccontextmanager
from telegram.bot import init_bot
from aiogram.types import BotCommand, MenuButtonCommands

from services.fractal_service import poll_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    print("🚀 Starting bot...")
    bot, _ = init_bot()

    commands = [
        BotCommand(command="start", description="Show menu"),
        BotCommand(command="help", description="Help"),
        BotCommand(command="join", description="Join fractal id (/join 12)"),
    ]
    await bot.set_my_commands(commands)
    print("✅ Bot menu commands set!")

    # --- Start poll worker ---
    async def start_poller():
        from infrastructure.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await poll_worker(db, poll_interval=60)

    # Run poller in background
    asyncio.create_task(start_poller())
    print("🌀 Poll worker started in background.")

    yield  # --- App runs here (FastAPI lifecycle main body runs) ---

    # --- Shutdown ---
    print("🛑 Shutting down bot...")
    await bot.session.close()
    print("✅ Bot shutdown complete.")


# Apply lifespan to your app
app = FastAPI(lifespan=lifespan)

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


