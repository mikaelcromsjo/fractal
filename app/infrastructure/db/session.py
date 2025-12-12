# telegram/repositories/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import settings

Base = declarative_base()

# Use DATABASE_URL from settings
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

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
        yield session
