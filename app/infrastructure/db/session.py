# telegram/repositories/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import settings
from sqlalchemy import text 

Base = declarative_base()

# Use DATABASE_URL from settings
#engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False, 
    future=True,
    pool_pre_ping=True,      # ✅ Validates connections
    pool_recycle=300,        # ✅ Kills idle connections
    pool_size=10,            # ✅ Limit connections
    max_overflow=20
)

# Async session factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Async context manager for a session
async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        # ✅ Health check before yield
        await session.execute(text("SELECT 1"))
        yield session