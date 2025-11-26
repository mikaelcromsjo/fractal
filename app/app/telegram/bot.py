import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from app.config.settings import settings
from app.telegram.handlers.fractal import router as fractal_router
from app.telegram.handlers.proposals import router as proposal_router
from app.telegram.callbacks import router as callback_router

bot: Bot | None = None
dp: Dispatcher | None = None


def get_bot_and_dispatcher():
    global bot, dp
    if bot is None:
        bot = Bot(token=settings.bot_token, parse_mode="HTML")
    if dp is None:
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        # register routers
        dp.include_router(fractal_router)
        dp.include_router(proposal_router)
        dp.include_router(callback_router)
    return bot, dp


async def start_polling():
    b, dispatcher = get_bot_and_dispatcher()
    # start long-polling (blocks until cancelled)
    try:
        await dispatcher.start_polling(bot=b)
    finally:
        await b.session.close()
