import asyncio
from telegram.bot import start_polling
import asyncio
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
import asyncio
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine
from infrastructure.db.session import Base  # adjust import to your Base
import subprocess
from watchfiles import watch


DATABASE_ADMIN_URL = "postgresql://fractal_user:fractal_pass@db:5432/postgres"
TEST_DB_NAME = "fractal_db"
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

async def main():
#    await recreate_test_db()
#    await create_tables()
#    await start_polling()
    print("No polling")

if __name__ == "__main__":
    asyncio.run(main())

