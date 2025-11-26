#~~~{"id":"70524","variant":"standard","title":"Async Fractal Service Layer"} 
# app/services/fractal_service.py
from typing import List, Optional, Dict
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.async_repos import (
    get_user_by_telegram_id,
    create_user,
    create_fractal,
    add_fractal_member,
    get_active_fractal_members,
    create_round,
    create_group,
    add_group_member,
    get_group_members,
    add_proposal,
    add_comment,
    cast_proposal_vote,
    cast_comment_vote,
    get_proposals_for_group,
    get_comments_for_proposal,
    get_top_proposals,
    close_round_repo,
    save_proposal_score,
    save_comment_score,
    get_groups_for_round_repo,
    select_representative,
    vote_representative,
    get_votes_for_comment,
    get_votes_for_proposal,
    get_round_by_id,
)
from app.domain import fractal_logic as domain



async def join_fractal(db: AsyncSession, user_info: Dict, fractal_id: int):
    """
    Join a user to a fractal.
    Create user if not exists.
    """
    user = await get_user_by_telegram_id(db, user_info.get("telegram_id"))
    if not user:
        user = await create_user(db, user_info)
    await add_fractal_member(db, fractal_id, user.id)
    return user


async def start_fractal(db: AsyncSession, fractal_id: int):
    """
    Mark fractal active and start first round.
    """
    members = await get_active_fractal_members(db, fractal_id)
    round_0 = await start_round(db, fractal_id, level=0, members=members)
    return round_0


# ----------------------------
# Round / Group Workflow
# ----------------------------
async def start_round(db: AsyncSession, fractal_id: int, level: int, members: List):
    """
    Create a round and divide users into groups.
    """
    round_obj = await create_round(db, fractal_id, level)

    user_ids = [m.user_id for m in members]
    group_size = 5  # Could come from fractal settings
    groups_flat = domain.divide_into_groups(user_ids, group_size)

    groups = []
    for grp_users in groups_flat:
        grp = await create_group(db, fractal_id, round_obj.id, level)
        for uid in grp_users:
            await add_group_member(db, grp.id, uid)
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
        proposals = await get_proposals_for_group(db, group.id)
        for p in proposals:
            # Explicitly load votes for this proposal
            proposal_votes = await get_votes_for_proposal(db, p.id)
            total_score = sum(v.score for v in proposal_votes)
            # Save proposal score per level
            await save_proposal_score(db, p.id, round_obj.level, total_score)

            # Explicitly load comments for this proposal
            comments = await get_comments_for_proposal(db, p.id)
            for c in comments:
                comment_votes = await get_votes_for_comment(db, c.id)
                yes_count = sum(1 for v in comment_votes if v.vote)
                no_count = sum(1 for v in comment_votes if not v.vote)
                comment_score = yes_count - no_count
                await save_comment_score(db, c.id, round_obj.level, comment_score)

    # Step 4: Promote to next round
    new_round = await promote_to_next_round(db, round_obj.id, round_obj.fractal_id)

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
        rep_id = await select_representative(db, g.id)  # highest voted rep
        if rep_id:
            rep_user_ids.append(rep_id)

    # Step 3: Create new round
    prev_round_obj = await get_round_by_id(db, prev_round_id)
    next_level = prev_round_obj.level + 1
    new_round = await create_round(db, fractal_id, next_level)

    # Step 4: Divide representatives into new groups
    group_size = 5  # can come from fractal settings
    groups_flat = domain.divide_into_groups(rep_user_ids, group_size)
    new_groups = []
    for grp_users in groups_flat:
        grp = await create_group(db, fractal_id, new_round.id, next_level)
        for uid in grp_users:
            await add_group_member(db, grp.id, uid)
        new_groups.append(grp)

    # Step 5: Promote top proposals from previous round
    top_count = 2  # can come from fractal settings
    for g_prev, grp_new in zip(prev_groups, new_groups):
        top_props = await get_top_proposals(db, g_prev.id, top_count)  # g_prev.id is group_id
        for p in top_props:
            p.round_id = new_round.id
            p.group_id = grp_new.id
            await db.commit()

    return new_round


# ----------------------------
# Proposal / Comment Workflow
# ----------------------------
async def create_proposal_async(db: AsyncSession, fractal_id: int, group_id: int, round_id: int,
                                title: str, body: str, creator_user_id: int):
    return await add_proposal(db, fractal_id, group_id, round_id, title, body, creator_user_id)


async def create_comment_async(db: AsyncSession, proposal_id: int, user_id: int, text: str,
                               parent_comment_id: Optional[int] = None):
    return await add_comment(db, proposal_id, user_id, text, parent_comment_id)


# ----------------------------
# Voting Workflow
# ----------------------------
async def vote_proposal_async(db: AsyncSession, proposal_id: int, voter_user_id: int, score: int):
    return await cast_proposal_vote(db, proposal_id, voter_user_id, score)


async def vote_comment_async(db: AsyncSession, comment_id: int, voter_user_id: int, vote: bool):
    return await cast_comment_vote(db, comment_id, voter_user_id, vote)



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
    proposals = await get_proposals_for_group(db, group_id)
    tree_result = []

    for p in proposals:
        # Proposal votes
        proposal_votes = await get_votes_for_proposal(db, p.id)
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
        comments = await get_comments_for_proposal(db, p.id)
        comment_map = {}
        for c in comments:
            votes = await get_votes_for_comment(db, c.id)
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
    comments = await get_comments_for_proposal(db, proposal_id)
    comment_dicts = [{"comment": c, "votes": c.votes} for c in comments]
    tree = domain.build_comment_tree(comment_dicts)
    result.append({"proposal": p, "comments": tree})
    return result



# ----------------------------
# Representative Selection
# ----------------------------
async def select_representative_from_vote(db: AsyncSession, group_id: int):
    return select_representative(db, group_id)


async def vote_representative_async(db: AsyncSession, group_id: int, voter_user_id: int, candidate_user_id: int):
    # You can add extra logic here, e.g., check if voter belongs to the group
    return await vote_representative(db, group_id, voter_user_id, candidate_user_id)