#~~~{"id":"70524","variant":"standard","title":"Async Fractal Service Layer"} 
# app/services/fractal_service.py
from typing import List, Optional, Dict
from datetime import datetime, timezone
from config.settings import settings
from fastapi.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from states import connected_clients
from datetime import datetime, timedelta
import asyncio


from repositories.fractal_repos import (
    get_last_group_repo,
    get_rep_votes_for_round_repo,
    save_rep_vote_repo,
    get_representatives_for_group_repo,
    get_user_rep_points_repo,
    get_votes_for_group_comments_repo,
    get_votes_for_group_proposals_repo,
    set_round_status_repo,
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
    vote_representative_repo,
    get_votes_for_comment_repo,
    get_votes_for_proposal_repo,
    get_round_repo,
    get_fractal_repo,
    get_group_repo,
    get_group_member_repo,
    set_active_fractal_repo,
    get_user_info_by_telegram_id_repo,
    create_user_repo,
    get_fractal_member_repo,
    get_fractal_members_repo,
    get_fractal_from_name_or_id_repo,
    get_next_card_repo,
    get_all_cards_repo,
    get_last_round_repo,
    close_fractal_repo,
    open_fractal_repo,
    get_waiting_fractals_repo,
    get_open_fractals_repo,
    get_or_build_round_tree_repo,
    get_fractals_repo,
    get_open_rounds_repo

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
    print ("added user:", telegram_id)
    print ("active fractal:", fractal_id)

    await add_fractal_member_repo(db, fractal_id, user.id)
    await set_active_fractal_repo(db, user.id, fractal_id)



    return user

async def start_fractal(db: AsyncSession, fractal_id: int):
    """
    Mark fractal active and start first round.
    """
    members = await get_active_fractal_members_repo(db, fractal_id)
    round_0 = await start_round(db, fractal_id, level=0, members=members)
    fractal = await get_fractal_repo(db, fractal_id)
    # 1️⃣ Notify all members that the fractal/round has started
    print ("🚀 Your fractal has started!")


    groups = await get_groups_for_round(db, round_0.id)
    print(f"Found {len(groups)} groups")
    group_members_map = {}
    total_members = 0

    for g in groups:
        members = await get_group_members(db, g.id)
        member_ids = [m.user_id for m in members]
        group_members_map[g.id] = member_ids
        total_members += len(member_ids)
        print(f"Group {g.id} members: {member_ids}")

    # Add member/group stats to message
    text = f"🚀 Fractal '{fractal.name}' has started!\n\n"
    "👥 The fractal has {total_members} members in {len(groups)} groups\n\n"
    "💬 Now you can chat with your group members in this private telegram chat. Try writing 'Hi!'\n\n"
    "📝 And you can write and vote on proposals in the Fractal Dashboard!"

    await send_button_to_fractal_members(db, text, "Dashboard", fractal_id)
    text = f"🚀 Fractal '{fractal.name}' has started!<p>💬 Now you can chat with your group members in this private chat. Try writing 'Hi!'<p>📝 And you can write and vote on proposals in the Fractal Dashboard!"
    await send_message_to_fractal_web_app_members(db, fractal_id, text, "start")
    await open_fractal_repo(db, fractal_id)
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

async def send_button_to_members(
    db: AsyncSession,
    members: Iterable[HasUserId],
    text: str,
    button,
    fractal_id,
    data
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
        await send_button_to_telegram_users(telegram_ids, text, button, fractal_id, data)


async def send_message_to_web_app_members(
    db: AsyncSession,
    members: Iterable[HasUserId],
    text: str,
    type: str,
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
        await send_message_to_web_app_users(telegram_ids, text, type)


async def send_message_to_group(db: AsyncSession, group_id: int, text: str) -> None:
    members = await get_group_members_repo(db, group_id)
    await send_message_to_members(db, members, text)

async def send_button_to_group(db: AsyncSession, group_id: int, text: str, button, fractal_id, data=0) -> None:
    members = await get_group_members_repo(db, group_id)
    await send_button_to_members(db, members, text, button, fractal_id, data=0)

async def send_message_to_fractal_members(db: AsyncSession, fractal_id: int, text: str) -> None:
    members = await get_fractal_members_repo(db, fractal_id)
    await send_message_to_members(db, members, text)


async def send_message_to_web_app_group(db: AsyncSession, group_id: int, text: str, event_type="message") -> None:
    members = await get_group_members_repo(db, group_id)
    await send_message_to_web_app_members(db, members, text, event_type)

async def send_message_to_fractal_web_app_members(db: AsyncSession, fractal_id: int, text: str, event_type="message") -> None:
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
#        print("crate group")

        for uid in grp_users:
            await add_group_member_repo(db, grp.id, uid)
#            print("add group member")
        groups.append(grp)
    return round_obj

async def get_groups_for_round(db: AsyncSession, round_id: int):
    return await get_groups_for_round_repo(db, round_id)

# ----------------------------
# Close Round
# ----------------------------

# =================== PROPOSAL SCORING ==========================
from collections import defaultdict

# ====================== CONFIGURATION =========================

# Top-N rank scoring configuration for proposals
MAX_RANK: int = 10
RANK_POINTS: List[int] = list(range(MAX_RANK, 0, -1))  # [10, 9, 8, ..., 1]

# Bayesian smoothing minimum votes threshold for comments
MIN_VOTES_FOR_BAYES: int = 5

async def calculate_proposal_scores_with_ties(db, group_id: int, round_obj):
    all_votes = await get_votes_for_group_proposals_repo(db, group_id)
    if not all_votes:
        return

    # Group by voter (one dict per member)
    votes_by_member = defaultdict(list)
    for v in all_votes:
        votes_by_member[v.voter_user_id].append(v)

    proposal_totals = defaultdict(float)

    for voter_user_id, votes in votes_by_member.items():
        sorted_votes = sorted(votes, key=lambda v: v.score, reverse=True)
        assigned_points = {}
        rank_index = 0

        while rank_index < len(sorted_votes) and rank_index < len(RANK_POINTS):
            current_score = sorted_votes[rank_index].score
            # Collect all proposals tied at this score
            tied_group = [v for v in sorted_votes if v.score == current_score]

            # Skip if already processed this score level
            if any(t.proposal_id in assigned_points for t in tied_group):
                rank_index += 1
                continue

            tie_count = len(tied_group)
            available_points = RANK_POINTS[rank_index : rank_index + tie_count]
            if not available_points:
                break

            avg_points = sum(available_points) / tie_count
            for t in tied_group:
                assigned_points[t.proposal_id] = avg_points

            rank_index += tie_count

        # Add this member's contribution
        for pid, pts in assigned_points.items():
            proposal_totals[pid] += pts

    # Save total scores per proposal
    for proposal_id, total_score in proposal_totals.items():
        await save_proposal_score_repo(db, proposal_id, round_obj.level, total_score)


# ===================== COMMENT SCORING =========================

async def calculate_comment_scores(db, group_id: int, round_obj):
    """
    Normalize user votes, then apply Bayesian weighted average.
    """
    print ("get all votes")
    all_votes = await get_votes_for_group_comments_repo(db, group_id)
    if not all_votes:
        return

    votes_by_user = defaultdict(list)
    for v in all_votes:
        votes_by_user[v.voter_user_id].append(v)

    normalized_votes = []
    for voter_user_id, votes in votes_by_user.items():
        max_score = max(v.vote for v in votes) or 1
        for v in votes:
            norm_score = v.vote / max_score
            normalized_votes.append((v.comment_id, norm_score))

    # Aggregate normalized votes
    comment_totals = defaultdict(list)
    for cid, score in normalized_votes:
        comment_totals[cid].append(score)

    # Compute global average for Bayesian smoothing
    global_avg = (
        sum(sum(vals) / len(vals) for vals in comment_totals.values()) / len(comment_totals)
    )

    # Apply Bayesian weighting
    for comment_id, vals in comment_totals.items():
        n = len(vals)
        local_avg = sum(vals) / n
        adjusted = (n / (n + MIN_VOTES_FOR_BAYES)) * local_avg + (
            MIN_VOTES_FOR_BAYES / (n + MIN_VOTES_FOR_BAYES)
        ) * global_avg
        await save_comment_score_repo(db, comment_id, round_obj.level, adjusted)
        print ("save comment score adjusted", comment_id, adjusted)



# ===================== ROUND CLOSURE ===========================

async def close_round(db: AsyncSession, fractal_id: int):
    """
    Close a round: mark it closed and calculate totals for proposals and comments.
    Saves scores per level as lists in JSONB.
    """
    round = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round_repo(db, round.id)
    text = "ℹ️ The round has ended!"
    for g in groups:
        await send_message_to_group(db, g.id, text)
        await send_message_to_web_app_group(db, g.id, text, "end")

    # Step 1: Mark round as closed
    round_obj = await close_round_repo(db, fractal_id)

    # Step 2: Process each group
    for group in groups:
        await calculate_proposal_scores_with_ties(db, group.id, round_obj)
        await calculate_comment_scores(db, group.id, round_obj)

    # Step 3: Promote to next round
    new_round = await promote_to_next_round(db, round_obj.id, round_obj.fractal_id)
    if new_round:
        next_groups = await get_groups_for_round(db, new_round.id)
        text = "🚀 The Next Round has started! ℹ️ You have been selected to represent your Circle!"
        for g in next_groups:
            await send_button_to_group(db, g.id, text, "Dashboard", round_obj.fractal_id)
            await send_message_to_web_app_group(db, g.id, text, "start")
        return new_round

    # Step 4: End fractal if no new round
    end_text = "⚡️ The Fractal has ended!"
    await send_message_to_fractal_members(db, fractal_id, end_text)
    await send_message_to_fractal_web_app_members(db, fractal_id, end_text, "end")
    await close_fractal_repo(db, fractal_id)
    return None

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
    if len(prev_groups) < 2:
        return None  # No next round

    # Step 2: Gather representatives from each group
    rep_user_ids = []
    for g in prev_groups:
        members = await get_group_members(db, g.id)
        voter_user_ids = [m.user_id for m in members]
        reps = await get_representatives_for_group_repo(db, g.id, prev_round_id)
        rep_id = reps.get(1)

#        rep_id = await select_representative_repo(db, g.id)  # highest voted rep

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
    top_count = settings.PROPOSALS_PER_USER_DEFAULT

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
    await send_message_to_web_app_group(db, group_id, str(creator_user_id), "refresh")
    return await add_proposal_repo(db, fractal_id, group_id, round_id, title, body, creator_user_id)


async def create_comment(db: AsyncSession, proposal_id: int, user_id: int, text: str,
                               parent_comment_id: Optional[int] = None, group_id: Optional[int] = None):
    await send_message_to_web_app_group(db, group_id, str(user_id), "refresh")    
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

#async def vote_representative(db: AsyncSession, group_id: int, voter_user_id: int, candidate_user_id: int):
#    return await vote_representative_repo(db, group_id, voter_user_id, candidate_user_id)


# app/services/representative_service.py
#async def vote_representative(db: AsyncSession, group_id: int, round_id: int, voter_id: int, candidate_id: int, points: int):
#    # Check points limit (max 5 total)
#    used_points = await get_user_rep_points_used_repo(db, group_id, round_id, voter_id)
#    if used_points + points > 5:
#        raise ValueError(f"Max 5 points total. Used: {used_points}")
    
    # Save vote
#    await save_rep_vote_repo(db, group_id, round_id, voter_id, candidate_id, points)
    
    # Recalculate live results
#    results = await calculate_rep_results(db, group_id, round_id)
#    return results

async def calculate_rep_results(db: AsyncSession, group_id: int, round_id: int):
    votes = await get_rep_votes_for_round_repo(db, group_id)
    
    scores = defaultdict(lambda: {"points": 0, "vote_count": 0})
    for vote in votes:
        scores[vote.candidate_user_id]["points"] += vote.points
        scores[vote.candidate_user_id]["vote_count"] += 1
    
    # Sort: points DESC, vote_count DESC, user_id DESC (tiebreaker)
    ranked = sorted(
        scores.items(), 
        key=lambda x: (x[1]["points"], x[1]["vote_count"], x[0]), 
        reverse=True
    )
    
    return {user_id: data for user_id, data in ranked[:3]}  # Top 3 only


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

async def get_all_cards(db: AsyncSession, group_id: int, current_user_id: int, fractal_id: int=-1) -> Optional[Dict]:
    """Service: Get next unvoted card for user."""
    return await get_all_cards_repo(db, group_id, current_user_id, fractal_id)


async def send_message_to_web_app_users(telegram_ids: list[int], text: str, event_type="message"):
    for user_id in telegram_ids:
        if(int(user_id)>=20000 and int(user_id)<300000):
            continue
        try:
            """Call this from your bot/game logic"""
            user_id = str(user_id)
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


# POLL

# ----------------- POLL LOOP -----------------

from sqlalchemy.ext.asyncio import AsyncSession

async def poll_worker(async_session_maker, poll_interval: int = 60):
    print("🌀 Poll worker loop started.")
    while True:
        try:
            async with async_session_maker() as db:  # ✅ this creates AsyncSession
                assert isinstance(db, AsyncSession)
                now = datetime.now(timezone.utc)
                print(f"🔁 Poll iteration @ {now.isoformat()}")
                await check_fractals(db)
                print("✅ Poll iteration done")
        except Exception as e:
            import traceback
            print("💥 UNHANDLED poll error in poll_worker:", e)
            traceback.print_exc()
        await asyncio.sleep(poll_interval)

# ----------------- MAIN CHECK -----------------

async def check_fractals(db: AsyncSession):
    """
    1. Starts waiting fractals whose start_date <= now.
    2. Checks OPEN ROUNDS for half/close times + closes overdue rounds.
    """
    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"🕓 [Poll @ {now.isoformat()}] Checking fractals...")
    print(f"{'='*60}")
    
    try:
        # 1. Start waiting fractals
        print(f"   [STEP 1] Fetching waiting fractals...")
        waiting_fractals = await get_waiting_fractals_repo(db, now)
        print(f"   ✓ Found {len(waiting_fractals)} waiting fractals")
        
        for fractal in waiting_fractals:
            print(f"      → id={fractal.id}, name='{fractal.name}', start={fractal.start_date}")
            if fractal.start_date <= now:
                print(f"      🚀 STARTING fractal {fractal.id}")
                try:
                    await start_fractal(db, fractal.id)
                    print(f"      ✅ Started successfully")
                except Exception as e:
                    print(f"      ❌ Error starting: {e}")
                    import traceback
                    traceback.print_exc()

        # 2. Check OPEN ROUNDS (+ close overdue)
        print(f"\n   [STEP 2] Fetching open rounds...")
        open_rounds = await get_open_rounds_repo(db)
        print(f"   ✓ Found {len(open_rounds)} open rounds")
        
        for round_obj in open_rounds:
            print(f"\n      🔍 Processing round {round_obj.id}...")
            
            try:
                # Get fractal metadata
                fractal = await get_fractal_repo(db, round_obj.fractal_id)
                if not fractal:
                    print(f"         ⏭️ Fractal {round_obj.fractal_id} not found, skipping")
                    continue
                    
                if not fractal.meta or "round_time" not in fractal.meta:
                    print(f"         ⏭️ No round_time in meta, skipping")
                    continue
                
                # ✅ FIXED: round_time is MINUTES now
                round_time_minutes = int(fractal.meta["round_time"])
                round_duration = timedelta(minutes=round_time_minutes)
                half_duration = round_duration / 2
                
                round_start = round_obj.started_at
                half_way_time = round_start + half_duration
                close_time = round_start + round_duration
                
                print(f"         Round time: {round_time_minutes}min ({round_duration})")
                print(f"         Started: {round_start}")
                print(f"         Half-way at: {half_way_time}")
                print(f"         Close at: {close_time}")
                print(f"         Now: {now}")
                
                # 1. Overdue first (always)
                if now > close_time + timedelta(minutes=10):
                    print(f"         🛑 OVERDUE - AUTO CLOSING!")
                    await close_round(db, fractal.id)
                    continue

                # 2. Halfway: starts AT half_way_time → +2min
                half_window_start = half_way_time
                half_window_end = half_way_time + timedelta(minutes=2)

                if round_obj.status == "open" and half_window_start <= now <= half_window_end:
                    print(f"         🟡 HALFWAY WINDOW ({(now - half_window_start).total_seconds()/60:.1f}min in)")
                    await round_half_way_service(db, fractal.id)

                # 3. Close: starts AT close_time → +3min  
                close_window_start = close_time
                close_window_end = close_time + timedelta(minutes=3)

                if close_window_start <= now <= close_window_end:
                    print(f"         🔴 CLOSE WINDOW ({(now - close_window_start).total_seconds()/60:.1f}min in)")
                    await close_round(db, fractal.id)
                    
                
            except Exception as e:
                print(f"         💥 Error processing round {round_obj.id}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*60}")
        print(f"✅ Poll cycle complete")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR in check_fractals: {e}")
        import traceback
        traceback.print_exc()

async def round_half_way_service(db, fractal_id: int):
    """
    Halfway through the round:
      - Get latest active round.
      - Notify each group with messages/buttons.
      - Mark round status as 'vote' using repo.
    """

    round = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round_repo(db, round.id)
    text = "ℹ️ Half of the time for this round is over. Now is the time to vote on all comments, proposals and select a group representative to continue the next round."
    for g in groups:

        await send_button_to_group(
            db=db,
            group_id=g.id,
            text=text,
            button="Dashboard",
            fractal_id=fractal_id,
        )

        await send_message_to_web_app_group(
            db=db,
            group_id=g.id,
            text=text, 
            event_type = "half_time"
        )

    await set_round_status_repo(db, round.id, "vote")

async def rep_vote_card(db: AsyncSession, user_id: int, group_id: int, fractal_id: int = -1) -> str:
    
    if (group_id == -1):
        group = await get_last_group_repo(db, fractal_id)
        group_id = group.id
    else:
        group = await get_group_repo(db, group_id)

    group = await get_group_repo(db, group_id)
    round = await get_round_repo(db, group.round_id)
    print("Round Status", round.status)
    if (round.status == "closed"):
        # if round is closed return the representatives total score
        reps = await get_representatives_for_group_repo(db, group_id, round.id)
        if not reps:
            members = await get_group_members(db, group_id)
            if not members:
                return "<div class='proposal-card rep-vote-card'><div class='instructions'>No members in group.</div></div>"
            

            html = [
                    "<div class='proposal-card rep-vote-card'>",
                    "<div class='instructions'>Group Members</div>",
                ]
            
            for member in members:
                user = await get_user(db, member.user_id)
                avatar = f"/static/img/64_{(member.user_id % 16) + 1}.png"
                name = user.username or f"User {member.user_id}"  # Safe: username or fallback
                
                html.append(f"""
                    <div class="rep-member">
                        <img src="{avatar}" alt="" class="proposal-comment-avatar">
                        <span class="name">{name}</span>
                    </div>
                """)
            return "\n".join(html)        


        html = [
            "<div class='proposal-card rep-vote-card'>",
            "<div class='instructions'>Group Representatives 🥇 🥈 🥉</div>",
        ]

        for rank, user_id in reps.items():
            user = await get_user(db, user_id)
            avatar = f"/static/img/64_{(user_id % 16) + 1}.png"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")
            html.append(f"""
                <div class="rep-member">
                    <img src="{avatar}" alt="" class="proposal-comment-avatar">
                    <span class="name">{user.username}</span>
                    <span class="medal">{medal}</span>
                </div>
            """)

        html.append("</div>")
        return "\n".join(html)        

    else:
        # if round open return vore card
        
        members = await get_group_members_repo(db, group_id)
        votes = await get_user_rep_points_repo(db, group_id, user_id)
        vote_map = {v.candidate_user_id: v.points for v in votes}

        html = [
            "<div class='proposal-card rep-vote-card'>",
            "<div class='instructions'>Group Representative: 🥇 🥈 🥉</div>",
        ]

        for m in members:
            user = await get_user(db, m.user_id)
            if user.id == user_id:
                continue
            points = vote_map.get(m.user_id, 0)
            medal, dimmed = "", "dimmed"

            if points == 3:
                medal, dimmed = "🥇", ""
            elif points == 2:
                medal, dimmed = "🥈", ""
            elif points == 1:
                medal, dimmed = "🥉", ""

            # avatar image based on user_id mod 16
            avatar = f"/static/img/64_{(m.user_id % 16) + 1}.png"

            html.append(f"""
                <div class="rep-member" data-user-id="{m.user_id}">
                    <img src="{avatar}" alt="" class="proposal-comment-avatar">
                    <span class="name">{user.username}</span>
                    <span class="medal {dimmed}">{medal}</span>
                </div>
            """)

        html.append("</div>")
        return "\n".join(html)

