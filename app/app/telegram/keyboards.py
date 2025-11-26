from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def vote_keyboard(proposal_id: int, comment_id: int | None = None):
    """
    Create inline vote keyboard for scores 1-10 and yes/no fallback.
    callback_data format: vote:{proposal_id}:{comment_id or 0}:{value}
    """
    kb = InlineKeyboardMarkup(row_width=5)
    buttons = []
    for i in range(1, 11):
        cb = f"vote:{proposal_id}:{comment_id or 0}:{i}"
        buttons.append(InlineKeyboardButton(text=str(i), callback_data=cb))
    # add yes/no row
    kb.add(*buttons[:5])
    kb.add(*buttons[5:])
    kb.add(
        InlineKeyboardButton(text="Yes", callback_data=f"vote:{proposal_id}:{comment_id or 0}:yes"),
        InlineKeyboardButton(text="No", callback_data=f"vote:{proposal_id}:{comment_id or 0}:no"),
    )
    return kb


def list_more_keyboard(proposal_id: int, offset: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="Show more", callback_data=f"more:{proposal_id}:{offset}"))
    return kb


def show_hidden_keyboard(comment_id: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="Show hidden comment", callback_data=f"showhidden:{comment_id}"))
    return kb
