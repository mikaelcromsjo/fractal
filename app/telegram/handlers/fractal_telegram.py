# telegram/handlers/fractal_telegram.py
import logging
from datetime import datetime, timedelta, timezone
import re
from datetime import datetime
from typing import Optional, Dict, Any, Union
from aiogram import types, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from html import escape
from aiogram.enums import ParseMode
from fastapi import HTTPException
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram import F
from aiogram.enums import ChatType
from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from config.settings import settings
from zoneinfo import ZoneInfo

from infrastructure.db.session import get_async_session

from telegram.service import send_message_to_telegram_users, send_button_to_telegram_users

from services.fractal_service import (
    create_fractal,
    join_fractal,
    start_fractal,
    close_last_round,
    get_fractal_from_name_or_id_repo,
    send_message_to_group,
    get_group_members_repo,
    get_user,
    get_winning_proposal_telegram_repo
)

from infrastructure.db.session import get_async_session
from services.fractal_service import (
    create_proposal,
    create_comment,
    vote_proposal,
    vote_comment,
    vote_representative_repo,
    get_proposals_comments_tree,
    get_proposal_comments_tree,
    get_user_by_telegram_id,
    get_user_info_by_telegram_id
)

from telegram.states import ProposalStates, CreateFractal
from telegram.keyboards import timezone_keyboard, share_to_group_button, create_keyboard, vote_comment_keyboard, vote_proposal_keyboard, list_more_keyboard, show_hidden_keyboard, cancel_keyboard, fractal_actions_menu, help_menu
from aiogram.filters import CommandStart


logger = logging.getLogger(__name__)
router = Router()

def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2 format.    
    MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

def format_international_times(start_date):
    start_dt = datetime.fromisoformat(start_date)
    
    times = {
        '🇪🇺 CET': start_dt.astimezone(ZoneInfo('Europe/Berlin')).strftime('%H:%M'),
        '🇬🇧 GMT': start_dt.astimezone(ZoneInfo('Europe/London')).strftime('%H:%M'),
        '🇺🇸 EST': start_dt.astimezone(ZoneInfo('America/New_York')).strftime('%H:%M'),
        '🇺🇸 PST': start_dt.astimezone(ZoneInfo('America/Los_Angeles')).strftime('%H:%M'),
        '🇧🇷 BRT': start_dt.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M'),
        '🇮🇳 IST': start_dt.astimezone(ZoneInfo('Asia/Kolkata')).strftime('%H:%M'),
        '🇯🇵 JST': start_dt.astimezone(ZoneInfo('Asia/Tokyo')).strftime('%H:%M'),
        '🇦🇺 AEST': start_dt.astimezone(ZoneInfo('Australia/Sydney')).strftime('%H:%M'),
    }
    
    time_lines = [f"{flag}: {time}" for flag, time in times.items()]
    return ' ' + ' '.join(time_lines[:8])  # Show first 7 for Telegram width


# Central command list (help)
COMMANDS = [
    ("start", "Check if bot is alive"),
    ("help", "Show available commands"),
    ("create_fractal", "Create a new fractal"),
    ("join", "Join a fractal (id or name)"),
    ("start_fractal", "Start the fractal (admin)"),
    ("close_round", "Close current round (admin)"),
#    ("proposal", "Start a new proposal (FSM)"),
#    ("comment", "Add a comment: /comment p_[id] <text> or /comment c_[id] <text>"),
#    ("vote", "Vote on proposal/comment"),
#    ("representative", "Vote for representative"),
#    ("tree", "Show proposals/comments tree"),
]


from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils import markdown

@router.inline_query()
async def handle_inline_share(query: InlineQuery):
    """Creates a 'Sign up for Fractal Meeting' button to share to groups."""
    print("INLINE QUERY RECEIVED:", query.query)

    q = query.query.strip()

    if not q.startswith("share fractal_"):
        return

    fractal_id = q.split("_", 1)[1]

    async for db in get_async_session():
        try:
            fractal = await get_fractal_from_name_or_id_repo(
                db=db,
                fractal_identifier=fractal_id
            )

            if not fractal:
                return
            now = datetime.now(timezone.utc)
            if fractal.start_date < now or fractal.status.lower() != "waiting":
                return

        except Exception as e:
            # Print the full traceback to understand what went wrong
            print(f"[ERROR] Failed to process fractal {fractal_id}: {e}")
            break



    bot_username = settings.bot_username
    join_url = f"https://t.me/{bot_username}?start=fractal_{fractal_id}"

    join_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Go to Fractal", url=join_url)]
        ]
    )
    start_date = fractal.start_date.strftime("%A %H:%M, %B %d, %Y")
    minutes = int(fractal.meta["round_time"])
    round_time = f"{int(minutes)} minutes"


    share_text = (
        f"🎉 Click to Sign up for Fractal Meeting: \"{sanitize_text(fractal.name)}\"\n\n"
        f"📝 {sanitize_text(fractal.description)}\n\n"
        f"📅 {start_date}\n\n"
        f"{format_international_times(fractal.start_date.isoformat())}\n\n"
        f"🔄 {round_time} rounds\n\n"
        f"📢 Share this link `https://t.me/{settings.bot_username}?start=fractal_{fractal_id}`"
    )

    await query.answer(
        results=[
            InlineQueryResultArticle(
                id=f"share_{fractal_id}",
                title="Share Fractal to Group",
                description="Send a join button to your group",
                input_message_content=InputTextMessageContent(
                    message_text=share_text,
                    parse_mode="Markdown",
                ),
                reply_markup=join_button,
            )
        ],
        cache_time=0,
        is_personal=True,  # Ensures fresh results for each user
    )

# Callbacks


@router.callback_query(F.data == "tz_manual")
async def handle_manual_tz(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "⌨️ *Enter UTC offset*:\n\n"
        "🇪🇺 `+1` CET\n🇫🇮 `+2` EET\n🇬🇧 `0` GMT\n"
        "🇺🇸 `-5` EST\n🇺🇸 `-8` PST\n🇧🇷 `-3` BRT\n"
        "🇮🇳 `+5.5` IST\n🇯🇵 `+9` JST\n🇦🇺 `+10` AEST\n"
        "🇨🇳 `+8` China\n🇷🇺 `+3` Moscow\n🇿🇦 `+2` South Africa\n"
        "🇲🇽 `-6` Mexico\n🇦🇷 `-3` Argentina\n🇸🇬 `+8` Singapore\n\n"
        "_Examples: `+3.5`, `-4.5`, `+11.5`_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.timezone_manual) 
    await callback.answer()

@router.message(CreateFractal.timezone_manual)
async def handle_manual_offset(message: types.Message, state: FSMContext):
    try:
        offset = float(message.text.strip())
        await state.update_data(user_tz_offset=offset)
        await message.answer(
            f"✅ *Offset {offset:+.1f}h* set! Now enter start time:\n"
            "• `30` = 30 min from now\n"
            "• `202601011700` = exact time",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(CreateFractal.start_date)  # ✅ Now go to start_date
    except ValueError:
        await message.answer("❌ Invalid offset. Use `+2` or `-5`. Try again:")


@router.callback_query(F.data.startswith("tz_"))
async def handle_timezone(callback: types.CallbackQuery, state: FSMContext):
    tz_map = {
        "tz_cet": 1.0,           # 🇪🇺 CET → Europe/Berlin
        "tz_gmt": 0.0,           # 🇬🇧 GMT → Europe/London  
        "tz_est": -5.0,          # 🇺🇸 EST → America/New_York
        "tz_pst": -8.0,          # 🇺🇸 PST → America/Los_Angeles
        "tz_brt": -3.0,          # 🇧🇷 BRT → America/Sao_Paulo
        "tz_ist": 5.5,           # 🇮🇳 IST → Asia/Kolkata
        "tz_jst": 9.0,           # 🇯🇵 JST → Asia/Tokyo
        "tz_aest": 10.0,         # 🇦🇺 AEST → Australia/Sydney
        "tz_eet": 2.0,           # Existing
    }
    offset = tz_map.get(callback.data, 0.0)
    
    await state.update_data(user_tz_offset=offset)
    data = await state.get_data()  # ✅ DEBUG
    print(f"🔍 STATE AFTER BUTTON: {data}")  # Check if saved
    
    await callback.message.edit_text(
        f"✅ TZ set! Enter start time:\n• `30` = 30 min from now\n"
        "• `202601011700` = Jan 1st 17:00",
        parse_mode="Markdown"
    )
    await state.set_state(CreateFractal.start_date)
    await callback.answer()

# Manual handler - add debug  
@router.message(CreateFractal.timezone_manual)
async def handle_manual_offset(message: types.Message, state: FSMContext):
    offset = float(message.text.strip())
    await state.update_data(user_tz_offset=offset)
    data = await state.get_data()  # ✅ DEBUG
    print(f"🔍 STATE AFTER MANUAL: {data}")  # Check if saved
    
    await message.answer("✅ Offset set! Enter start time:\n• `30`")
    await state.set_state(CreateFractal.start_date)

@router.callback_query(lambda c: c.data == "cmd:help")
async def cb_help(call: types.CallbackQuery):
    await call.answer()
    await cmd_help(call.message)

@router.callback_query(lambda c: c.data.startswith("join:"))
async def cb_join(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    
    fractal_id = int(call.data.split(":", 1)[1])
    
    # ✅ Use call.message (works perfectly) + pass real user via state
    await cmd_join(call.message, state=state, fractal_id=fractal_id, 
                   user_id=str(call.from_user.id),  # ✅ Real user ID
                   username=getattr(call.from_user, "username", ""))


@router.callback_query(lambda c: c.data.startswith("tree:"))
async def cb_tree(call: types.CallbackQuery, state: FSMContext):
    await call.answer()  # stop the spinner

    fractal_id = call.data.split(":", 1)[1]  # extract fractal ID

    # call your existing cmd_start function directly
    # assuming cmd_start accepts fractal_id and optionally FSM state
    await cmd_tree(call.message, fractal_id=fractal_id)


@router.callback_query(lambda c: c.data.startswith("start_fractal:"))
async def cb_start_fractal(call: types.CallbackQuery, state: FSMContext):
    await call.answer()  # stop the spinner

    fractal_id = call.data.split(":", 1)[1]  # extract fractal ID

    # call your existing cmd_start function directly
    # assuming cmd_start accepts fractal_id and optionally FSM state
    await cmd_start_fractal(call.message, fractal_id=fractal_id, state=state)


@router.callback_query(lambda c: c.data == "cmd:create_fractal")
async def cb_start_create_fractal(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("📝 Please enter name of the meeting:", parse_mode="Markdown", reply_markup=cancel_keyboard())
    await state.set_state(CreateFractal.name)


@router.callback_query(lambda c: c.data.startswith("proposal:"))
async def cb_proposal_button(call: types.CallbackQuery, state: FSMContext):
    await call.answer()

    # Extract fractal_id from callback_data
    fractal_id = call.data.split(":", 1)[1]

    # Save Telegram ID and fractal_id in FSM state
    await state.update_data(
        telegram_id=str(call.from_user.id),  # the user who clicked
        fractal_id=fractal_id,
        body=""
    )

    # Start the proposal FSM
    await cmd_proposal_start(call.message, state)


@router.callback_query(lambda c: c.data == "cmd:cancel")
async def cb_cancel(call: types.CallbackQuery, state: FSMContext):
    await call.answer()  # stops the spinner
    await state.clear()  # cancels any FSM
    await call.message.answer(
        "❌ Operation canceled."
    )

# -----------------------
# Helpers
# -----------------------


async def get_user_info(telegram_id) -> Dict:
    async for db in get_async_session():
            try:
                user_info = await get_user_info_by_telegram_id(db, str(telegram_id))
                return user_info
            except Exception:
                logger.exception("Failed getting user data")
                return {}

def format_proposal_preview(proposal: Dict[str, Any]) -> str:
    """Return HTML formatted preview of a proposal (placeholder)."""
    pid = getattr(proposal, "id", None) or proposal.get("id")
    title = getattr(proposal, "title", "") or proposal.get("title", "")
    creator = getattr(proposal, "creator_user_id", "") or proposal.get("creator_user_id", "")
    snippet = (getattr(proposal, "body", "") or proposal.get("body", ""))[:200].replace("<", "&lt;")
    return f"<b>P_{pid}</b> {title}\nBy: {creator}\n{snippet}..."


async def parse_start_date(state: FSMContext, s: str) -> Optional[datetime]:
    print(f"🔍 PARSE: input='{s}'")
    
    s = s.strip()
    data = await state.get_data()
    user_tz_offset = data.get('user_tz_offset', 0)
    print(f"🔍 PARSE: offset={user_tz_offset}")
    
    try:
        if re.match(r'^\d{1,4}$', s):
            minutes = int(s)
            print(f"✅ PARSE: relative {minutes}min")
            
            # User's local now → UTC
            utc_now = datetime.now(timezone.utc)
            user_local_now = utc_now + timedelta(hours=user_tz_offset)
            user_future_local = user_local_now + timedelta(minutes=minutes)
            
            # Back to UTC for DB
            utc_for_db = user_future_local - timedelta(hours=user_tz_offset)
            print(f"🔍 UTC now: {utc_now}, User local: {user_local_now}, UTC DB: {utc_for_db}")
            return utc_for_db
        
        if re.match(r'^\d{12}$', s):
            print("✅ PARSE: exact time")
            user_time = datetime.strptime(s, "%Y%m%d%H%M")
            # User local → UTC
            utc_time = user_time.replace(tzinfo=timezone.utc) - timedelta(hours=user_tz_offset)
            return utc_time
    
    except Exception as e:
        print(f"❌ PARSE ERROR: {e}")
    
    return None


def sanitize_text(s: str) -> str:
    """Escape characters that might be misinterpreted by Telegram when parse_mode=None is not set."""
    if s is None:
        return ""
    return s.replace("<", "&lt;").replace(">", "&gt;")


# -----------------------
# Handlers
# -----------------------


from telegram.keyboards import default_menu  # adjust import to your structure
from aiogram.types import BotCommand, MenuButtonCommands


@router.message(Command("dashboard"))
async def dashboard_command(message: types.Message):
    dashboard_url = f"{settings.public_base_url}/api/v1/fractals/dashboard"

    if message.chat.type == ChatType.PRIVATE:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[

            [        InlineKeyboardButton(
                        text="🚀 Open Dashboard",
                        web_app=WebAppInfo(url=dashboard_url),
                    )   
            ]
        ])
        
        await message.answer(
            text="Open The Fractal Circles App:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            text=f"Go to https://t.me/{settings.bot_username}"
        )



@router.message(Command("invite"), F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]))
async def cmd_invite_group(message: types.Message):
    fractal_id = int(message.text.split()[1])

    # in groups: NO web_app button, only URL buttons
    join_menu = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🎯 Sign up for Fractal Meeting {fractal_id}",
                    url=f"https://t.me/{settings.bot_username}?start=fractal_{fractal_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Open Dashboard",
                    url=f"{settings.public_base_url}/api/v1/fractals/dashboard?fractal_id={fractal_id}",
                )
            ],
        ]
    )

    await message.answer(
        f"🚀 *Fractal {fractal_id} ready for group!*\n\n"
        f"👆 Click button to join via private chat",
        reply_markup=join_menu,
        parse_mode="Markdown",
    )

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    from telegram.bot import init_bot
    bot, _ = init_bot()
    
    # Commands
    commands = [
        BotCommand(command="start", description="Start Menu"),
        BotCommand(command="help", description="Information"),
        BotCommand(command="dashboard", description="Dashboard"),
    ]
    #await bot.set_my_commands(commands)
    
    if message.chat.type == ChatType.PRIVATE:
        await bot.set_chat_menu_button(chat_id=message.chat.id, menu_button=MenuButtonCommands())

    args = message.text.split(maxsplit=1)
    
    if len(args) > 1 and args[1].startswith("fractal_"):
        try:
            fractal_id = int(args[1].replace("fractal_", ""))
        except ValueError:
            await message.answer("❌ Invalid fractal ID.")
            return

        async for db in get_async_session():
            try:
                fractal = await get_fractal_from_name_or_id_repo(db=db, fractal_identifier=fractal_id)
                
                if not fractal:
                    await message.answer(
                        f"❌ Fractal *{sanitize_text(str(fractal_id))}* not found or not created yet.\n\n"
                        f"ℹ️ It may have been deleted or never initialized properly.",
                        parse_mode="Markdown",
                    )
                    break

#                print(f"🔍 FRACTAL STATUS: '{fractal.status}'")
#                now = datetime.now(timezone.utc)

                # ✅ FIX 1: Define start_date consistently
                start_date = (
                    fractal.start_date.strftime("%A %H:%M, %B %d, %Y")
                    if fractal.start_date
                    else "Unknown"
                )
                
                minutes = fractal.meta.get("round_time", 0)
                round_time = f"{int(minutes)} minutes"

                # A fractal can only be joined if status is "waiting"

                if fractal.status.lower() == "closed":
                    # 🏆 VISAR VINNARE NÄR FRACTAL ÄR STÄNGD
                    winning_text = await get_winning_proposal_telegram_repo(db, fractal.id)
                    
                    if winning_text:
                        await message.answer(
                            f"🏆 <b>Fractal avslutad!</b>\n\n{winning_text}",
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            f"❌ Fractal \"{sanitize_text(fractal.name)}\" är stängd\n"
                            f"Men inget förslag vann.",
                            parse_mode=None
                        )
                    break

                elif fractal.status.lower() != "waiting":
                    international_times = format_international_times(
                        fractal.start_date.isoformat()
                    )
                    
                    await message.answer(
                        f"❌ The Fractal is not open: \"{sanitize_text(fractal.name)}\"\n\n"
                        f"📝 {sanitize_text(fractal.description)}\n\n"
                        f"📅 {start_date}\n"
                        f"{international_times}\n\n"
                        f"🔄 {round_time} rounds",
                        parse_mode=None
                    )
                    break
                    
                # ✅ SHOW JOIN MENU
                builder = InlineKeyboardBuilder()
                builder.button(text="🙋 Sign up for Fractal Meeting", callback_data=f"join:{fractal.id}")
                builder.button(
                    text="ℹ️ Get more information",
                    callback_data="cmd:help"
                )
                builder.adjust(1, 1)
                button = builder.as_markup()

                # Remove time from start_date - show only date
                start_date_formatted = (
                    fractal.start_date.strftime("%A, %B %d, %Y")
                    if fractal.start_date
                    else "Unknown"
                )

                international_times = format_international_times(
                    fractal.start_date.isoformat()
                )

                await message.answer(
                    f"🎉 Click to Sign up for Fractal Meeting: \"{sanitize_text(fractal.name)}\"\n\n"
                    f"📝 {sanitize_text(fractal.description)}\n\n"
                    f"📅 {start_date_formatted}\n\n"  # Date only
                    f"{international_times}\n\n"    # Times only
                    f"🔄 {round_time} rounds\n\n"
                    f"📢 Share this link `https://t.me/{settings.bot_username}?start=fractal_{fractal_id}`",
                    reply_markup=button, 
                    parse_mode=None
                )
                break

            except Exception as e:
                print(f"[ERROR] Fractal {fractal_id}: {e}")
                await message.answer("❌ Error loading fractal.")
                break
        
        return  # ✅ Exit after fractal handling

    # ✅ DEFAULT /start
    await message.answer("👋 Hi, I am the Fractal Circle Bot!", reply_markup=default_menu(message.chat.type == ChatType.PRIVATE))


@router.message(Command("help"))
async def cmd_help(message: types.Message):

    if message.chat.type == ChatType.PRIVATE:
        help_text = (
            "🤖 **Fractal Circle Bot** helps you organize fractal meetings in large groups.\n\n"
            "💌 In most cases, you'll be invited to join a fractal meeting that someone else created. "
            "You'll receive an invite link when that happens.\n\n"
            "🧩 If you're a group organizer, you can also create your own fractal and invite others to join.\n\n"
            "🎯 A Fractal meeting is divided into separate rounds where small Circles create proposals, discuss them, and vote on the best ideas. "
            "Most participants attend only one round; only the selected representatives continue to the next round.\n\n"
            "👥 When the fractal starts, you're placed in a small **Circle** (5-7 people). "
            "You'll chat with your Circle members in a private Telegram group and use the **Dashboard** web app to make proposals and vote.\n\n"
            "📝 **First half - Create & Discuss:** Focus on creating proposals on the topic and adding comments to refine ideas together. "
            "This is your brainstorming phase—be creative, ask questions, and build on each other's thoughts.\n\n"
            "⏰ **Halfway mark:** The bot reminds you that voting time has begun. You can still add comments to help clarify ideas, but no new proposals can be created. "
            "Now shift your focus to evaluation.\n\n"
            "⭐ **Vote on proposals:** Give each proposal a score from 1-10 stars based on its merit. "
            "The **top 2 proposals** from your Circle will move to the next round.\n\n"
            "⭐ **Vote on comments:** Rate each comment with 1-3 stars to surface the most valuable insights. "
            "This helps everyone see which feedback matters most.\n\n"
            "🥇 **Select your representative:** Allocate Gold, Silver, and Bronze medals to three Circle members who you trust to represent your group's voice. "
            "The person with the most points advances to the next round. You cannot vote for yourself.\n\n"
            "🔄 **Next rounds:** Only representatives continue, discussing the top proposals that advanced. They vote again and select a new representative. "
            "This repeats until one final Circle remains with the best ideas from everyone.\n\n"
            "🏆 **Final results:** When the fractal ends, you'll see the top-ranked proposals from the center Circle and the most trusted representatives who carried ideas forward. "
            "This is collective wisdom in action—the best ideas rise to the top through collaboration.\n\n"
            "Collaborate, connect, and grow your circle! 🌱\n\n"
            "Read more at https://FractalCircles.org\nContribute to the development on https://UniteAwake.com"
        )
        await message.answer(help_text, parse_mode="Markdown")
    else:
        help_text = (
            "🤖 **Fractal Circle Bot** helps you organize fractal meetings in large groups.\n\n"
            "💌 In most cases, you'll be invited to join a fractal meeting that someone else created. "
            "You'll receive an invite link when that happens.\n\n"
            "🧩 If you’re a group organizer, you can also create your own fractal and invite others to join. \n\n"
            "🎯 A Fractal meeting is divided into separate rounds in which breakout groups create proposals, discuss them, and vote on them. Most participants attend only one round; only the selected representatives continue to the next round. Go to the #FractalCircleBot and try it out!\n\n"
            "Collaborate, connect, and grow your circle!\n\nRead more on https://FractalCircles.org\nContribute on http://UniteAwake.com"
        )
        await message.answer(help_text, parse_mode="Markdown")

@router.message(CreateFractal.name)
async def fsm_get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer(
        "✏️ Now enter the *fractal description*.\n"
        "You can write multiple lines in a single message.",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.description)

@router.message(CreateFractal.description)
async def fsm_get_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer(
        "⏱ Specify *round time* in minutes per round (e.g. 30):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.round_time)

@router.message(CreateFractal.round_time)
async def fsm_get_round_time(message: types.Message, state: FSMContext):
    try:
        round_time = int(message.text.strip())
        if round_time <= 0 or round_time > 120:  # Max 2 hours reasonable
            raise ValueError
    except ValueError:
        await message.answer("❌ Invalid round time. Enter 1-120 minutes (e.g. 15, 30).")
        return
    
    await state.update_data(round_time=round_time)
    await message.answer(
        "🌍 *Pick your timezone*, then enter start time:\n\n"
        "• `30` = 30 min from now\n"
        "• `202601011700` = Jan 1st 17:00",
        parse_mode="Markdown",
        reply_markup=timezone_keyboard()
    )
    await state.set_state(CreateFractal.timezone)

@router.message(CreateFractal.start_date)
async def fsm_get_start_date(message: types.Message, state: FSMContext):
    start_date_raw = message.text.strip()
    print(f"🔍 DEBUG START_DATE: raw='{start_date_raw}'")
    
    time = await parse_start_date(state, start_date_raw)
    print(f"🔍 DEBUG RESULT: time={time}")
    
    if not time:
        print("❌ DEBUG: parse_start_date returned None")
        await message.answer(
            "❌ Invalid format. Use:\n"
            "• `30` = 30 min from now\n"
            "• `202601011700` = exact time",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        return
    
    print("✅ DEBUG: Success! Continuing...")

    data = await state.get_data()
    name = data["name"]
    description = data["description"]
    round_time = data["round_time"]

    # ✅ Format for display
    start_date_formatted = time.strftime("%A, %B %d, %Y")
    international_times = format_international_times(time.isoformat())

    # Build dict for create_fractal
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
            fractal_name = getattr(fractal, "name", name)

            share_text = (
                f'<b>🎉 Fractal Created:</b> "{sanitize_text(fractal_name)}"\n\n'
                f'<i>📝 {sanitize_text(description)}</i>\n\n'
                f'<b>📅 {start_date_formatted}</b>\n\n'
                f'{international_times}\n\n'
                f'<b>🔄 {round_time} minute rounds</b>\n\n'
                f"👉 <a href=\"https://t.me/{settings.bot_username}?start=fractal_{fractal_id}\">Go to Fractal to sign up for the meeting</a>"
            )

            await message.answer(share_text, parse_mode="HTML")

            if message.chat.type == ChatType.PRIVATE:
                await message.answer(
                    text="📢 Join and Share your Fractal to a group:",
                    reply_markup=share_to_group_button(fractal_id),
                )
            break  # ✅ Exit loop

        except Exception as e:
            logger.exception("FSM create_fractal failed")
            await message.answer(f"⚠️ Failed to create fractal: {e}")
            break

    await state.clear()

    

@router.message(Command("create_fractal"))
async def cmd_create_fractal(message: types.Message):
    """
    Usage:
      /create_fractal name "description with spaces" round_time start_date
    """
    # Remove the command itself
    args = message.text[len("/create_fractal "):].strip()
    if not args:
        await message.answer(
            "Usage: /create_fractal <name> [<desc>] <round_time> <start_date>\n"
            "• round_time: minutes per round (e.g. 30)\n"
            "• start_date: minutes-from-now (e.g. 30) or YYYYMMDDHHMM (e.g. 202511261530)",
            parse_mode=None,
            reply_markup=create_keyboard(),
        )
        return

    try:
        args_parts = args.split()
        if len(args_parts) < 3:
            await message.answer("Usage: /create_fractal <name> [<desc>] <round_time> <start_date>", parse_mode=None)
            return

        name = args_parts[0].strip()

        # Flexible description parsing - handles quoted multi-word descriptions
        description = ""
        i = 1
        if len(args_parts) > 1 and args_parts[1].startswith('"'):
            # Collect quoted parts until closing quote
            while i < len(args_parts) and not args_parts[i].endswith('"'):
                description += args_parts[i] + " "
                i += 1
            if i < len(args_parts) and args_parts[i].endswith('"'):
                description += args_parts[i]
                description = description.strip('"').strip()
                i += 1
            else:
                await message.answer('Usage: /create_fractal <name> "<description>" <round_time> <start_date>', parse_mode=None)
                return
        else:
            # Single word description
            description = args_parts[1].strip()
            i = 2

        # Remaining args: round_time + start_date
        if i + 1 >= len(args_parts):
            await message.answer('Usage: /create_fractal <name> <desc> <round_time> <start_date>\nOR\n/create_fractal <name> "<long desc>" <round_time> <start_date>', parse_mode=None)
            return

        round_time = args_parts[i].strip()
        start_date_raw = args_parts[i + 1].strip()

        print(f"DEBUG: name='{name}', desc='{description}', round={round_time}, start='{start_date_raw}'")

        # Validation
        round_time_int = int(round_time)
        start_date = parse_start_date(start_date_raw)
        if not start_date:
            await message.answer("Couldn't parse start_date. Use minutes or YYYYMMDDHHMM.", parse_mode=None)
            return

        meta_settings = {"round_time": round_time_int}  # minutes

    except ValueError:
        await message.answer("round_time must be a number.", parse_mode=None)
        return
    except Exception as e:
        await message.answer(f"Failed to parse arguments: {e}", parse_mode=None)
        return

    # Create fractal
    async for db in get_async_session():
        try:
            fractal = await create_fractal(
                db=db,
                name=name,
                description=description,
                start_date=start_date,
                settings=meta_settings
            )
            fractal_id = getattr(fractal, "id", None)
            fractal_name = getattr(fractal, "name", name)

            from telegram.keyboards import fractal_created_menu

            share_text = (
                f"🚀 Fractal *{fractal_name}* created!\n\n"
                f"👥 You can invite others to join:\n"
                f"`https://t.me/{settings.bot_username}?start=fractal_{fractal_id}`"
            )

            await message.answer(share_text, parse_mode="Markdown")

            if message.chat.type == ChatType.PRIVATE:
                await message.answer(
                    text="📢 Join and Share your Fractal to a group:",
                    reply_markup=share_to_group_button(fractal_id),
                )
            else:
                await message.answer(share_text, parse_mode="Markdown")
            return

        except Exception as e:
            logger.exception("create_fractal failed")
            await message.answer(f"Failed to create fractal: {e}", parse_mode=None)
            return


async def cmd_join(message: types.Message, state: FSMContext, 
                  fractal_id: Union[str, int] | None = None,
                  user_id: str = None,  # ✅ From callback
                  username: str = None): # ✅ From callback
    
    # ✅ Use callback params FIRST, fallback to message.from_user
    telegram_id = user_id or str(message.from_user.id)

    username = username or getattr(message.from_user, "username", "")
    
    user_info = {"username": username, "telegram_id": telegram_id}

    if fractal_id is None:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /join <fractal_id|fractal_name>", parse_mode=None)
            return
        fractal_id = parts[1].strip()

    if not fractal_id:
        await message.answer("No fractal ID or name provided.")
        return

    logger.info(f"Looking up fractal: '{fractal_id}'")
    
    async for db in get_async_session():
        try:
            fractal = await get_fractal_from_name_or_id_repo(db=db, fractal_identifier=fractal_id)
            if not fractal:
                await message.answer(
                    f"❌ Fractal *{sanitize_text(str(fractal_id))}* not found or not created yet.\n\n"
                    f"ℹ️ It may have been deleted or never initialized properly.",
                    parse_mode="Markdown",
                )
                return  # ✅ stop cleanly, not break            
            
            user = await join_fractal(db, user_info, fractal.id)
            await state.update_data(
                user_id=user.id,
                fractal_id=fractal.id,
                fractal_name=fractal.name
            )
            await message.answer(f"🤝 Welcome to Fractal '{sanitize_text(fractal.name)}'!\n\n⚡ You will get a telegram message when the meeting starts!")
            break  # ✅ Exit after success
            
        except Exception as e:
            logger.exception("Join failed")

            # Build message text with proper escaping
            escaped_name = escape_markdown_v2(fractal.name or "Fractal")
            escaped_desc = escape_markdown_v2(fractal.description or "")
            start_date = fractal.start_date.strftime("%A, %B %d, %Y") if fractal.start_date else "Unknown"            
            minutes = int(fractal.meta.get("round_time", 0))
            times_str = format_international_times(fractal.start_date.isoformat())
            escaped_times = escape_markdown_v2(times_str)
                            
            await message.answer(
                f"⚠️ {e}\n\n"
                f"❌ Error in fractal: {sanitize_text(fractal.name)}\n\n"
                f"📝 {escaped_desc}\n\n"
                f"📅 {start_date}\n\n"
                f"{escaped_times}\n\n"
                f"📊 {fractal.status.title()}\n\n",
                parse_mode="MarkdownV2",
            )
            break

@router.message(Command("start_fractal"))
async def cmd_start_fractal(
    message: types.Message,
    state: FSMContext,
    fractal_id: str | None = None  # can be passed from button
):
    """
    /start_fractal <fractal_id>
    """
    if fractal_id is None:
        # parse from message text if user typed the command manually
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Usage: /start_fractal <fractal_id>", parse_mode=None)
            return
        fractal_id = parts[1].strip()

    async for db in get_async_session():
        try:
            print("start fractal")
            round = await start_fractal(db, int(fractal_id))            
        except Exception as e:
            logger.exception("Failed to start fractal")
            await message.answer(f"Failed to start fractal: {e}", parse_mode=None)
            return

    await message.answer(f"🚀 Fractal `{fractal_id}` started!", parse_mode="None")

@router.message(Command("close_round"))
async def cmd_close_round(message: types.Message):
    """
    Admin command: close_round <f>
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /close_round <fractal_id>", parse_mode=None)
        return
    round_id = int(parts[1].strip())

    async for db in get_async_session():
        try:
            res = await close_last_round(db=db, fractal_id=fractal_id)
            next_round_id = getattr(res, "id", None)
            # Optionally broadcast: need to find fractal id for this round, if available
            fractal_id = getattr(res, "fractal_id", None)
            await message.answer(f"Round closed for round {round_id}.", parse_mode=None)
        except Exception as e:
            logger.exception("close_round failed")
            await message.answer(f"Failed to close round: {e}", parse_mode=None)



# -------------------------
# Proposal FSM: Start + Done
# -------------------------

@router.message(Command("proposal"))
async def cmd_proposal_start(
    message: types.Message,
    state: FSMContext,
    fractal_id: str | None = None
):
    """
    Start FSM to create a proposal.
    Can be called via button (fractal_id) or /proposal command.
    Supports one-liner: /proposal "Title: Body"
    """
    # Save fractal_id and Telegram ID in FSM state
    await state.update_data(fractal_id=fractal_id)
    await state.update_data(body="")
    await state.update_data(telegram_id=str(message.from_user.id))  # important

    text = message.text or ""

    # One-liner support: /proposal "Title: Body"
    if '"' in text:
        try:
            quoted = text.split('"')[1]  # text inside quotes
            if ":" in quoted:
                title, body = map(str.strip, quoted.split(":", 1))
            else:
                title = quoted.strip()
                body = ""
            await state.update_data(title=title, body=body)

            if body:
                # Directly create proposal if body present
                await proposal_done(message, state)
                return
            else:
                # Ask for body
                await state.set_state(ProposalStates.waiting_for_body)
                await message.answer(
                    f"Title saved: {title}\nSend body for this proposal (one message).",
                    reply_markup=cancel_keyboard(), parse_mode=None
                )
                return
        except Exception:
            pass

    # Normal FSM flow: ask for title first
    await state.set_state(ProposalStates.waiting_for_title)
    await message.answer(
        "Creating a proposal. Send the title as text.",
        reply_markup=cancel_keyboard()
    )


async def proposal_done(message: types.Message, state: FSMContext):
    """
    Complete a proposal creation.
    Expects FSM state to contain 'title', 'body', 'telegram_id', and optionally 'fractal_id'.
    """
    data = await state.get_data()
    title = data.get("title", "").strip()
    body = data.get("body", "").strip()
    telegram_id = data.get("telegram_id")  # fetched from FSM

    if not title or not body:
        await message.answer("❌ Title or body missing. Proposal canceled.")
        await state.clear()
        return

    if len(body) > 2000:
        await message.answer("❌ Body too long (max 2000 chars). Proposal canceled.")
        await state.clear()
        return

    async for db in get_async_session():
        # Fetch the correct user using saved Telegram ID
        user_info = await get_user_info(str(telegram_id))
        if not user_info:
            await message.answer("❌ You must join a fractal first!")
            await state.clear()
            return

        fractal_id = int(user_info.get("fractal_id", 0))
        group_id = int(user_info.get("group_id", 0))
        round_id = int(user_info.get("round_id", 0))
        creator_user_id = int(user_info.get("creator_user_id", 0))

        try:
            proposal = await create_proposal(
                db=db,
                fractal_id=fractal_id,
                group_id=group_id,
                round_id=round_id,
                title=title,
                body=body,
                creator_user_id=creator_user_id,
            )
            pid = getattr(proposal, "id", None) or (proposal.get("id") if isinstance(proposal, dict) else None)

            # Escape for HTML
            safe_title = escape(title)
            safe_creator = escape(str(telegram_id))
            safe_snippet = escape(body[:200])

            html_text = f"<b>P_{pid}</b> {safe_title}\nBy: {safe_creator}\n{safe_snippet}..."
            await message.answer(
                html_text,
                reply_markup=vote_proposal_keyboard(pid),
                parse_mode=ParseMode.HTML
            )        
        except Exception as e:
            logger.exception("create_proposal failed")
            await message.answer(f"❌ Failed to create proposal: {escape(str(e))}")

    # Clear FSM state
    await state.clear()


@router.message(lambda msg: msg.text is not None, StateFilter(ProposalStates.waiting_for_title))
async def proposal_title_received(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Title cannot be empty. Send text for the title.")
        return

    await state.update_data(title=title)
    await state.set_state(ProposalStates.waiting_for_body)
    await message.answer(f"Title saved: {title}\nSend body for this proposal (one message).", reply_markup=cancel_keyboard(), parse_mode=None)


@router.message(lambda msg: msg.text is not None, StateFilter(ProposalStates.waiting_for_body))
async def proposal_body_received(message: types.Message, state: FSMContext):
    body = message.text.strip()
    if not body:
        await message.answer("Body cannot be empty. Send text for the body.")
        return

    await state.update_data(body=body)
    await proposal_done(message, state)


# -------------------------
# Comment
# -------------------------
@router.message(Command("comment"))
async def cmd_comment(message: types.Message):
    """
    /comment p_<proposal_id> <text>
    /comment c_<comment_id> <text>
    """
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /comment p_<id> <text>  OR  /comment c_<id> <text>", parse_mode=None)
        return
    id_part = parts[1]
    text = parts[2].strip()
    if id_part.startswith("p_"):
        pid = int(id_part[2:])
        parent = None
        async for db in get_async_session():
            try:
                comment = await create_comment(db=db, proposal_id=pid, user_id=message.from_user.id, text=text, parent_comment_id=None)
                cid = getattr(comment, "id", None) or (comment.get("id") if isinstance(comment, dict) else None)
                await message.answer(f"Comment added to proposal P_{pid}: C_{cid}", parse_mode=None)
            except Exception as e:
                logger.exception("create_comment failed")
                await message.answer(f"Failed to add comment: {e}")
    elif id_part.startswith("c_"):
        cid = int(id_part[2:])
        # Need to know which proposal this comment belongs to; service should handle parent linkage
        async for db in get_async_session():
            try:
                comment = await create_comment(db=db, proposal_id=0, user_id=message.from_user.id, text=text, parent_comment_id=cid)
                cid2 = getattr(comment, "id", None) or (comment.get("id") if isinstance(comment, dict) else None)
                await message.answer(f"Reply added: C_{cid2}")
            except Exception as e:
                logger.exception("create_comment_async failed (reply)")
                await message.answer(f"Failed to add reply: {e}")
    else:
        await message.answer("ID must be p_<id> or c_<id>", parse_mode=None)

# -------------------------
# Vote
# -------------------------
@router.message(Command("vote"))
async def cmd_vote(message: types.Message):
    """
    /vote p_<id> 1-10
    /vote c_<id> yes/no/1/0
    """
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /vote p_<id> <1-10>  OR  /vote c_<id> <yes|no|1|0>", parse_mode=None)
        return
    id_part = parts[1]
    val = parts[2].lower()

    async for db in get_async_session():
        try:
            if id_part.startswith("p_"):
                pid = int(id_part[2:])
                score = int(val) if val.isdigit() else None
                if score is None or not (1 <= score <= 10):
                    await message.answer("Proposal votes must be 1-10")
                    return
                await vote_proposal(db=db, proposal_id=pid, voter_user_id=message.from_user.id, score=score)
                await message.answer("Proposal vote recorded.")
            elif id_part.startswith("c_"):
                cid = int(id_part[2:])
                vote_bool = True if val in ("yes","y","1","true") else False
                await vote_comment(db=db, comment_id=cid, voter_user_id=message.from_user.id, vote=vote_bool)
                await message.answer("Comment vote recorded.")
            else:
                await message.answer("ID must be p_<id> or c_<id>", parse_mode=None)
        except Exception as e:
            logger.exception("vote failed")
            await message.answer(f"Failed to record vote: {e}")

# -------------------------
# Representative
# -------------------------
@router.message(Command("representative"))
async def cmd_rep(message: types.Message):
    """
    /representative <id|@username>
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /representative <user_id|@username>")
        return
    arg = parts[1].strip()
    async for db in get_async_session():
        try:
            candidate_id = None
            if arg.startswith("@"):
                candidate_id = await get_id_from_username(db, arg[1:])
                if candidate_id is None:
                    await message.answer("Cannot resolve username to id.")
                    return
            else:
                candidate_id = int(arg)
            user = get_user(message.from_user_id)
            await vote_representative_repo(db=db, group_id=user["group_id"], voter_user_id=user["user_id"], candidate_user_id=candidate_id)
            await message.answer("Representative vote recorded.")
        except Exception as e:
            logger.exception("vote representative failed")
            await message.answer(f"Failed to vote representative: {e}")

# -------------------------
# Tree display
# -------------------------
@router.message(Command("tree"))
async def cmd_tree(message: types.Message, fractal_id: str | None = None):
    """
    /tree                -> proposals tree for active group (requires active fractal)
    /tree p_<id>         -> specific proposal
    /tree c_<id>         -> (future) comment subtree
    """

    print (message.text)
    parts = message.text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else None
    print (arg)

    async for db in get_async_session():
        try:
            if arg is None:
                # need user's active group from FSM or in-memory
                # quick try: ask user to /join first
                await message.answer("Showing tree for active group is not implemented unless you have joined a fractal and group. Use /join first.")
                return
            if arg.startswith("p_"):
                pid = int(arg[2:])
#                print("get tree")
                tree = await get_proposal_comments_tree(db=db, proposal_id=pid)
                # tree formatting placeholder
                print(tree)
                await message.answer(f"Proposal P_{pid} tree (placeholder):\n")
            elif arg.startswith("c_"):
                cid = int(arg[2:])
                await message.answer("Comment subtree not yet implemented.")
            else:
                await message.answer("Invalid /tree argument. Use /tree, /tree p_<id> or /tree c_<id>", parse_mode=None)
        except Exception as e:
            logger.exception("tree failed")
            await message.answer(f"Failed to get tree: {e}")


message_history = {} 

@router.message(lambda m: m.reply_to_message and m.reply_to_message.from_user.is_bot)
async def handle_reply(message: types.Message):
    replied_text = message.reply_to_message.text or ""
    if not replied_text:
        return

    last_line = replied_text.splitlines()[-1].strip()

    original_sender = None
    original_message = last_line

    # Case 1: plain "Name: text"
    if "💬 " in last_line and not last_line.startswith("💬 Reply:"):
        original_sender, original_message = last_line.split("💬 ", 1)

    # Case 2: our own "💬 Reply: text"
    elif last_line.startswith("💬 Reply:"):
        original_message = last_line.replace("💬 Reply:", "", 1).strip()
        # Extract sender from the header line instead of using bot username
        header = replied_text.splitlines()[0] if replied_text.splitlines() else ""
        # header looks like: "➡️ MikaelAnanda replied to MikaelAnanda:" or similar
        if " replied to " in header:
            h = header.replace("➡️", "").strip()
            parts = h.split(" replied to ")
            # parts[0] is replier, parts[1] ends with ':'
            original_sender = parts[0].strip()

    # Fallback: if still no sender, use the current user (never the bot)
    if not original_sender:
        original_sender = message.from_user.username or "User"

    user_info = await get_user_info(str(message.from_user.id))
    if not user_info:
        return

    group_id = int(user_info.get("group_id", 0))
    if group_id == 0:
        return

    async for db in get_async_session():
        try:
            telegram_ids = []
            members = await get_group_members_repo(db, group_id)
            for member in members:
                user = await get_user(db, member.user_id)
                if not user or not user.telegram_id:
                    continue
                try:
                    telegram_ids.append(int(user.telegram_id))
                except ValueError:
                    continue
        except Exception:
            return

    if original_message:
        reply_text = (
            f"➡️ {user_info.get('username', 'User')} replied to {original_sender}:\n"
            f"📝 Original: {original_message}\n"
            f"💬 Reply: {message.text}"
        )
    else:
        reply_text = (
            f"➡️ {user_info.get('username', 'User')} replied to {original_sender}:\n"
            f"💬 Reply: {message.text}"
        )

    await send_message_to_telegram_users(telegram_ids, reply_text)

# 2) SECOND: catch‑all echo
@router.message()
async def echo_all(message: types.Message):
    if not message.text:
#        await message.answer(
#            f"Received non-text message of type: {message.content_type}"
#        )
        return

    user_info = await get_user_info(str(message.from_user.id))  # Or your source
    if not user_info:
#        await message.answer("User not found or no group assigned.")  # Or log/return
        return

    group_id = int(user_info.get("group_id", 0))
    if group_id == 0:
#        await message.answer("No group assigned to user.")
        return

    message_text = f"👋 {user_info.get('username', 'User')} wrote:\n💬 {message.text}"

    async for db in get_async_session():
        try:
            telegram_ids = []
            members = await get_group_members_repo(db, group_id)
            for member in members:
                user = await get_user(db, member.user_id)
                if not user or not user.telegram_id:
                    continue
                try:
                    telegram_ids.append(int(user.telegram_id))
                except ValueError:
                    continue
        except Exception as e:
            await message.answer(f"Error getting members: {e}")
            return

    await send_message_to_telegram_users(telegram_ids, message_text)