#~~~{"id":"70524","variant":"standard","title":"Async Fractal Service Layer"} 
# app/services/fractal_service.py
from typing import List, Optional, Dict
from datetime import datetime, timezone
from config.settings import settings
from fastapi.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from states import connected_clients

from repositories.fractal_repos import (
    get_user_by_telegram_id_repo,
    create_user_repo,
    get_user_repo,
    create_fractal_repo,
    add_fractal_member_repo,
    get_active_fractal_members_repo,
    create_round_repo,
    create_group_repo,
    add_group_member_repo,
    get_group_members_repo,
    add_proposal_repo,
    add_comment_repo,
    vote_proposal_repo,
    vote_comment_repo,
    get_proposals_for_group_repo,
    get_comments_for_proposal_repo,
    get_top_proposals_repo,
    close_round_repo,
    save_proposal_score_repo,
    save_comment_score_repo,
    get_groups_for_round_repo,
    select_representative_repo,
    vote_representative_repo,
    get_votes_for_comment_repo,
    get_votes_for_proposal_repo,
    get_round_repo,
    get_fractal_repo,
    get_group_repo,
    get_group_member_repo,
    set_active_fractal_repo,
    get_user_info_by_telegram_id_repo,
    create_fractal_repo,
    create_user_repo,
    get_fractal_member_repo,
    get_fractal_members_repo,
    get_fractal_from_name_or_id_repo,
    get_next_card_repo,
    get_all_cards_repo,
    get_or_build_round_tree_repo

)
from domain import fractal_logic as domain

from typing import Iterable, Protocol
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.service import send_message_to_telegram_users, send_button_to_telegram_users

class HasUserId(Protocol):
    user_id: int


# Wrapper

async def create_fractal(
    db: AsyncSession,
    name: str,
    description: str,
    start_date: datetime,
    status: Optional[str] = "waiting",
    settings: Optional[dict] = None
):
    """
    Create a new Fractal in the repo
    """
    return await create_fractal_repo(
        db,
        name,
        description,
        start_date,
        status,
        settings)

async def get_group_members(db: AsyncSession, group_id: int):
    """
    Returns a list of GroupMember objects for the given group_id.
    """
    return await get_group_members_repo(db, group_id)

async def create_user(db: AsyncSession, user_info: Dict):
    return await create_user_repo(db, user_info)


async def join_fractal(db: AsyncSession, user_info: Dict, fractal_id: int):
    """
    Service: Join user to fractal with business validation.
    Raises ValueError for business rule violations.
    """
    # 1. Get fractal via REPO
    fractal = await get_fractal_repo(db, fractal_id)
    if not fractal:
        raise ValueError("Fractal not found")
    
    if fractal.status != "waiting":
        raise ValueError(f"Fractal is not open for joining (status: {fractal.status})")
    
    # 2. Get or create user
    telegram_id = user_info.get("telegram_id")
    if not telegram_id:
        raise ValueError("telegram_id required")
    
    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        user = await create_user(db, user_info)
    
    # 3. Check membership via REPO
    existing_member = await get_fractal_member_repo(db, fractal_id, user.id)
    if existing_member:
        raise ValueError("User is already a member of this fractal")
    
    # 4. Execute operations
    await add_fractal_member_repo(db, fractal_id, user.id)
    await set_active_fractal_repo(db, user.id, fractal_id)



    return user

async def start_fractal(db: AsyncSession, fractal_id: int):
    """
    Mark fractal active and start first round.
    """
    members = await get_active_fractal_members_repo(db, fractal_id)
    round_0 = await start_round(db, fractal_id, level=0, members=members)
    # 1️⃣ Notify all members that the fractal/round has started
    print ("🚀 Your fractal round has started!")
    text = "🚀 Your fractal round has started!"
    await send_button_to_fractal_members(db, text, "Dashboard", fractal_id)
    print ("🚀 Your fractal round has started!")
    await send_message_to_fractal_web_app_members(db, fractal_id, text)

    return round_0


async def send_message_to_members(
    db: AsyncSession,
    members: Iterable[HasUserId],
    text: str,
) -> None:
    """
    Given any member objects with .user_id (FractalMember, GroupMember, etc.),
    resolve Users and send them a Telegram message.
    """
    telegram_ids: list[int] = []

    for member in members:
        user = await get_user(db, member.user_id)
        if not user or not user.telegram_id:
            continue
        try:
            telegram_ids.append(int(user.telegram_id))
        except ValueError:
            continue

    if telegram_ids:
        await send_message_to_telegram_users(telegram_ids, text)


async def send_message_to_web_app_members(
    db: AsyncSession,
    members: Iterable[HasUserId],
    text: str,
    type: str,
) -> None:
    

    print ("send_message_to_web_app_members")

    """
    Given any member objects with .user_id (FractalMember, GroupMember, etc.),
    resolve Users and send them a Telegram message.
    """
    telegram_ids: list[int] = []

    for member in members:
        user = await get_user(db, member.user_id)
        if not user or not user.telegram_id:
            continue
        try:
            telegram_ids.append(int(user.telegram_id))
        except ValueError:
            continue

    if telegram_ids:
        await send_message_to_web_app_users(telegram_ids, text, type)


async def send_message_to_group(db: AsyncSession, group_id: int, text: str) -> None:
    members = await get_group_members_repo(db, group_id)
    await send_message_to_members(db, members, text)

async def send_button_to_group(db: AsyncSession, group_id: int, text: str, button, fractal_id, data=0) -> None:
    print("send to group", group_id)
    members = await get_group_members_repo(db, group_id)
    await send_button_to_fractal_members(db, text, button, fractal_id, data=0)

async def send_message_to_fractal_members(db: AsyncSession, fractal_id: int, text: str) -> None:
    members = await get_fractal_members_repo(db, fractal_id)
    await send_message_to_members(db, members, text)


async def send_message_to_web_app_group(db: AsyncSession, group_id: int, text: str, event_type="message") -> None:
    members = await get_group_members_repo(db, group_id)
    await send_message_to_web_app_members(db, members, text, event_type)

async def send_message_to_fractal_web_app_members(db: AsyncSession, fractal_id: int, text: str, event_type="") -> None:
    members = await get_fractal_members_repo(db, fractal_id)
    await send_message_to_web_app_members(db, members, text, event_type)

async def send_button_to_fractal_members(db, text, button, fractal_id, data=0):
    members = await get_fractal_members_repo(db, fractal_id)
    telegram_ids: list[int] = []

    for member in members:
        user = await get_user(db, member.user_id)
        if not user or not user.telegram_id:
            continue
        try:
            telegram_ids.append(int(user.telegram_id))
        except ValueError:
            continue

    if telegram_ids:
        await send_button_to_telegram_users(telegram_ids, text, button, fractal_id, data)




# ----------------------------
# Round / Group Workflow
# ----------------------------

async def start_round(db: AsyncSession, fractal_id: int, level: int, members: List):
    """
    Create a round and divide users into groups.
    """
    print("starting round")
    round_obj = await create_round_repo(db, fractal_id, level)

    user_ids = [m.user_id for m in members]
#    group_size = 8  # Could come from fractal settings

    fractal = await get_fractal(db, fractal_id)
    settings_dict = fractal.settings or {}

    group_size = settings_dict.get("group_size")
    if group_size is None:
        group_size = settings.GROUP_SIZE_DEFAULT

    groups_flat = domain.divide_into_groups(user_ids, group_size)

    groups = []
    for grp_users in groups_flat:
        grp = await create_group_repo(db, fractal_id, round_obj.id, level)
        print("crate group")

        for uid in grp_users:
            await add_group_member_repo(db, grp.id, uid)
            print("add group member")
        groups.append(grp)
    return round_obj

async def get_groups_for_round(db: AsyncSession, round_id: int):
    return await get_groups_for_round_repo(db, round_id)

# ----------------------------
# Close Round
# ----------------------------
async def close_round(db: AsyncSession, round_id: int):
    """
    Close a round: mark it closed and calculate totals for proposals and comments.
    Saves scores per level as lists in JSONB.
    """
    # Step 1: Mark round as closed
    round_obj = await close_round_repo(db, round_id)

    # Step 2: Get all groups for this round
    groups = await get_groups_for_round_repo(db, round_obj.id)

    # Step 3: For each group, process proposals and comments
    for group in groups:
        # Get all proposals explicitly
        proposals = await get_proposals_for_group_repo(db, group.id)
        for p in proposals:
            # Explicitly load votes for this proposal
            proposal_votes = await get_votes_for_proposal_repo(db, p.id)
            total_score = sum(v.score for v in proposal_votes)
            # Save proposal score per level
            await save_proposal_score_repo(db, p.id, round_obj.level, total_score)

            # Explicitly load comments for this proposal
            comments = await get_comments_for_proposal_repo(db, p.id)
            for c in comments:
                comment_votes = await get_votes_for_comment_repo(db, c.id)
                yes_count = sum(1 for v in comment_votes if v.vote)
                no_count = sum(1 for v in comment_votes if not v.vote)
                comment_score = yes_count - no_count
                await save_comment_score_repo(db, c.id, round_obj.level, comment_score)

    # Step 4: Promote to next round
    new_round = await promote_to_next_round(db, round_obj.id, round_obj.fractal_id)

    groups = await get_groups_for_round(db, new_round.id)
    text = f"The Next Round has started!"
    for g in groups:
        await send_button_to_group(db, g.id, text, "Dashboard", round_obj.fractal_id)
        await send_message_to_web_app_group(db, g.id, text)

    # Step 5: Return the new round if created, else the closed round
    return new_round if new_round else round_obj

# ----------------------------
# Promote to Next Round
# ----------------------------
async def promote_to_next_round(db: AsyncSession, prev_round_id: int, fractal_id: int):
    """
    Start next round if previous round has more than 2 groups.
    Only representatives join new groups.
    Top proposals from previous round are promoted to new round.
    """
    # Step 1: Get all groups in previous round
    prev_groups = await get_groups_for_round(db, prev_round_id)
    if len(prev_groups) <= 2:
        return None  # No next round

    # Step 2: Gather representatives from each group
    rep_user_ids = []
    for g in prev_groups:
        members = await get_group_members(db, g.id)
        member_ids = [m.user_id for m in members]
        rep_id = await select_representative_repo(db, g.id)  # highest voted rep
        if rep_id:
            rep_user_ids.append(rep_id)

    # Step 3: Create new round
    prev_round_obj = await get_round_repo(db, prev_round_id)
    next_level = prev_round_obj.level + 1
    new_round = await create_round_repo(db, fractal_id, next_level)

    # Step 4: Divide representatives into new groups

    fractal = await get_fractal(db, fractal_id)
    settings_dict = fractal.settings or {}

    group_size = settings_dict.get("group_size")
    if group_size is None:
        group_size = settings.GROUP_SIZE_DEFAULT

    groups_flat = domain.divide_into_groups(rep_user_ids, group_size)
    new_groups = []
    for grp_users in groups_flat:
        grp = await create_group_repo(db, fractal_id, new_round.id, next_level)
        for uid in grp_users:
            await add_group_member_repo(db, grp.id, uid)
        new_groups.append(grp)

    # Step 5: Promote top proposals from previous round
    top_count = 2  # can come from fractal settings
    for g_prev, grp_new in zip(prev_groups, new_groups):
        top_props = await get_top_proposals_repo(db, g_prev.id, top_count)  # g_prev.id is group_id
        for p in top_props:
            p.round_id = new_round.id
            p.group_id = grp_new.id
            await db.commit()

    return new_round


# ----------------------------
# Proposal / Comment Workflow
# ----------------------------
async def create_proposal(db: AsyncSession, fractal_id: int, group_id: int, round_id: int,
                                title: str, body: str, creator_user_id: int):
    # send ws to group about new proposal
    await send_message_to_web_app_group(db, group_id, "new proposals ready", "refresh")
    return await add_proposal_repo(db, fractal_id, group_id, round_id, title, body, creator_user_id)


async def create_comment(db: AsyncSession, proposal_id: int, user_id: int, text: str,
                               parent_comment_id: Optional[int] = None, group_id: Optional[int] = None):
    await send_message_to_web_app_group(db, group_id, "new comments ready", "refresh")    
    return await add_comment_repo(db, proposal_id, user_id, text, parent_comment_id, group_id)


# ----------------------------
# Voting Workflow
# ----------------------------
async def vote_proposal(db: AsyncSession, proposal_id: int, voter_user_id: int, score: int):
    return await vote_proposal_repo(db, proposal_id, voter_user_id, score)


async def vote_comment(db: AsyncSession, comment_id: int, voter_user_id: int, vote: int):
    return await vote_comment_repo(db, comment_id, voter_user_id, vote)



# ----------------------------
# Fetch for Bot Layer
# ----------------------------
async def get_proposals_comments_tree(db: AsyncSession, group_id: int):
    """
    Fetch all proposals for a group with their votes and nested comments including votes.
    Returns:
        [
            {
                "proposal": Proposal,
                "votes": {"raw": List[ProposalVote], "total": int},
                "comments": [
                    {
                        "comment": Comment,
                        "votes": {"raw": List[CommentVote], "yes": int, "no": int},
                        "replies": [ ... same structure recursively ... ]
                    }
                ]
            }
        ]
    """
    proposals = await get_proposals_for_group_repo(db, group_id)
    tree_result = []

    for p in proposals:
        # Proposal votes
        proposal_votes = await get_votes_for_proposal_repo(db, p.id)
        total_score = sum(v.score for v in proposal_votes)
        proposal_data = {
            "proposal": p,
            "votes": {
                "raw": proposal_votes,
                "total": total_score
            },
            "comments": []
        }

        # Comments
        comments = await get_comments_for_proposal_repo(db, p.id)
        comment_map = {}
        for c in comments:
            votes = await get_votes_for_comment_repo(db, c.id)
            yes_count = sum(1 for v in votes if v.vote)
            no_count = sum(1 for v in votes if not v.vote)
            comment_map[c.id] = {
                "comment": c,
                "votes": {
                    "raw": votes,
                    "yes": yes_count,
                    "no": no_count
                },
                "replies": []
            }

        # Build tree structure
        for c in comments:
            if c.parent_comment_id and c.parent_comment_id in comment_map:
                comment_map[c.parent_comment_id]["replies"].append(comment_map[c.id])

        top_level_comments = [v for k, v in comment_map.items() if v["comment"].parent_comment_id is None]
        proposal_data["comments"] = top_level_comments

        tree_result.append(proposal_data)

    return tree_result

# ----------------------------
# Fetch for Bot Layer
# ----------------------------
async def get_proposal_comments_tree(db: AsyncSession, proposal_id: int):
    """
    Fetch proposals with nested comments and votes for a group.
    """
    result = []
    comments = await get_comments_for_proposal_repo(db, proposal_id)
    comment_dicts = [{"comment": c, "votes": c.votes} for c in comments]
    tree = domain.build_comment_tree(comment_dicts)
    result.append({"proposal": "test", "comments": tree})
    return result



# ----------------------------
# Representative Selection
# ----------------------------
async def select_representative_from_vote(db: AsyncSession, group_id: int):
    return select_representative_repo(db, group_id)


async def vote_representative(db: AsyncSession, group_id: int, voter_user_id: int, candidate_user_id: int):
    # You can add extra logic here, e.g., check if voter belongs to the group
    return await vote_representative_repo(db, group_id, voter_user_id, candidate_user_id)

# Add to services/fractal_service.py:
async def get_user_by_telegram_id(db: AsyncSession, telegram_id: str):
    # Implementation using repo
    return await get_user_by_telegram_id_repo(db, telegram_id)

# Add to services/fractal_service.py:
async def get_user_info_by_telegram_id(db: AsyncSession, telegram_id: str):
    # Implementation using repo
    return await get_user_info_by_telegram_id_repo(db, telegram_id)

async def get_fractal(db: AsyncSession, fractal_id: int):
    return await get_fractal_repo(db, fractal_id)

async def get_user(db: AsyncSession, user_id: int):
    return await get_user_repo(db, user_id)

async def get_fractal_member(db: AsyncSession, user_id: int):
    return await get_fractal_member_repo(db, user_id)


async def get_next_card(db: AsyncSession, group_id: int, current_user_id: int) -> Optional[Dict]:
    """Service: Get next unvoted card for user."""
    return await get_next_card_repo(db, group_id, current_user_id)

async def get_all_cards(db: AsyncSession, group_id: int, current_user_id: int) -> Optional[Dict]:
    """Service: Get next unvoted card for user."""
    return await get_all_cards_repo(db, group_id, current_user_id)


async def send_message_to_web_app_users(telegram_ids: list[int], text: str, event_type="message"):
    for user_id in telegram_ids:
        if(int(user_id)>=20000 and int(user_id)<300000):
            continue
        try:
            """Call this from your bot/game logic"""
            user_id = str(user_id)
            print("Sending")
            print(f"DEBUG: user_id type: {type(user_id)}, value: {repr(user_id)}")
            print(f"DEBUG: connected_clients type: {type(connected_clients)}")
            print(f"DEBUG: connected_clients keys: {list(connected_clients.keys())}")
            print(f"DEBUG: connected_clients keys types: {[type(k) for k in connected_clients.keys()]}")
            print(f"DEBUG: user_id in connected_clients: {user_id in connected_clients}")
            if user_id in connected_clients:
                print ("Sent")
                event = {"type": event_type, "message": text, "timestamp": datetime.now(timezone.utc).isoformat()}
                disconnected = []
                
                for ws in connected_clients[user_id][:]:  # Copy list
                    try:
                        # ✅ CHECK IF STILL OPEN
                        if ws.client_state == WebSocketState.CONNECTED:
                            await ws.send_json(event)
                            print("✅ send success")
                        else:
                            print("⚠️ WS already closed")
                            disconnected.append(ws)
                    except Exception as e:
                        print(f"❌ send failed: {e}")
                        disconnected.append(ws)
                
                # Cleanup
                for ws in disconnected:
                    connected_clients[user_id].remove(ws)

        except Exception as e:
            print(f"Failed to send to {user_id}: {e}")


