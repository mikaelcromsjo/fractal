# telegram/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config.settings import settings


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

    builder.adjust(2)  # 2 buttons per row

    return builder.as_markup()


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

    builder.adjust(1, 1)  # two rows, one button each

    return builder.as_markup()


def help_menu():
    builder = InlineKeyboardBuilder()

    builder.button(text="✨ Create Fractal", callback_data="cmd:create_fractal")

    builder.adjust(1)
    return builder.as_markup()


def create_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(text="✨ Create Fractal", callback_data="cmd:create_fractal")

    builder.adjust(1)
    return builder.as_markup()


def fractal_created_menu(fractal_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🙋 Join Fractal",
        callback_data=f"join:{fractal_id}"
    )
    builder.button(
        text="🚀 Start Fractal (Force)",
        callback_data=f"start_fractal:{fractal_id}"
    )

    builder.adjust(1, 1)
    return builder.as_markup()


def share_to_group_button(fractal_id: int) -> InlineKeyboardMarkup:
    """Button shown in private chat with Join + Share options."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🙋 Join Fractal",
                    callback_data=f"join:{fractal_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Share to Group",
                    switch_inline_query=f"share fractal_{fractal_id}"
                )
            ]
        ]
    )


def fractal_actions_menu(fractal_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Share Join Link",
                    switch_inline_query=f"Join fractal {fractal_id}: t.me/{settings.bot_username}?start=fractal_{fractal_id}"
                )
            ],
            [
                InlineKeyboardButton(text="📋 Join fractal", url=f"https://t.me/{settings.bot_username}?start=fractal_{fractal_id}")
            ]
        ]
    )


def timezone_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇸🇪 Sweden (CET)", callback_data="tz_cet")],
        [InlineKeyboardButton(text="🇫🇮 Finland (EET)", callback_data="tz_eet")],
        [InlineKeyboardButton(text="🇬🇧 UK (GMT)", callback_data="tz_gmt")],
        [InlineKeyboardButton(text="🇺🇸 NY (EST)", callback_data="tz_est")],
        [InlineKeyboardButton(text="🇺🇸 LA (PST)", callback_data="tz_pst")],
        [InlineKeyboardButton(text="➕ Other", callback_data="tz_manual")],
        [InlineKeyboardButton(text="Cancel", callback_data="cancel")]
    ])


def default_menu(type=""):
    """
    Create default menu based on chat type.
    - Private: Show Dashboard + Help
    - Public/Group: Show Bot link + Help
    """
    if type == "private":
        builder = InlineKeyboardBuilder()

        # Button 1: Open Telegram Web App dashboard
        builder.button(
            text="🚀 Open Dashboard",
            web_app=WebAppInfo(
                url=f"{settings.public_base_url}/api/v1/fractals/dashboard"
            )
        )

        # Button 2: Show help menu via callback
        builder.button(
            text="ℹ️ Get more information",
            callback_data="cmd:help"
        )

        builder.adjust(1, 1)

        return builder.as_markup()
    else:
        # PUBLIC GROUP/CHANNEL: Show bot link + help
        builder = InlineKeyboardBuilder()
        
        # Button: Open private chat with bot
        builder.button(
            text="💬 Fractal Circle Bot",
            url=f"https://t.me/{settings.bot_username}"
        )
        
        # Help via callback (works in groups!)
        builder.button(
            text="ℹ️ Information",
            callback_data="cmd:help"
        )
        builder.adjust(1)
        return builder.as_markup()


def cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data="cmd:cancel")
    return builder.as_markup()