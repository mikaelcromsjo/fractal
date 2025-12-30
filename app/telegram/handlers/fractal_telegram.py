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

from infrastructure.db.session import get_async_session

from telegram.service import send_message_to_telegram_users, send_button_to_telegram_users

from services.fractal_service import (
    create_fractal,
    join_fractal,
    start_fractal,
    close_round,
    get_fractal_from_name_or_id_repo,
    send_message_to_group,
    get_group_members_repo,
    get_user,
)

from infrastructure.db.session import get_async_session
from services.fractal_service import (
    create_proposal,
    create_comment,
    vote_proposal,
    vote_comment,
    vote_representative,
    get_proposals_comments_tree,
    get_proposal_comments_tree,
    get_user_by_telegram_id,
    get_user_info_by_telegram_id
)

from telegram.states import ProposalStates, CreateFractal
from telegram.keyboards import share_to_group_button, create_keyboard, vote_comment_keyboard, vote_proposal_keyboard, list_more_keyboard, show_hidden_keyboard, cancel_keyboard, fractal_actions_menu, help_menu
from aiogram.filters import CommandStart


logger = logging.getLogger(__name__)
router = Router()


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
    """Creates a 'Join Fractal' button to share to groups."""
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
            [InlineKeyboardButton(text="🚀 Join Fractal", url=join_url)]
        ]
    )
    start_date = fractal.start_date.strftime("%A %H:%M, %B %d, %Y")
    minutes = int(fractal.meta["round_time"]) / 60
    round_time = f"{int(minutes)} minutes" if minutes.is_integer() else f"{minutes} minutes"

    share_text = (
                   f"🎉 Click to Join Fractal Meeting: \"{sanitize_text(fractal.name)}\"\n\n"
                    f"📝 {sanitize_text(fractal.description)}\n\n"
                    f"📅 {start_date}\n\n"
                    f"⏰ {round_time} rounds"
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
        "❌ Operation canceled.",
        reply_markup=default_menu()
    )

# -----------------------
# Helpers
# -----------------------


async def get_user_info(telegram_id) -> Dict:
    print("get_user_info")
    async for db in get_async_session():
            try:
                user_info = await get_user_info_by_telegram_id(db, str(telegram_id))
                print ("got user_info", user_info)
                return user_info
            except Exception:
                print("failed in get_user_info")

                logger.exception("Failed getting user data")
                return {}

def format_proposal_preview(proposal: Dict[str, Any]) -> str:
    """Return HTML formatted preview of a proposal (placeholder)."""
    pid = getattr(proposal, "id", None) or proposal.get("id")
    title = getattr(proposal, "title", "") or proposal.get("title", "")
    creator = getattr(proposal, "creator_user_id", "") or proposal.get("creator_user_id", "")
    snippet = (getattr(proposal, "body", "") or proposal.get("body", ""))[:200].replace("<", "&lt;")
    return f"<b>P_{pid}</b> {title}\nBy: {creator}\n{snippet}..."



def parse_start_date(s: str) -> Optional[datetime]:
    """
    Accept either:
      - minutes from now (e.g., "30")
      - YYYYMMDDHHMM (e.g., 202511261530)
    Returns UTC datetime or None.
    """
    if not s:
        return None
    s = s.strip()
    try:
        if re.fullmatch(r"\d{1,4}", s):
            minutes = int(s)
            return datetime.now(timezone.utc) + timedelta(minutes=minutes)
        if re.fullmatch(r"\d{12}", s):
            # assume provided time is in UTC
            return datetime.strptime(s, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except Exception:
        return None
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

@router.message(Command("invite"), F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]))
async def cmd_invite_group(message: types.Message):
    fractal_id = int(message.text.split()[1])

    # in groups: NO web_app button, only URL buttons
    join_menu = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🎯 Join Fractal {fractal_id}",
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
    ]
    await bot.set_my_commands(commands)
    
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


                    break  # or return
                    
                print(f"🔍 FRACTAL STATUS: '{fractal.status}'")  # 5️⃣


                now = datetime.now(timezone.utc)

                # A fractal can only be joined if status is "waiting"
                if fractal.status.lower() != "waiting":
                    start_str = (
                        fractal.start_date.strftime("%A %H:%M, %B %d, %Y")
                        if fractal.start_date
                        else "Unknown"
                    )
                    round_time_minutes = int(fractal.meta.get("round_time", 0) / 60)
                    round_time_str = f"{round_time_minutes} min/round" if round_time_minutes else "N/A"

                    await message.answer(
                        f"❌ *This fractal isn't open for joining.*\n\n"
                        f"🆔 **Name:** {sanitize_text(fractal.name or 'Unknown')}\n"
                        f"📝 **Description:** {sanitize_text(fractal.description or 'No description')}\n"
                        f"📅 **Start:** {start_str}\n"
                        f"⏰ **Round time:** {round_time_str}\n"
                        f"📊 **Status:** {fractal.status.title()}\n\n"
                        f"⚠️ The fractal has probably already started, so joining is not possible.\n"
                        f"Please check back later once the organizer opens it again.",
                        parse_mode="Markdown",
                    )
                    return
                
                # ✅ SHOW JOIN MENU (like your earlier code!)
                builder = InlineKeyboardBuilder()
                builder.button(text=f"🙋 Join Fractal", callback_data=f"join:{fractal.id}")
                button = builder.as_markup()

                start_date = fractal.start_date.strftime("%A %H:%M, %B %d, %Y")
                minutes = fractal.meta.get("round_time", 0) / 60
                round_time = f"{int(minutes)} minutes" if minutes.is_integer() else f"{minutes:.1f} minutes"

                await message.answer(
                    f"🎉 Click to Join Fractal Meeting: \"{sanitize_text(fractal.name)}\"\n\n"
                    f"📝 {sanitize_text(fractal.description)}\n\n"
                    f"📅 {start_date}\n\n"
                    f"⏰ {round_time} rounds", 
                    reply_markup=button, 
                    parse_mode=None
                )
                return  # ✅ Exit after showing menu
                
                
            except Exception as e:
                print(f"[ERROR] Fractal {fractal_id}: {e}")
                await message.answer("❌ Error loading fractal.")
                break
        return

    # ✅ DEFAULT /start
    await message.answer("👋 Hi, I am the Fractal Circle Bot!", reply_markup=default_menu())


@router.message(Command("help"))
async def cmd_help(message: types.Message):

    help_text = (
        "🤖 **Fractal Circle Bot** helps you organize fractal meetings in large groups.\n\n"
        "💌 In most cases, you'll be invited to join a fractal meeting that someone else created. "
        "You'll receive an invite link when that happens.\n\n"
        "🧩 If you’re a group organizer, you can also create your own fractal and invite others to join. \n\n"
        "🎯 A Fractal meeting is divided into separate rounds in which breakout groups create proposals, discuss them, and vote on them. Most participants attend only one round; only the selected representatives continue to the next round. "
        "Collaborate, connect, and grow your circle!\n\nRead more on https://FractalCircles.org"
    )
    await message.answer(help_text, reply_markup=help_menu(), parse_mode="Markdown")


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
        round_time = int(message.text.strip()) * 60
        if round_time <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Invalid round time. Enter a positive number (e.g. 30).")
        return
    
    await state.update_data(round_time=round_time)
    await message.answer(
        "📅 Finally, enter the *start date*:\n"
        "• minutes-from-now (e.g. 30)\n"
        "• or YYYYMMDDHHMM (e.g. 202511271300)",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(CreateFractal.start_date)    

@router.message(CreateFractal.start_date)
async def fsm_get_start_date(message: types.Message, state: FSMContext):
    start_date_raw = message.text.strip()
    start_date = parse_start_date(start_date_raw)

    if not start_date:
        await message.answer(
            "❌ Couldn't parse start_date.\nTry again (minutes or YYYYMMDDHHMM)."
        )
        return

    data = await state.get_data()
    name = data["name"]
    description = data["description"]
    round_time = data["round_time"]

    # Build dict for create_fractal
    meta_settings = {"round_time": round_time}

    async for db in get_async_session():
        try:
            fractal = await create_fractal(
                db=db,
                name=name,
                description=description,
                start_date=start_date,
                settings=meta_settings,
            )

            fractal_id = getattr(fractal, "id", None)
            fractal_name = getattr(fractal, "name", name)

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
            logger.exception("FSM create_fractal failed")
            await message.answer(f"⚠️ Failed to create fractal: {e}")

    await state.clear()
    return
    
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

        # Flexible description parsing
        if len(args_parts) == 4:  # name desc round start
            description = args_parts[1].strip()
            round_time = args_parts[2].strip()
            start_date_raw = args_parts[3].strip()
        elif len(args_parts) == 5 and args_parts[1].startswith('"') and args_parts[2].endswith('"'):  # name "desc" round start
            description = (args_parts[1] + " " + args_parts[2]).strip('"').strip()  # ✅ FIX 1: join quoted parts
            round_time = args_parts[3].strip()
            start_date_raw = args_parts[4].strip()
        else:
            await message.answer('Usage: /create_fractal <name> <short_desc> <round_time> <start_date>\nOR\n/create_fractal <name> "<long desc>" <round_time> <start_date>', parse_mode=None)
            return

        # Validation
        round_time_int = int(round_time) * 60 # ✅ FIX 2: moved inside try
        start_date = parse_start_date(start_date_raw)
        if not start_date:
            await message.answer("Couldn't parse start_date. Use minutes or YYYYMMDDHHMM.", parse_mode=None)
            return

        meta_settings = {"round_time": round_time_int} 

    except ValueError:
        await message.answer("round_time must be a number.", parse_mode=None)
        return
    except Exception:
        await message.answer("Failed to parse arguments.", parse_mode=None)
        return

    # ✅ FIX 4: INDENTATION - move creation inside try block
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
                f"`https://t.me/{settings.bot_username}?start=fractal_{fractal_id}`"  # ✅ FIX 5: use settings['bot_username']? No - use global settings
            )

            # ✅ FIX 6: Use global settings.bot_username
            share_text = share_text.format(bot_username=settings.bot_username) if 'bot_username' in settings else (
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

            round_time_minutes = int(fractal.meta.get("round_time", 0) / 60)
            round_time_str = f"{round_time_minutes} min/round" if round_time_minutes else "N/A"


            await message.answer(
                f"❌ *This fractal isn't open for joining.*\n\n"
                f"🆔 **Name:** {sanitize_text(fractal.name or 'Unknown')}\n"
                f"📝 **Description:** {sanitize_text(fractal.description or 'No description')}\n"
                f"📅 **Start:** {start_str}\n"
                f"⏰ **Round time:** {round_time_str}\n"
                f"📊 **Status:** {fractal.status.title()}\n\n"
                f"⚠️ The fractal has probably already started, so joining is not possible.\n"
                f"Please check back later once the organizer opens it again.",
                parse_mode="Markdown",
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
            res = await close_round(db=db, fractal_id=fractal_id)
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
            await vote_representative(db=db, group_id=user["group_id"], voter_user_id=user["user_id"], candidate_user_id=candidate_id)
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
                print("get tree")
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

    user_info = await get_user_info(str(message.from_user.id))
    if not user_info:
#        await message.answer("User not found in database.")
        return

    group_id = int(user_info.get("group_id", 0))
    if group_id == 0:
 #       await message.answer("No group assigned to user.")
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