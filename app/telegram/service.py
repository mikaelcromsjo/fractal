# telegram/service.py

from aiogram import Bot
from typing import Iterable
from sqlalchemy import select
from config.settings import settings
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

bot = Bot(token=settings.bot_token)

async def send_message_to_telegram_users(telegram_ids: list[int], text: str):
    for user_id in telegram_ids:
        if(int(user_id)>=20000 and int(user_id)<300000):
            continue
        try:
            print("Sending message to telegram")
            await bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            print(f"Failed to send to {user_id}: {e}")


async def send_button_to_telegram_users(
    telegram_ids: Iterable[int],
    text: str,
    button: str,
    fractal_id: int,
    data: int,
) -> None:
    
    if (button=="Dashboard"):
        url = f"{settings.public_base_url}/api/v1/fractals/dashboard?fractal_id={fractal_id}"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="🚀 Open Dashboard",
                    web_app=WebAppInfo(url=url),
                )
            ]]
        )

        for user_id in telegram_ids:
            if(int(user_id)>=20000 and int(user_id)<300000): # test users
                continue

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                )
                print("message sent to ", user_id)

            except Exception as e:
                print(f"Failed to send to {user_id}: {e}")
    else:

        for user_id in telegram_ids:
            if(int(user_id)>=20000 and int(user_id)<300000): # test users
                continue

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                )

            except Exception as e:
                print(f"Failed to send to {user_id}: {e}")
