from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.telegram.states import ProposalStates
from app.telegram.keyboards import vote_keyboard, list_more_keyboard, show_hidden_keyboard
from app.services import _fractal_service  # uses the functions you provided

router = Router()


@router.message(Command("proposal"))
async def cmd_proposal_start(message: types.Message, state: FSMContext):
    """
    Start FSM flow to create a proposal.
    Use:
      /proposal
    Bot will then ask for title, then body (up to 2000 chars). Type /done when finished sending body.
    """
    await message.answer("Creating a proposal. Send title:")
    await state.set_state(ProposalStates.waiting_for_title)


@router.message(lambda message: True, state=ProposalStates.waiting_for_title)
async def proposal_title_received(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Got title. Now send body text. You can send multiple messages. When finished, send /done")
    await state.set_state(ProposalStates.waiting_for_body)
    await state.update_data(body="")


@router.message(Command("done"), state=ProposalStates.waiting_for_body)
async def proposal_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title")
    body = data.get("body", "").strip()
    if not title or not body:
        await message.answer("Title or body missing. Cancelled.")
        await state.clear()
        return

    if len(body) > 2000:
        await message.answer("Body is too long (max 2000 chars). Please shorten and try again.")
        await state.clear()
        return

    # TODO: add real db/session management; example: db = get_db_session(); fractal_service.add_proposal(...)
    # For now we call the service as if it accepts a db object set to None (adjust when implementing)
    try:
        new_id = _fractal_service.add_proposal(
            db=None,
            fractal_id=0,
            group_id=0,
            round_id=0,
            title=title,
            body=body,
            creator_user_id=message.from_user.id,
            ptype="base",
        )
        await message.answer(f"Proposal created with id {new_id}")
    except Exception as e:
        await message.answer(f"Failed to create proposal: {e}")

    await state.clear()


@router.message(lambda message: message.text and message.text.startswith("/comment"))
async def cmd_comment(message: types.Message):
    """
    /comment proposal_id/comment_id comment
    If comment_id is omitted or zero -> top-level comment on proposal.
    """
    # parse
    parts = message.text.split(" ", 2)
    if len(parts) < 3:
        await message.reply("Usage: /comment proposal_id[/parent_comment_id] comment")
        return
    id_part = parts[1]
    comment_text = parts[2].strip()
    if "/" in id_part:
        proposal_id_str, parent_id_str = id_part.split("/", 1)
        parent_id = int(parent_id_str) if parent_id_str else None
    else:
        proposal_id_str = id_part
        parent_id = None
    proposal_id = int(proposal_id_str)
    # TODO: resolve user id mapping (message.from_user.id) -> internal user id
    try:
        comment_id = _fractal_service.add_comment(db=None, proposal_id=proposal_id, user_id=message.from_user.id, text=comment_text, parent_comment_id=parent_id)
        await message.answer(f"Comment added with id {comment_id}")
    except Exception as e:
        await message.answer(f"Error adding comment: {e}")


@router.message(lambda message: message.text and message.text.startswith("/vote"))
async def cmd_vote(message: types.Message):
    """
    /vote proposal_id/comment_id value
    comment_id can be 0 or omitted.
    value is 1-10 or yes/no
    """
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Usage: /vote proposal_id[/comment_id] value")
        return
    id_part = parts[1]
    value = parts[2].lower()
    if "/" in id_part:
        proposal_id_str, comment_id_str = id_part.split("/", 1)
        comment_id = int(comment_id_str) if comment_id_str else None
    else:
        proposal_id_str = id_part
        comment_id = None
    proposal_id = int(proposal_id_str)
    try:
        if comment_id:
            # comment votes are yes/no (cast_comment_vote)
            vote_bool = True if value in ("yes", "y", "true", "1") else False
            _fractal_service.cast_comment_vote(db=None, comment_id=comment_id, voter_user_id=message.from_user.id, vote=vote_bool)
            await message.answer("Comment vote recorded.")
        else:
            # proposal vote is 1-10
            score = int(value) if value.isdigit() else None
            if score is None or not (1 <= score <= 10):
                await message.answer("Proposal votes must be an integer 1-10.")
                return
            _fractal_service.cast_proposal_vote(db=None, proposal_id=proposal_id, voter_user_id=message.from_user.id, score=score)
            await message.answer("Proposal vote recorded.")
    except Exception as e:
        await message.answer(f"Error recording vote: {e}")


@router.message(Command("new"))
async def cmd_new(message: types.Message):
    """
    Return proposals/comments that the user hasn't voted on.
    For brevity, this fetch is done via a service function you should implement.
    """
    # TODO: call a service function to get new items for this user
    # items = fractal_service.get_new_items_for_user(db, user_id=message.from_user.id)
    # for each item: send message + vote keyboard
    await message.answer("Not implemented: /new - service must return items you haven't voted on.")


@router.message(Command("list"))
async def cmd_list(message: types.Message):
    """
    /list
    /list proposal_id
    /list proposal_id/comment_id
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) == 1:
        # list all proposals and comments (paginated)
        await message.answer("Not implemented: full list. Implement via service that returns nested structure.")
        return

    target = parts[1].strip()
    if "/" in target:
        proposal_id_str, comment_id_str = target.split("/", 1)
        proposal_id = int(proposal_id_str)
        comment_id = int(comment_id_str)
        await message.answer(f"Not implemented: list proposal {proposal_id} comment {comment_id}")
    else:
        proposal_id = int(target)
        await message.answer(f"Not implemented: list proposal {proposal_id}")
