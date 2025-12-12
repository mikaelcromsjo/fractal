import pytest
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.fractal_repos import create_fractal, get_group_members
from services.fractal_service import (
    join_fractal,
    start_fractal,
    get_groups_for_round,
    create_proposal,
    create_comment,
    vote_proposal,
    vote_comment,
    close_round,
)

from infrastructure.models import ProposalVote, CommentVote

# -------------------------------------------
# Make sure your db_session fixture returns AsyncSession
# -------------------------------------------
@pytest.mark.asyncio
async def test_fractal_simulation(db_session: AsyncSession):
    db = db_session

    # -------------------------
    # STEP 1: Create fractal
    # -------------------------
    fractal = await create_fractal(
        db,
        name="Mega Fractal",
        description="Simulation test",
        start_date=datetime.now(timezone.utc),
        status="waiting",
        settings={"group_size": 5},
    )

    # -------------------------
    # STEP 2: Join 25 users
    # -------------------------
    users = []
    for i in range(25):
        u = await join_fractal(
            db,
            {"username": f"user{i+1}", "telegram_id": str(20000 + i)},
            fractal.id,
        )
        users.append(u)

    # -------------------------
    # STEP 3: Start fractal → round 0 open
    # -------------------------
    round0 = await start_fractal(db, fractal.id)
    print(f"Round 0 ID: {round0.id}, status: {round0.status}")

    # -------------------------
    # STEP 4: Get all groups for round 0
    # -------------------------
    groups = await get_groups_for_round(db, round0.id)
    print(f"Found {len(groups)} groups for round 0")

    # -------------------------
    # STEP 4b: Get members for each group
    # -------------------------
    group_members_map = {}
    for g in groups:
        members = await get_group_members(db, g.id)
        member_ids = [m.user_id for m in members]
        group_members_map[g.id] = member_ids
        print(f"Group {g.id} members: {member_ids}")

    # -------------------------
    # STEP 5: Each user creates a proposal
    # -------------------------
    proposals_by_group = {}
    for g in groups:
        proposals_by_group[g.id] = []
        for uid in group_members_map[g.id]:
            user_obj = next(u for u in users if u.id == uid)
            p = await create_proposal(
                db=db,
                fractal_id=fractal.id,
                group_id=g.id,
                round_id=round0.id,
                title=f"Proposal by {user_obj.username}",
                body="This is a test proposal",
                creator_user_id=uid,
            )
            proposals_by_group[g.id].append(p)

    # -------------------------
    # STEP 6: Print all proposals
    # -------------------------
    all_proposals = [p for plist in proposals_by_group.values() for p in plist]
    print("All proposals:")
    for p in all_proposals:
        print(f"Proposal {p.id} by user {p.creator_user_id} in group {p.group_id}")

    # -------------------------
    # STEP 7: Each user votes and comments on each proposal
    # -------------------------
    comments_by_proposal = {}
    for g in groups:
        members = group_members_map[g.id]
        for p in proposals_by_group[g.id]:
            # vote
            for uid in members:
                await vote_proposal(db, p.id, uid, score=10)
            # comment
            commenter_id = members[0]
            c = await create_comment(
                db=db,
                proposal_id=p.id,
                user_id=commenter_id,
                text=f"Comment on proposal {p.id}",
                parent_comment_id=None,
            )
            comments_by_proposal[p.id] = c
            # vote on comment
            for uid in members:
                await vote_comment(db, c.id, uid, vote=True)

    # -------------------------
    # STEP 8: Print proposal vote totals
    # -------------------------
    print("Proposal vote totals:")
    for g in groups:
        for p in proposals_by_group[g.id]:
            res = await db.execute(
                select(func.sum(ProposalVote.score)).where(ProposalVote.proposal_id == p.id)
            )
            total_votes = res.scalar() or 0
            print(f"Proposal {p.id} total votes: {total_votes}")

    # Close current round (and automatically create next round if applicable)
    next_round = await close_round(db, round0.id)

    if next_round is None:
        print(f"\nRound {round0.id} closed. No next round created (not enough groups).")
    else:
        print(f"\nRound {round0.id} closed. New Round {next_round.id} created, level {next_round.level}")

        # Print new groups and members
        new_groups = await get_groups_for_round(db, next_round.id)
        print(f"New groups for Round {next_round.id}: {[g.id for g in new_groups]}")

        for g in new_groups:
            members = await get_group_members(db, g.id)
            member_ids = [m.user_id for m in members]
            print(f"  Group {g.id} members: {member_ids}")

            # For testing, pick first member as representative
            if member_ids:
                representative_id = member_ids[0]
                print(f"  Group {g.id} representative (test): {representative_id}")            
