# main.py
"""
Application entrypoint. Includes routers and mounts.
"""

import asyncpg
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
from infrastructure.db.session import AsyncSessionLocal

from sqlalchemy.ext.asyncio import create_async_engine
from infrastructure.db.session import Base  # adjust import to your Base


DATABASE_ADMIN_URL = "postgresql://fractal_user:fractal_pass@db:5432/postgres"
TEST_DB_NAME = "test_fractal_db"
DATABASE_URL = f"postgresql+asyncpg://fractal_user:fractal_pass@db:5432/{TEST_DB_NAME}"


async def recreate_test_db():
    conn = await asyncpg.connect(DATABASE_ADMIN_URL)
    # Terminate connections to the test DB
    await conn.execute(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid();
    """)
    # Drop and create DB
    await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")
    await conn.execute(f"CREATE DATABASE {TEST_DB_NAME};")
    await conn.close()
    print(f"Database '{TEST_DB_NAME}' recreated successfully.")


async def create_tables():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        print("Creating all tables...")
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Tables created successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):


#    await recreate_test_db()
#    await create_tables()

    print("🚀 Starting")
    bot, _ = init_bot()

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook("https://fractal.ia-ai.se/api/v1/fractals/webhook")

    commands = [
        BotCommand(command="start", description="Show menu"),
        BotCommand(command="help", description="Help"),
        BotCommand(command="join", description="Join fractal id (/join 12)"),
    ]
    await bot.set_my_commands(commands)
    print("✅ Bot menu commands set!")

    # Start poller with sessionmaker factory
    poll_task = asyncio.create_task(poll_worker(AsyncSessionLocal, poll_interval=60))
    print("🌀 Poll worker started in background.")

    try:
        yield
    finally:
        print("🛑 Shutting down bot...")
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
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


