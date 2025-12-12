# telegram/bot.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config.settings import settings
from telegram.handlers.fractal_telegram import router as fractal_router

from aiogram import Bot, Dispatcher
from aiogram.types import Update

bot: Bot | None = None
dp: Dispatcher | None = None

def init_bot():
    global bot, dp
    if bot is None or dp is None:
        bot, dp = get_bot_and_dispatcher()
    return bot, dp

async def process_update(update_dict: dict):
    """Kallas från FastAPI-webhookroute."""
    bot, dp = init_bot()
    update = Update.model_validate(update_dict)
    await dp.feed_update(bot, update)

def get_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    """Create Bot and Dispatcher (with routers)."""
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())  # do not bind bot here
    dp.include_router(fractal_router)
#    dp.include_router(proposal_router)
#    dp.include_router(callback_router)
    return bot, dp

async def start_polling():
    """Start Aiogram long-polling."""
    bot, dp = get_bot_and_dispatcher()
    print("Bot created. Username:", (await bot.get_me()).username)


    print("Starting polling...")
    try:
        await dp.start_polling(bot)  # pass bot explicitly
    except Exception as e:
        print("Polling error:", e)
    finally:
        await bot.session.close()
        print("Bot stopped.")
