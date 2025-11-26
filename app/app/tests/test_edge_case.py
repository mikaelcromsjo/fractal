# app/tests/test_edge_cases.py
import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.models import User, Group, Proposal, Comment
from app.services.fractal_service import (
    vote_proposal_async,
    vote_comment_async,
    vote_representative,
    create_comment_async,
    close_round,
    promote_to_next_round,
    get_groups_for_round,
    get_proposals_for_group,
    get_comments_for_proposal,
    get_votes_for_proposal,
    get_votes_for_comment,
)
from app.services.round_service import RoundClosedError

pytestmark = pytest.mark.asyncio

# -----------------------------
# Helpers
# -----------------------------
async def create_test_data(db: AsyncSession):
    """
    Create a small fractal, round, groups, users, proposals, and comments.
    Returns dicts for easy access.
    """
    users = [User(username=f"user{i}") for i in range(1, 6)]
    db.add_all(users)
    await db.commit()
    await db.refresh(users[0])

    # One round
    from app.services.round_service import create_round, create_group, add_group_member, create_proposal

    round_obj = await create_round(db, fractal_id=1, level=0)

    # One group
    group = await create_group(db, fractal_id=1, round_id=round_obj.id, level=0)
    for u in users:
        await add_group_member(db, group.id, u.id)

    # 2 proposals
    proposals = []
    for u in users[:2]:
        p = await create_proposal(db, fractal_id=1, group_id=group.id, round_id=round_obj.id, creator_user_id=u.id, title=f"Proposal by {u.username}")
        proposals.append(p)

    # One comment per proposal
    comments = []
    for p in proposals:
        c = await create_comment_async(db, proposal_id=p.id, user_id=users[0].id, text=f"Comment on proposal {p.id}")
        comments.append(c)

    return {
        "users": users,
        "round": round_obj,
        "group": group,
        "proposals": proposals,
        "comments": comments,
    }


# -----------------------------
# Edge Case Tests
# -----------------------------
async def test_vote_outside_group(db: AsyncSession):
    data = await create_test_data(db)
    user_outside = User(username="outside")
    db.add(user_outside)
    await db.commit()
    await db.refresh(user_outside)

    # Pick proposal from the group
    p = data["proposals"][0]

    # User not in group tries to vote
    with pytest.raises(Exception):
        await vote_proposal_async(db, p.id, user_outside.id, score=5)


async def test_vote_after_round_closed(db: AsyncSession):
    data = await create_test_data(db)
    round_id = data["round"].id
    await close_round(db, round_id)

    p = data["proposals"][0]
    user_id = data["users"][0].id

    with pytest.raises(RoundClosedError):
        await vote_proposal_async(db, p.id, user_id, score=5)


async def test_double_vote(db: AsyncSession):
    data = await create_test_data(db)
    p = data["proposals"][0]
    user_id = data["users"][0].id

    # First vote
    vote1 = await vote_proposal_async(db, p.id, user_id, 5)
    # Second vote should overwrite or raise
    vote2 = await vote_proposal_async(db, p.id, user_id, 7)

    votes = await get_votes_for_proposal(db, p.id)
    assert len(votes) == 1
    assert votes[0].score == 7


async def test_small_group_no_promotion(db: AsyncSession):
    data = await create_test_data(db)
    # Only 2 groups
    from app.services.round_service import create_group
    group2 = await create_group(db, fractal_id=1, round_id=data["round"].id, level=0)
    next_round = await promote_to_next_round(db, data["round"].id, fractal_id=1)
    assert next_round is None


async def test_no_votes(db: AsyncSession):
    data = await create_test_data(db)
    # Do not vote
    p = data["proposals"][0]
    votes = await get_votes_for_proposal(db, p.id)
    assert votes == []  # no votes
    await close_round(db, data["round"].id)


async def test_tie_votes_representative(db: AsyncSession):
    data = await create_test_data(db)
    group = data["group"]
    users = data["users"]

    from app.services.representative_service import vote_representative, get_representative_repo

    # Each member votes for themselves → tie
    for u in users:
        await vote_representative(db, group.id, u.id, u.id)

    rep_id = await get_representative_repo(db, group.id)
    assert rep_id in [u.id for u in users]  # Any of the tied users


async def test_invalid_ids(db: AsyncSession):
    # Voting on non-existent proposal/comment
    with pytest.raises(Exception):
        await vote_proposal_async(db, 99999, 1, 5)

    with pytest.raises(Exception):
        await vote_comment_async(db, 99999, 1, vote=True)


async def test_large_simulation(db: AsyncSession):
    # 50 users, 10 groups, 5 proposals each
    users = [User(username=f"user{i}") for i in range(1, 51)]
    db.add_all(users)
    await db.commit()

    from app.services.round_service import create_round, create_group, add_group_member, create_proposal

    round_obj = await create_round(db, fractal_id=1, level=0)
    groups = []
    for i in range(10):
        g = await create_group(db, fractal_id=1, round_id=round_obj.id, level=0)
        for u in users[i*5 : (i+1)*5]:
            await add_group_member(db, g.id, u.id)
        groups.append(g)

    # Each group: 5 proposals, 5 comments, votes
    for g in groups:
        for u in users[:5]:
            p = await create_proposal(db, fractal_id=1, group_id=g.id, round_id=round_obj.id, creator_user_id=u.id, title=f"Proposal by {u.username}")
            for member in users[:5]:
                await vote_proposal_async(db, p.id, member.id, score=10)
            c = await create_comment_async(db, p.id, users[0].id, text=f"Comment on proposal {p.id}")
            for member in users[:5]:
                await vote_comment_async(db, c.id, member.id, vote=True)

    await close_round(db, round_obj.id)
