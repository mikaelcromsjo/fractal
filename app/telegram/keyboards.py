# telegram/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def vote_proposal_keyboard(proposal_id: int, comment_id: int | None = None):
    builder = InlineKeyboardBuilder()

    # 1–10 score buttons
    for i in range(1, 11):
        cb = f"vote:{proposal_id}:{comment_id or 0}:{i}"
        builder.button(text=str(i), callback_data=cb)

    builder.adjust(5, 5)  # two rows of 5

    return builder.as_markup()

def vote_comment_keyboard(proposal_id: int, comment_id: int | None = None):
    builder = InlineKeyboardBuilder()

    # Yes / No buttons
    builder.button(text="Yes", callback_data=f"vote:{proposal_id}:{comment_id or 0}:yes")
    builder.button(text="No", callback_data=f"vote:{proposal_id}:{comment_id or 0}:no")

    builder.adjust(5, 5, 2)  # optional second adjust to keep clean layout

    return builder.as_markup()


from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def list_more_keyboard(proposal_id: int, offset: int = 0):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Show more",
        callback_data=f"more:{proposal_id}:{offset}"
    )
    return builder.as_markup()


def show_hidden_keyboard(comment_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Show hidden comment",
        callback_data=f"showhidden:{comment_id}"
    )
    return builder.as_markup()

def proposal_card_keyboard(proposal_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(
        text="Vote",
        callback_data=f"open_vote:{proposal_id}"
    )

    builder.button(
        text="Show comments",
        callback_data=f"open_comments:{proposal_id}"
    )

    builder.adjust(1, 1)  # two rows, one button each (optional)

    return builder.as_markup()

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo



def default_menu():
    builder = InlineKeyboardBuilder()

    builder.button(text="✨ Create Fractal", callback_data="cmd:create_fractal")
    builder.button(text="❓ Help", callback_data="cmd:help")

    builder.adjust(1, 1, 1)
    return builder.as_markup()

def create_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(text="✨ Create Fractal", callback_data="cmd:create_fractal")

    builder.adjust(1, 1, 1)
    return builder.as_markup()



def fractal_created_menu(fractal_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(
        text=f"🙋 Join Fractal",
        callback_data=f"join:{fractal_id}"
    )
    builder.button(
        text=f"🚀 Start Fractal (Force)",
        callback_data=f"start_fractal:{fractal_id}"
    )

    builder.adjust(1, 1)
    return builder.as_markup()

from config.settings import settings

def fractal_actions_menu(fractal_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Open Fractal Dashboard",
                    web_app=WebAppInfo(url=f"{settings.public_base_url}/api/v1/fractals/dashboard?fractal_id={fractal_id}")
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Share Join Link",
                    switch_inline_query=f"Join fractal {fractal_id}: t.me/{settings.bot_username}?start=fractal_{fractal_id}"
                )
            ],
            [
                InlineKeyboardButton(text="📋 Copy Link", url=f"https://t.me/{settings.bot_username}?start=fractal_{fractal_id}")
            ]
        ]
    )


def cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data="cmd:cancel")
    return builder.as_markup()




