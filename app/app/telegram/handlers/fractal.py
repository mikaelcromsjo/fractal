from aiogram import types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import Router
from app.services._fractal_service import create_level_groups  # example usage
from app.services._fractal_service import add_proposal  # might be used later

router = Router()


@router.message(Command("create_fractal"))
async def cmd_create_fractal(message: types.Message):
    """
    Expect: /create_fractal fractal_name description start_date
    This handler keeps parsing simple space-split; for long descriptions
    you can instead use FSM (not implemented here).
    """
    parts = message.text.split(" ", 3)
    if len(parts) < 4:
        await message.reply("Usage: /create_fractal fractal_name description start_date")
        return

    _, fractal_name, description, start_date = parts
    # call your domain/service function that creates a fractal
    # Example: fractal = create_fractal(db, name=fractal_name, description=description, start_date=start_date)
    # For now just respond.
    await message.reply(f"Fractal '{fractal_name}' created. Join using /join {fractal_name}")


@router.message(Command("join"))
async def cmd_join(message: types.Message):
    """
    /join fractal_name
    Register user as member (private/secret join message)
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Usage: /join fractal_name")
        return
    fractal_name = parts[1].strip()
    # TODO: call service to add member to fractal by telegram user id
    # e.g. add_member(db, fractal_name, telegram_user_id=message.from_user.id)
    await message.answer(f"Welcome — you joined '{fractal_name}'. We will start at <start_date>. Type /help for a list of commands")
