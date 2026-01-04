# telegram/handlers/fractal_telegram.py
"""
Complete fixed Telegram bot handler for Fractal Circle bot.
All text sanitization and MarkdownV2 escaping properly applied.
"""

import logging
from datetime import datetime, timedelta, timezone
import re
from typing import Optional, Dict, Any, Union
from aiogram import types, Router, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode, ChatType
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Message,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    BotCommand, MenuButtonCommands
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config.settings import settings
from zoneinfo import ZoneInfo
from html import escape

from infrastructure.db.session import get_async_session
from telegram.service import send_message_to_telegram_users, send_button_to_telegram_users
from telegram.keyboards import (
    timezone_keyboard, share_to_group_button, create_keyboard,
    vote_comment_keyboard, vote_proposal_keyboard, list_more_keyboard,
    show_hidden_keyboard, cancel_keyboard, fractal_actions_menu,
    help_menu, default_menu
)
from telegram.states import ProposalStates, CreateFractal
from services.fractal_service import (
    create_fractal, join_fractal, start_fractal, close_round,
    get_fractal_from_name_or_id_repo, send_message_to_group,
    get_group_members_repo, get_user, create_proposal, create_comment,
    vote_proposal, vote_comment, vote_representative_repo,
    get_proposals_comments_tree, get_proposal_comments_tree,
    get_user_by_telegram_id, get_user_info_by_telegram_id
)

logger = logging.getLogger(__name__)
router = Router()


# =====================
# UTILITY FUNCTIONS
# =====================

def escape_markdown_v2(text: str) -> str:
    """
    Escapes special characters for Telegram MarkdownV2 parse mode.
    These characters MUST be escaped: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    if text is None:
        return ""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    escaped = ''.join('\\' + char if char in special_chars else char for char in text)
    return escaped


def format_international_times(start_date: str, round_time: int) -> str:
    """Format start time across multiple timezones."""
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    
    times = {
        '🇪🇺 CET': start_dt.astimezone(ZoneInfo('Europe/Berlin')).strftime('%H:%M'),
        '🇫🇮 EET': start_dt.strftime('%H:%M'),
        '🇬🇧 GMT': start_dt.astimezone(ZoneInfo('Europe/London')).strftime('%H:%M'),
        '🇺🇸 EST': start_dt.astimezone(ZoneInfo('America/New_York')).strftime('%H:%M'),
        '🇺🇸 PST': start_dt.astimezone(ZoneInfo('America/Los_Angeles')).strftime('%H:%M'),
        '🇧🇷 BRT': start_dt.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M'),
        '🇮🇳 IST': start_dt.astimezone(ZoneInfo('Asia/Kolkata')).strftime('%H:%M'),
        '🇯🇵 JST': start_dt.astimezone(ZoneInfo('Asia/Tokyo')).strftime('%H:%M'),
        '🇦🇺 AEST': start_dt.astimezone(ZoneInfo('Australia/Sydney')).strftime('%H:%M'),
    }
    
    time_lines = [f"{flag}: {time}" for flag, time in times.items()]
    result = ' '.join(time_lines[:9])
    # Return unescaped - caller will escape if using MarkdownV2
    return result


async def parse_start_date(state: FSMContext, s: str) -> Optional[datetime]:
    """Parse user input for start date (relative minutes or absolute YYYYMMDDHHMM)."""
    s = s.strip()
    data = await state.get_data()
    user_tz_offset = data.get('user_tz_offset', 0)
    
    try:
        if re.match(r'^\d{1,4}$', s):
            # Relative: minutes from now
            minutes = int(s)
            utc_now = datetime.now(timezone.utc)
            user_local_now = utc_now + timedelta(hours=user_tz_offset)
            user_future_local = user_local_now + timedelta(minutes=minutes)
            utc_for_db = user_future_local - timedelta(hours=user_tz_offset)
            return utc_for_db
        
        if re.match(r'^\d{12}$', s):
            # Absolute: YYYYMMDDHHMM format
            user_time = datetime.strptime(s, "%Y%m%d%H%M")
            utc_time = user_time.replace(tzinfo=timezone.utc) - timedelta(hours=user_tz_offset)
            return utc_time
    except Exception as e:
        logger.error(f"Failed to parse start date: {e}")
    
    return None


async def get_user_info(telegram_id: str) -> Dict:
    """Fetch user info from database."""
    async for db in get_async_session():
        try:
            user_info = await get_user_info_by_telegram_id(db, str(telegram_id))
            return user_info or {}
        except Exception as e:
            logger.exception(f"Failed getting user data for {telegram_id}")
            return {}


# =====================
# INLINE QUERY (Share)
# =====================

@router.inline_query()
async def handle_inline_share(query: InlineQuery):
    """Share fractal to groups via inline query."""
    q = query.query.strip()
    
    if not q.startswith("share fractal_"):
        return
    
    try:
        fractal_id = int(q.split("_", 1)[1])
    except (ValueError, IndexError):
        return
    
    async for db in get_async_session():
        try:
            fractal = await get_fractal_from_name_or_id_repo(
                db=db, fractal_identifier=str(fractal_id)
            )
            
            if not fractal or fractal.status.lower() != "waiting":
                return
            
            now = datetime.now(timezone.utc)
            if fractal.start_date < now:
                return
            
            # Build message text with proper escaping
            escaped_name = escape_markdown_v2(fractal.name or "Fractal")
            escaped_desc = escape_markdown_v2(fractal.description or "")
            start_date = fractal.start_date.strftime("%A, %B %d, %Y") if fractal.start_date else "Unknown"
            
            minutes = int(fractal.meta.get("round_time", 0))
            times_str = format_international_times(fractal.start_date.isoformat(), minutes)
            escaped_times = escape_markdown_v2(times_str)
            
            share_text = (
                f"🎉 *Click to Join Fractal Meeting*\n\n"
                f"🚀 {escaped_name}\n\n"
                f"📝 {escaped_desc}\n\n"
                f"📅 {start_date}\n\n"
                f"{escaped_times}\n\n"
                f"🔄 {minutes} minutes per round\n\n"
                f"⚡️ Share this link https://t.me/{settings.bot_username}?start=fractal_{fractal_id}"
            )
            
            join_button = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(
                    text="🚀 Join Fractal",
                    url=f"https://t.me/{settings.bot_username}?start=fractal_{fractal_id}"
                )]]
            )
            
            await query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=f"share_{fractal_id}",
                        title="Share Fractal to Group",
                        description="Send a join button to your group",
                        input_message_content=InputTextMessageContent(
                            message_text=share_text,
                            parse_mode="MarkdownV2",
                        ),
                        reply_markup=join_button,
                    )
                ],
                cache_time=0,
                is_personal=True,
            )
            break
        except Exception as e:
            logger.exception(f"Failed to process inline share for fractal {fractal_id}: {e}")
            break


# =====================
# CALLBACKS
# =====================

@router.callback_query(F.data == "tz_manual")
async def handle_manual_tz(callback: types.CallbackQuery, state: FSMContext):
    """Handle manual timezone offset input."""
    await callback.message.edit_text(
        "⌨️ *Enter UTC offset*:\n\n"
        "🇪🇺 `+1` CET\n🇫🇮 `+2` EET\n🇬🇧 `0` GMT\n"
        "🇺🇸 `-5` EST\n🇺🇸 `-8` PST\n🇧🇷 `-3` BRT\n"
        "🇮🇳 `+5\\.5` IST\n🇯🇵 `+9` JST\n🇦🇺 `+10` AEST\n"
        "🇨🇳 `+8` China\n🇷🇺 `+3` Moscow\n🇿🇦 `+2` South Africa\n"
        "🇲🇽 `-6` Mexico\n🇦🇷 `-3` Argentina\n🇸🇬 `+8` Singapore\n\n"
        "_Examples: `+3\\.5`, `-4\\.5`, `+11\\.5`_",
        parse_mode="MarkdownV2",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.timezone_manual)
    await callback.answer()


@router.message(CreateFractal.timezone_manual)
async def handle_manual_offset(message: types.Message, state: FSMContext):
    """Process manual timezone offset."""
    try:
        offset = float(message.text.strip())
        await state.update_data(user_tz_offset=offset)
        await message.answer(
            f"✅ *Offset {offset:+\\.1f}h* set! Now enter start time:\n"
            "• `30` = 30 min from now\n"
            "• `202601011700` = exact time",
            parse_mode="MarkdownV2",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(CreateFractal.start_date)
    except ValueError:
        await message.answer(
            "❌ Invalid offset\\. Use `+2` or `-5`\\. Try again:",
            parse_mode="MarkdownV2"
        )


@router.callback_query(F.data.startswith("tz_"))
async def handle_timezone(callback: types.CallbackQuery, state: FSMContext):
    """Handle timezone selection from keyboard."""
    tz_map = {
        "tz_cet": 1.0,
        "tz_eet": 2.0,
        "tz_gmt": 0.0,
        "tz_est": -5.0,
        "tz_pst": -8.0,
    }
    
    callback_data = callback.data
    offset = tz_map.get(callback_data.split(":")[0] if ":" in callback_data else callback_data, 0.0)
    
    await state.update_data(user_tz_offset=offset)
    
    await callback.message.edit_text(
        f"✅ TZ set\\! *UTC {offset:+g}* Enter start time:\n"
        "• `30` = 30 min from now\n"
        "• `202701011700` = Jan 1st 17:00 \\(*your local time*\\)",
        parse_mode="MarkdownV2"
    )
    await state.set_state(CreateFractal.start_date)
    await callback.answer()


@router.callback_query(F.data == "cmd:help")
async def cb_help(callback: types.CallbackQuery):
    """Handle help button from keyboard."""
    await callback.answer()
    await cmd_help(callback.message)


@router.callback_query(F.data.startswith("join:"))
async def cb_join(callback: types.CallbackQuery, state: FSMContext):
    """Handle join button from keyboard."""
    await callback.answer()
    
    try:
        fractal_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.message.answer("❌ Invalid fractal ID\\.")
        return
    
    await cmd_join(
        callback.message,
        state=state,
        fractal_id=fractal_id,
        user_id=str(callback.from_user.id),
        username=getattr(callback.from_user, "username", "")
    )


@router.callback_query(F.data.startswith("start_fractal:"))
async def cb_start_fractal(callback: types.CallbackQuery, state: FSMContext):
    """Handle start fractal button from keyboard."""
    await callback.answer()
    
    try:
        fractal_id = callback.data.split(":", 1)[1]
    except IndexError:
        await callback.message.answer("❌ Invalid fractal ID\\.")
        return
    
    await cmd_start_fractal(callback.message, fractal_id=fractal_id, state=state)


@router.callback_query(F.data == "cmd:create_fractal")
async def cb_start_create_fractal(callback: types.CallbackQuery, state: FSMContext):
    """Handle create fractal button from keyboard."""
    await callback.answer()
    await callback.message.answer(
        "📝 Please enter name of the meeting:",
        parse_mode="MarkdownV2",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.name)


@router.callback_query(F.data.startswith("proposal:"))
async def cb_proposal_button(callback: types.CallbackQuery, state: FSMContext):
    """Handle proposal button from keyboard."""
    await callback.answer()
    
    try:
        fractal_id = callback.data.split(":", 1)[1]
    except IndexError:
        return
    
    await state.update_data(
        telegram_id=str(callback.from_user.id),
        fractal_id=fractal_id,
        body=""
    )
    
    await cmd_proposal_start(callback.message, state)


@router.callback_query(F.data == "cmd:cancel")
async def cb_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Handle cancel button from keyboard."""
    await callback.answer()
    await state.clear()
    
    chat_type = "private" if callback.message.chat.type == ChatType.PRIVATE else "group"
    await callback.message.answer(
        "❌ Operation canceled\\.",
        reply_markup=default_menu(chat_type)
    )


# =====================
# COMMANDS
# =====================

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """Handle /start command."""
    from telegram.bot import init_bot
    bot, _ = init_bot()
    
    # Set commands
    commands = [
        BotCommand(command="start", description="Start Menu"),
        BotCommand(command="help", description="Information"),
        BotCommand(command="dashboard", description="Dashboard"),
    ]
    await bot.set_my_commands(commands)
    
    if message.chat.type == ChatType.PRIVATE:
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonCommands()
        )
    
    # Check for fractal_id argument
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1 and args[1].startswith("fractal_"):
        try:
            fractal_id = int(args[1].replace("fractal_", ""))
        except ValueError:
            await message.answer("❌ Invalid fractal ID\\.")
            return
        
        async for db in get_async_session():
            try:
                fractal = await get_fractal_from_name_or_id_repo(
                    db=db,
                    fractal_identifier=str(fractal_id)
                )
                
                if not fractal:
                    await message.answer(
                        f"❌ Fractal *{escape_markdown_v2(str(fractal_id))}* not found or not created yet\\.\n\n"
                        f"ℹ️ It may have been deleted or never initialized properly\\.",
                        parse_mode="MarkdownV2",
                    )
                    break
                
                # Check if fractal is still joinable
                if fractal.status.lower() != "waiting":
                    escaped_name = escape_markdown_v2(fractal.name or "Fractal")
                    escaped_desc = escape_markdown_v2(fractal.description or "")
                    start_date = fractal.start_date.strftime("%A %H:%M, %B %d, %Y") if fractal.start_date else "Unknown"
                    minutes = int(fractal.meta.get("round_time", 0))
                    times_str = format_international_times(fractal.start_date.isoformat(), minutes)
                    escaped_times = escape_markdown_v2(times_str)
                    
                    await message.answer(
                        f"❌ *The Fractal is not open to join*\n\n"
                        f"🚀 {escaped_name}\n\n"
                        f"📝 {escaped_desc}\n\n"
                        f"📅 {start_date}\n"
                        f"{escaped_times}\n\n"
                        f"🔄 {minutes} minutes rounds",
                        parse_mode="MarkdownV2"
                    )
                    break
                
                # Show join menu
                builder = InlineKeyboardBuilder()
                builder.button(text="🙋 Join Fractal", callback_data=f"join:{fractal.id}")
                button = builder.as_markup()
                
                escaped_name = escape_markdown_v2(fractal.name or "Fractal")
                escaped_desc = escape_markdown_v2(fractal.description or "")
                start_date = fractal.start_date.strftime("%A, %B %d, %Y") if fractal.start_date else "Unknown"
                minutes = int(fractal.meta.get("round_time", 0))
                times_str = format_international_times(fractal.start_date.isoformat(), minutes)
                escaped_times = escape_markdown_v2(times_str)
                
                await message.answer(
                    f"🎉 *Click to Join Fractal Meeting*\n\n"
                    f"🚀 {escaped_name}\n\n"
                    f"📝 {escaped_desc}\n\n"
                    f"📅 {start_date}\n\n"
                    f"{escaped_times}\n\n"
                    f"🔄 {minutes} minutes rounds\n\n"
                    f"⚡️ Share this link https://t.me/{settings.bot_username}?start=fractal_{fractal_id}",
                    reply_markup=button,
                    parse_mode="MarkdownV2"
                )
                break
            except Exception as e:
                logger.exception(f"Error loading fractal {fractal_id}")
                await message.answer("❌ Error loading fractal\\.")
                break
        
        return
    
    # Default /start message
    chat_type = "private" if message.chat.type == ChatType.PRIVATE else "group"
    await message.answer(
        "👋 Hi, I am the Fractal Circle Bot\\!",
        reply_markup=default_menu(chat_type)
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Display help information."""
    help_text = (
        "🤖 *Fractal Circle Bot* helps you organize fractal meetings in large groups\\.\n\n"
        "💌 In most cases, you'll be invited to join a fractal meeting that someone else created\\. "
        "You'll receive an invite link when that happens\\.\n\n"
        "🧩 If you're a group organizer, you can also create your own fractal and invite others to join\\. \n\n"
        "🎯 A Fractal meeting is divided into separate rounds in which breakout groups create proposals, "
        "discuss them, and vote on them\\. Most participants attend only one round; only the selected "
        "representatives continue to the next round\\. Collaborate, connect, and grow your circle\\!\n\n"
        "Read more on https://FractalCircles\\.org"
    )
    await message.answer(help_text, reply_markup=help_menu(), parse_mode="MarkdownV2")


@router.message(Command("dashboard"))
async def dashboard_command(message: types.Message):
    """Show dashboard command."""
    if message.chat.type == ChatType.PRIVATE:
        dashboard_url = f"{settings.public_base_url}/api/v1/fractals/dashboard"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(
                text="🚀 Open Dashboard",
                web_app=WebAppInfo(url=dashboard_url),
            )]]
        )
        text = "🚀 *Open your Fractal Dashboard:*"
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(
                text="💬 Open Dashboard in private chat",
                url=f"https://t.me/{settings.bot_username}?start=dashboard"
            )]]
        )
        text = "💬 *Dashboard available in private chat:*\nTap above to continue\\."
    
    await message.answer(
        text=text,
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )


# =====================
# CREATE FRACTAL FSM
# =====================

@router.message(CreateFractal.name)
async def fsm_get_name(message: types.Message, state: FSMContext):
    """Get fractal name from user."""
    await state.update_data(name=message.text.strip())
    await message.answer(
        "✏️ Now enter the *fractal description*\\.\n"
        "You can write multiple lines in a single message\\.",
        parse_mode="MarkdownV2",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.description)


@router.message(CreateFractal.description)
async def fsm_get_description(message: types.Message, state: FSMContext):
    """Get fractal description from user."""
    await state.update_data(description=message.text.strip())
    await message.answer(
        "⏱ Specify *round time* in minutes per round \\(e\\.g\\. 30\\):",
        parse_mode="MarkdownV2",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.round_time)


@router.message(CreateFractal.round_time)
async def fsm_get_round_time(message: types.Message, state: FSMContext):
    """Get round time from user."""
    try:
        round_time = int(message.text.strip())
        if round_time <= 0 or round_time > 120:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Invalid round time\\. Enter 1\\-120 minutes \\(e\\.g\\. 15, 30\\)\\.",
            parse_mode="MarkdownV2"
        )
        return
    
    await state.update_data(round_time=round_time)
    await message.answer(
        "🌍 *Pick your timezone*, then enter start time:\n\n"
        "• `30` = 30 min from now\n"
        "• `202601011700` = Jan 1st 17:00",
        parse_mode="MarkdownV2",
        reply_markup=timezone_keyboard()
    )
    await state.set_state(CreateFractal.timezone)


@router.message(CreateFractal.start_date)
async def fsm_get_start_date(message: types.Message, state: FSMContext):
    """Get start date from user."""
    start_date_raw = message.text.strip()
    
    time = await parse_start_date(state, start_date_raw)
    
    if not time:
        await message.answer(
            "❌ Invalid format\\. Use:\n"
            "• `30` = 30 min from now\n"
            "• `202601011700` = exact time",
            parse_mode="MarkdownV2",
            reply_markup=cancel_keyboard()
        )
        return
    
    data = await state.get_data()
    name = data.get("name", "")
    description = data.get("description", "")
    round_time = data.get("round_time", 30)
    
    start_date_formatted = time.strftime("%A, %B %d, %Y")
    times_str = format_international_times(time.isoformat(), round_time)
    
    escaped_name = escape_markdown_v2(name)
    escaped_desc = escape_markdown_v2(description)
    escaped_times = escape_markdown_v2(times_str)
    
    meta_settings = {"round_time": round_time}
    
    async for db in get_async_session():
        try:
            fractal = await create_fractal(
                db=db,
                name=name,
                description=description,
                start_date=time,
                settings=meta_settings,
            )
            
            fractal_id = getattr(fractal, "id", None)
            
            share_text = (
                f"🎉 *Fractal Created*\n\n"
                f"🚀 {escaped_name}\n\n"
                f"📝 {escaped_desc}\n\n"
                f"📅 {start_date_formatted}\n\n"
                f"{escaped_times}\n\n"
                f"🔄 {round_time} minutes rounds\n\n"
                f"⚡️ Share this link https://t.me/{settings.bot_username}?start=fractal_{fractal_id}"
            )
            
            await message.answer(share_text, parse_mode="MarkdownV2")
            
            if message.chat.type == ChatType.PRIVATE:
                await message.answer(
                    text="📢 Join and Share your Fractal to a group:",
                    reply_markup=share_to_group_button(fractal_id),
                )
            
            break
        except Exception as e:
            logger.exception("Failed to create fractal")
            await message.answer(f"⚠️ Failed to create fractal: {escape(str(e))}")
            break
    
    await state.clear()


# =====================
# JOIN FRACTAL
# =====================

@router.message(Command("join"))
async def cmd_join(
    message: types.Message,
    state: FSMContext,
    fractal_id: Union[str, int] = None,
    user_id: str = None,
    username: str = None
):
    """Handle /join command or button callback."""
    telegram_id = user_id or str(message.from_user.id)
    username = username or getattr(message.from_user, "username", "")
    
    if fractal_id is None:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /join <fractal_id|fractal_name>")
            return
        fractal_id = parts[1].strip()
    
    if not fractal_id:
        await message.answer("No fractal ID or name provided\\.")
        return
    
    user_info = {"username": username, "telegram_id": telegram_id}
    
    async for db in get_async_session():
        try:
            fractal = await get_fractal_from_name_or_id_repo(
                db=db,
                fractal_identifier=str(fractal_id)
            )
            
            if not fractal:
                await message.answer(
                    f"❌ Fractal *{escape_markdown_v2(str(fractal_id))}* not found or not created yet\\.\n\n"
                    f"ℹ️ It may have been deleted or never initialized properly\\.",
                    parse_mode="MarkdownV2",
                )
                break
            
            user = await join_fractal(db, user_info, fractal.id)
            await state.update_data(
                user_id=user.id,
                fractal_id=fractal.id,
                fractal_name=fractal.name
            )
            
            escaped_name = escape_markdown_v2(fractal.name or "Fractal")
            await message.answer(
                f"🤝 Welcome to Fractal *{escaped_name}*\\!\n\n"
                f"⚡ You will get a telegram message when the meeting starts\\!",
                parse_mode="MarkdownV2"
            )
            break
        except Exception as e:
            logger.exception("Join failed")
            
            escaped_name = escape_markdown_v2(fractal.name or "Unknown")
            escaped_desc = escape_markdown_v2(fractal.description or "No description")
            start_str = fractal.start_date.strftime("%A %H:%M, %B %d, %Y") if fractal.start_date else "Unknown"
            round_time_minutes = int(fractal.meta.get("round_time", 0))
            round_time_str = f"{round_time_minutes} min/round" if round_time_minutes else "N/A"
            
            await message.answer(
                f"❌ *Cannot join fractal*\n\n"
                f"🆔 {escaped_name}\n\n"
                f"📝 {escaped_desc}\n\n"
                f"📅 {start_str}\n\n"
                f"⏰ {round_time_str}\n\n"
                f"📊 {fractal.status.title()}\n\n"
                f"⚠️ The fractal has probably already started, so joining is not possible\\.",
                parse_mode="MarkdownV2",
            )
            break


# =====================
# START/CLOSE FRACTAL
# =====================

@router.message(Command("start_fractal"))
async def cmd_start_fractal(
    message: types.Message,
    state: FSMContext = None,
    fractal_id: str = None
):
    """Handle /start_fractal command."""
    if fractal_id is None:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Usage: /start_fractal <fractal_id>")
            return
        fractal_id = parts[1].strip()
    
    async for db in get_async_session():
        try:
            round_obj = await start_fractal(db, int(fractal_id))
            await message.answer(f"🚀 Fractal `{fractal_id}` started\\!")
        except Exception as e:
            logger.exception("Failed to start fractal")
            await message.answer(f"Failed to start fractal: {escape(str(e))}")
        break


@router.message(Command("close_round"))
async def cmd_close_round(message: types.Message):
    """Handle /close_round command."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /close_round <fractal_id>")
        return
    
    fractal_id = int(parts[1].strip())
    
    async for db in get_async_session():
        try:
            res = await close_round(db=db, fractal_id=fractal_id)
            await message.answer(f"Round closed for fractal {fractal_id}\\.")
        except Exception as e:
            logger.exception("close_round failed")
            await message.answer(f"Failed to close round: {escape(str(e))}")
        break


# =====================
# PROPOSAL FSM
# =====================

@router.message(Command("proposal"))
async def cmd_proposal_start(
    message: types.Message,
    state: FSMContext,
    fractal_id: str = None
):
    """Start FSM for proposal creation."""
    await state.update_data(
        fractal_id=fractal_id,
        body="",
        telegram_id=str(message.from_user.id)
    )
    
    text = message.text or ""
    
    # One-liner support: /proposal "Title: Body"
    if '"' in text:
        try:
            quoted = text.split('"')[1]
            if ":" in quoted:
                title, body = map(str.strip, quoted.split(":", 1))
            else:
                title = quoted.strip()
                body = ""
            
            await state.update_data(title=title, body=body)
            
            if body:
                await proposal_done(message, state)
                return
            else:
                await state.set_state(ProposalStates.waiting_for_body)
                await message.answer(
                    f"Title saved: {escape(title)}\n"
                    f"Send body for this proposal \\(one message\\)\\.",
                    reply_markup=cancel_keyboard()
                )
                return
        except Exception:
            pass
    
    # Normal FSM flow
    await state.set_state(ProposalStates.waiting_for_title)
    await message.answer(
        "Creating a proposal\\. Send the title as text\\.",
        reply_markup=cancel_keyboard(),
        parse_mode="MarkdownV2"
    )


@router.message(ProposalStates.waiting_for_title)
async def proposal_title_received(message: types.Message, state: FSMContext):
    """Receive proposal title."""
    title = message.text.strip()
    if not title:
        await message.answer("Title cannot be empty\\. Send text for the title\\.")
        return
    
    await state.update_data(title=title)
    await state.set_state(ProposalStates.waiting_for_body)
    await message.answer(
        f"Title saved: {escape(title)}\n"
        f"Send body for this proposal \\(one message\\)\\.",
        reply_markup=cancel_keyboard()
    )


@router.message(ProposalStates.waiting_for_body)
async def proposal_body_received(message: types.Message, state: FSMContext):
    """Receive proposal body."""
    body = message.text.strip()
    if not body:
        await message.answer("Body cannot be empty\\. Send text for the body\\.")
        return
    
    await state.update_data(body=body)
    await proposal_done(message, state)


async def proposal_done(message: types.Message, state: FSMContext):
    """Complete proposal creation."""
    data = await state.get_data()
    title = data.get("title", "").strip()
    body = data.get("body", "").strip()
    telegram_id = data.get("telegram_id")
    
    if not title or not body:
        await message.answer("❌ Title or body missing\\. Proposal canceled\\.")
        await state.clear()
        return
    
    if len(body) > 2000:
        await message.answer("❌ Body too long \\(max 2000 chars\\)\\. Proposal canceled\\.")
        await state.clear()
        return
    
    async for db in get_async_session():
        user_info = await get_user_info(str(telegram_id))
        if not user_info:
            await message.answer("❌ You must join a fractal first\\!")
            await state.clear()
            break
        
        try:
            fractal_id = int(user_info.get("fractal_id", 0))
            group_id = int(user_info.get("group_id", 0))
            round_id = int(user_info.get("round_id", 0))
            creator_user_id = int(user_info.get("creator_user_id", 0))
            
            proposal = await create_proposal(
                db=db,
                fractal_id=fractal_id,
                group_id=group_id,
                round_id=round_id,
                title=title,
                body=body,
                creator_user_id=creator_user_id,
            )
            
            pid = getattr(proposal, "id", None)
            safe_title = escape(title)
            safe_snippet = escape(body[:200])
            
            html_text = f"<b>P_{pid}</b> {safe_title}\nBy: {telegram_id}\n{safe_snippet}\\.\\.\\."
            await message.answer(
                html_text,
                reply_markup=vote_proposal_keyboard(pid),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.exception("create_proposal failed")
            await message.answer(f"❌ Failed to create proposal: {escape(str(e))}")
        
        break
    
    await state.clear()


# =====================
# COMMENT
# =====================

@router.message(Command("comment"))
async def cmd_comment(message: types.Message):
    """Add comment to proposal or reply to comment."""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /comment p_<id> <text>  OR  /comment c_<id> <text>")
        return
    
    id_part = parts[1]
    text = parts[2].strip()
    
    async for db in get_async_session():
        try:
            if id_part.startswith("p_"):
                pid = int(id_part[2:])
                comment = await create_comment(
                    db=db,
                    proposal_id=pid,
                    user_id=message.from_user.id,
                    text=text,
                    parent_comment_id=None
                )
                cid = getattr(comment, "id", None)
                await message.answer(f"Comment added to proposal P_{pid}: C_{cid}")
            elif id_part.startswith("c_"):
                cid = int(id_part[2:])
                comment = await create_comment(
                    db=db,
                    proposal_id=0,
                    user_id=message.from_user.id,
                    text=text,
                    parent_comment_id=cid
                )
                cid2 = getattr(comment, "id", None)
                await message.answer(f"Reply added: C_{cid2}")
            else:
                await message.answer("ID must be p_<id> or c_<id>")
        except Exception as e:
            logger.exception("create_comment failed")
            await message.answer(f"Failed to add comment: {escape(str(e))}")
        break


# =====================
# VOTE
# =====================

@router.message(Command("vote"))
async def cmd_vote(message: types.Message):
    """Vote on proposal or comment."""
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /vote p_<id> <1\\-10>  OR  /vote c_<id> <yes|no|1|0>")
        return
    
    id_part = parts[1]
    val = parts[2].lower()
    
    async for db in get_async_session():
        try:
            if id_part.startswith("p_"):
                pid = int(id_part[2:])
                score = int(val) if val.isdigit() else None
                if score is None or not (1 <= score <= 10):
                    await message.answer("Proposal votes must be 1\\-10")
                    return
                await vote_proposal(
                    db=db,
                    proposal_id=pid,
                    voter_user_id=message.from_user.id,
                    score=score
                )
                await message.answer("Proposal vote recorded\\.")
            elif id_part.startswith("c_"):
                cid = int(id_part[2:])
                vote_bool = True if val in ("yes", "y", "1", "true") else False
                await vote_comment(
                    db=db,
                    comment_id=cid,
                    voter_user_id=message.from_user.id,
                    vote=vote_bool
                )
                await message.answer("Comment vote recorded\\.")
            else:
                await message.answer("ID must be p_<id> or c_<id>")
        except Exception as e:
            logger.exception("vote failed")
            await message.answer(f"Failed to record vote: {escape(str(e))}")
        break


# =====================
# CATCH-ALL ECHO
# =====================

@router.message()
async def echo_all(message: types.Message):
    """Catch-all echo handler for messages in groups."""
    if not message.text:
        return
    
    user_info = await get_user_info(str(message.from_user.id))
    if not user_info:
        return
    
    group_id = int(user_info.get("group_id", 0))
    if group_id == 0:
        return
    
    username = user_info.get("username", "User")
    message_text = f"👋 {escape(username)} wrote:\n💬 {escape(message.text)}"
    
    async for db in get_async_session():
        try:
            telegram_ids = []
            members = await get_group_members_repo(db, group_id)
            for member in members:
                user = await get_user(db, member.user_id)
                if user and user.telegram_id:
                    try:
                        telegram_ids.append(int(user.telegram_id))
                    except ValueError:
                        pass
            
            if telegram_ids:
                await send_message_to_telegram_users(telegram_ids, message_text)
        except Exception as e:
            logger.exception(f"Failed to broadcast message: {e}")
        break
