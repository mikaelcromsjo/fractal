import asyncio
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional

import asyncpg
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from infrastructure.models import Base
import infrastructure.models as models
from services.fractal_service import (
    create_fractal,
    join_fractal,
    start_fractal,
    get_groups_for_round,
    get_group_members,
    create_proposal,
    create_comment,
    vote_proposal,
    vote_comment,
    vote_representative,
    close_round,
)

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

DATABASE_ADMIN_URL = "postgresql://fractal_user:fractal_pass@db:5432/postgres"
TEST_DB_NAME = "test_fractal_db"
DATABASE_URL = f"postgresql+asyncpg://fractal_user:fractal_pass@db:5432/{TEST_DB_NAME}"



# Max simulated users = 8 * 8 * 7
MAX_SIM_USERS = 8 * 8 * 7

# Telegram id for your test user (string, as stored in DB)
TEST_USER_TELEGRAM_ID = "1369836643"  # change to your real Telegram id as string

# -------------------------------------------------------------------
# Helpers: DB, pause, demo content
# -------------------------------------------------------------------

async def recreate_test_db():
    conn = await asyncpg.connect(DATABASE_ADMIN_URL)
    await conn.execute(
        f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid();
        """
    )
    await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")
    await conn.execute(f"CREATE DATABASE {TEST_DB_NAME};")
    await conn.close()
    print(f"Database '{TEST_DB_NAME}' recreated successfully.")


async def create_tables():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        print("Creating all tables...")
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Tables created successfully.")


engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def pause(label: str):
    print(f"\n=== PAUSE: {label} ===")
    print("Press Enter to continue...")
    await asyncio.to_thread(input)


FIRST_NAMES = [
    "Alex", "Sam", "Jordan", "Taylor", "Casey", "Morgan", "Jamie", "Robin",
    "Chris", "Drew", "Lee", "Avery", "Sky", "Quinn", "Riley", "Devin",
]
LAST_NAMES = [
    "River", "Stone", "Lake", "Hill", "Forest", "Vale", "Brook", "Field",
    "Wood", "Meadow", "Dale", "Grove",
]

PROPOSAL_TITLES = [
    "Improve onboarding flow",
    "Refine voting UX",
    "Enhance group chat",
    "Optimize proposal ranking",
    "Add dark mode support",
    "Streamline notifications",
    "Improve mobile layout",
    "Clarify rules and FAQs",
]

PROPOSAL_BODIES = [
    "This proposal suggests small, concrete changes that are easy to test.",
    "The idea is to keep things simple while improving clarity for new users.",
    "This would help groups coordinate more smoothly between rounds.",
    "The goal is to make the experience feel more natural and fluid.",
    "This is a low‑risk change with clear benefits for many participants.",
]

COMMENT_TEXTS = [
    "This looks great, would love to see a quick prototype.",
    "Makes sense to me, especially for larger fractals.",
    "Nice idea, curious how it would work for new users.",
    "I like the direction, maybe we can keep the first version minimal.",
    "Good starting point, we can refine details after testing.",
]


def random_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def random_title() -> str:
    return random.choice(PROPOSAL_TITLES)


def random_body() -> str:
    return random.choice(PROPOSAL_BODIES)


def random_comment_text() -> str:
    return random.choice(COMMENT_TEXTS)


# -------------------------------------------------------------------
# Core simulation logic
# -------------------------------------------------------------------

async def simulate_round(
    db: AsyncSession,
    fractal: models.Fractal,
    round_obj: models.Round,
    test_user: models.User,
    sim_users: List[models.User],
):
    """
    Simulate one round:
    - Each simulated user makes 1 proposal.
    - 20% chance to comment on each proposal.
    - No replies to comments.
    - Test user always top representative and gets highest scores on own content.
    - Others' votes random.
    - Pauses:
        1) already done before start_fractal / round creation
        2) after half sim users have created proposals/comments
        3) before close_round
    """
    print(f"\n--- Simulating Round {round_obj.level} (id={round_obj.id}) ---")

    groups = await get_groups_for_round(db, round_obj.id)
    print(f"Round {round_obj.id} has groups: {[g.id for g in groups]}")

    # Map group_id -> list of member user_ids
    group_members: Dict[int, List[int]] = {}
    for g in groups:
        m = await get_group_members(db, g.id)
        member_ids = [gm.user_id for gm in m]
        group_members[g.id] = member_ids
        print(f"Group {g.id} members: {member_ids}")

    # Build a quick lookup for simulated users (excluding test user)
    sim_user_ids = {u.id for u in sim_users}

    # STEP A: Proposals + comments
    proposals_by_group: Dict[int, List[models.Proposal]] = {}
    total_sim_users = len(sim_users)
    half_point = max(1, total_sim_users // 2)
    created_count = 0
    paused_halfway = False

    for g in groups:
        proposals_by_group[g.id] = []

        # Filter to simulated users in this group (exclude test user and any other non-sim users)
        member_ids = [uid for uid in group_members[g.id] if uid in sim_user_ids]

        for uid in member_ids:
            user = next(u for u in sim_users if u.id == uid)

            # Create one proposal per simulated user
            p = await create_proposal(
                db=db,
                fractal_id=fractal.id,
                group_id=g.id,
                round_id=round_obj.id,
                title=random_title(),
                body=random_body(),
                creator_user_id=user.id,
            )
            proposals_by_group[g.id].append(p)

            # 20% chance user comments on own proposal
            if random.random() < 0.2:
                await create_comment(
                    db=db,
                    proposal_id=p.id,
                    user_id=user.id,
                    text=random_comment_text(),
                    parent_comment_id=None,
                    group_id=g.id,
                )

            created_count += 1
            if not paused_halfway and created_count >= half_point:
                paused_halfway = True
                await pause(
                    f"Half of simulated users have created proposals/comments in round {round_obj.level}"
                )

    # STEP B: Voting on proposals/comments
    print("\nCasting votes...")

    ProposalVote = models.ProposalVote
    CommentVote = models.CommentVote

    for g in groups:
        all_members = group_members[g.id]
        for p in proposals_by_group[g.id]:
            # Everyone votes on proposal
            for voter_id in all_members:
                # Determine score:
                # - If this is test user's own proposal, give it a high fixed score from everyone.
                # - Otherwise, random score 1–10.
                if p.creator_user_id == test_user.id:
                    score = 10
                else:
                    score = random.randint(4, 9)
                await vote_proposal(db, p.id, voter_id, score=score)

            # Get all top-level comments on this proposal for this group
            res_comments = await db.execute(
                select(models.Comment).where(
                    models.Comment.proposal_id == p.id,
                    models.Comment.parent_comment_id.is_(None),
                    models.Comment.group_id == g.id,
                )
            )
            comments = res_comments.scalars().all()

            for c in comments:
                for voter_id in all_members:
                    # If comment by test user, force positive vote
                    if c.user_id == test_user.id:
                        vote = True
                    else:
                        vote = random.random() < 0.75
                    await vote_comment(db, c.id, voter_id, vote=vote)

    # STEP C: Representative votes
    print("\nCasting representative votes...")

    for g in groups:
        member_ids = group_members[g.id]
        # Ensure test user is in this group, otherwise pick first member
        if test_user.id in member_ids:
            candidate_id = test_user.id
        else:
            candidate_id = member_ids[0]

        for voter_id in member_ids:
            # Vote for candidate_id (test user where available)
            await vote_representative(db, g.id, voter_id, candidate_id)

    # STEP D: Print proposal vote totals
    print("\nProposal vote totals (per group):")
    for g in groups:
        for p in proposals_by_group[g.id]:
            res = await db.execute(
                select(func.sum(ProposalVote.score)).where(
                    ProposalVote.proposal_id == p.id
                )
            )
            total_votes = res.scalar() or 0
            print(
                f"  Group {g.id} Proposal {p.id} "
                f"(creator={p.creator_user_id}) total score: {total_votes}"
            )

    # PAUSE before closing this round
    await pause(f"Before closing round {round_obj.level}")

    # STEP E: Close round and create next, if any
    next_round = await close_round(db, round_obj.id)

    if not next_round:
        print(f"Round {round_obj.id} closed. No next round created.")
        return None

    print(
        f"Round {round_obj.id} closed. "
        f"New Round {next_round.id} created at level {next_round.level}"
    )

    # Print new groups and members
    new_groups = await get_groups_for_round(db, next_round.id)
    print(f"New groups in round {next_round.id}: {[g.id for g in new_groups]}")
    for g in new_groups:
        m = await get_group_members(db, g.id)
        member_ids = [gm.user_id for gm in m]
        print(f"  Group {g.id} members: {member_ids}")

    return next_round


# -------------------------------------------------------------------
# Main simulation (up to 3 rounds)
# -------------------------------------------------------------------

async def main():
    await recreate_test_db()
    await create_tables()

    async with AsyncSessionLocal() as db:
        # Create fractal
        fractal = await create_fractal(
            db,
            name="Demo Fractal",
            description="Demo simulation with 3 rounds",
            start_date=datetime.now(timezone.utc),
            status="waiting",
            settings={"group_size": 8},
        )
        print(f"Created fractal {fractal.id}")

        # Create test user
        print("Creating test user...")
        test_user_info = {
            "username": "demo_test_user",
            "telegram_id": TEST_USER_TELEGRAM_ID,
        }
        test_user = await join_fractal(db, test_user_info, fractal.id)
        print(f"Test user id={test_user.id}, telegram_id={test_user.telegram_id}")

        # Create simulated users
        sim_users: List[models.User] = []
        sim_user_count = MAX_SIM_USERS
        print(f"Creating {sim_user_count} simulated users...")
        for i in range(sim_user_count):
            user_info = {
                "username": random_name().replace(" ", "_").lower() + f"_{i+1}",
                "telegram_id": str(200000 + i),
            }
            u = await join_fractal(db, user_info, fractal.id)
            sim_users.append(u)

        all_users = [test_user] + sim_users
        print(f"Total users in fractal: {len(all_users)}")

        # PAUSE before starting fractal
        await pause("Before start_fractal (you can test joining / dashboard now)")

        # Start first round via start_fractal
        round0 = await start_fractal(db, fractal.id)
        print(f"Started Round 0: id={round0.id}, level={round0.level}")

        current_round = round0
        max_rounds = 3
        for _ in range(max_rounds):
            if not current_round:
                break
            current_round = await simulate_round(
                db=db,
                fractal=fractal,
                round_obj=current_round,
                test_user=test_user,
                sim_users=sim_users,
            )

        print("\nSimulation finished.")


if __name__ == "__main__":
    asyncio.run(main())
