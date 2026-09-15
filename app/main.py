# main.py
"""
Application entrypoint. Includes routers and mounts.
"""

import asyncpg
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional
import asyncio

from routers import fractal_routers
from config.settings import settings
from mako.lookup import TemplateLookup
from fastapi.staticfiles import StaticFiles
import os


from contextlib import asynccontextmanager
from telegram.bot import init_bot
from aiogram.types import BotCommand, MenuButtonCommands, BotCommandScopeAllPrivateChats

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
    await create_tables()

    print("🚀 Starting")
    bot, _ = init_bot()


    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(f"https://fractal.ia-ai.se/api/v1/fractals/webhook/{settings.bot_token}")

    # Private chat commands
    private_commands = [
        BotCommand(command="start", description="Show Menu"),
        BotCommand(command="help", description="Information"),
        BotCommand(command="dashboard", description="Fractal App"),
    ]

    # Set PRIVATE chat commands
    await bot.set_my_commands(
        private_commands,
        scope=BotCommandScopeAllPrivateChats()
    )
    print("✅ Bot menu commands set!")

    if getattr(app.state, "poller_started", False):
        print("⚠️ Poller already running. Skipping duplicate start.")
    else:
        app.state.poller_started = True
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

@app.get("/health")
async def health():
    """Health / basic info endpoint."""
    return {"status": "ok", "service": "fractal-backend", "env": settings.ENV}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Marketing landing page — links into /app (the standalone web app)."""
    template = fractal_routers.templates.get_template("landing.html")
    return HTMLResponse(template.render(request=request))


@app.get("/app", response_class=HTMLResponse)
async def web_app_entry(
    request: Request,
    fractal_id: Optional[str] = Query(None, description="Fractal id or name to join/view"),
):
    """Standalone (non-Telegram) web app entry point — same dashboard.html,
    rendered in web_mode so it authenticates via a browser-generated guest id
    instead of Telegram init_data."""
    template = fractal_routers.templates.get_template("dashboard.html")
    html = template.render(
        request=request,
        fractal_id=fractal_id,
        default_name="Guest",
        settings=settings,
        web_mode=True,
    )
    return HTMLResponse(html)


