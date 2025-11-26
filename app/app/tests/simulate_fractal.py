import asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.repositories.async_repos import create_fractal, get_group_members, create_user
from app.services.fractal_service import (
    join_fractal,
    start_fractal,
    get_groups_for_round,
    create_proposal_async,
    create_comment_async,
    vote_proposal_async,
    vote_comment_async,
    vote_representative_async,
    close_round,
    get_proposals_comments_tree,
    get_proposal_comments_tree,
    
)
from app.infrastructure.models import ProposalVote, CommentVote
from sqlalchemy import select, func
from app.infrastructure.models import Base

import asyncio
import asyncpg

DATABASE_ADMIN_URL = "postgresql://fractal_user:fractal_pass@db:5432/postgres"
TEST_DB_NAME = "test_fractal_db"
DATABASE_URL = f"postgresql+asyncpg://fractal_user:fractal_pass@db:5432/{TEST_DB_NAME}"

async def recreate_test_db():
    # Connect to the default 'postgres' database
    conn = await asyncpg.connect(DATABASE_ADMIN_URL)

    # Terminate all connections to the test DB if it exists
    await conn.execute(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid();
    """)
    # Drop the test DB if exists
    await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")
    # Create a new test DB
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

# ---------------------------------
# Setup async engine & session
# ---------------------------------
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def main():
    await recreate_test_db()
    await create_tables()


    async with AsyncSessionLocal() as db:
        # -------------------------
        # STEP 1: Create fractal
        # -------------------------
        fractal = await create_fractal(
            db,
            name="Mega Fractal",
            description="Manual simulation test",
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
        # STEP 3: Start fractal
        # -------------------------
        round0 = await start_fractal(db, fractal.id)
        print(f"Round 0 ID: {round0.id}, status: {round0.status}")

        # -------------------------
        # STEP 4: Get groups
        # -------------------------
        groups = await get_groups_for_round(db, round0.id)
        print(f"Found {len(groups)} groups")

        # -------------------------
        # STEP 5: Print group members
        # -------------------------
        group_members_map = {}
        for g in groups:
            members = await get_group_members(db, g.id)
            member_ids = [m.user_id for m in members]
            group_members_map[g.id] = member_ids
            print(f"Group {g.id} members: {member_ids}")

        # -------------------------
        # STEP 6: Proposals
        # -------------------------
        proposals_by_group = {}
        for g in groups:
            proposals_by_group[g.id] = []
            for uid in group_members_map[g.id]:
                user_obj = next(u for u in users if u.id == uid)
                p = await create_proposal_async(
                    db=db,
                    fractal_id=fractal.id,
                    group_id=g.id,
                    round_id=round0.id,
                    title=f"Proposal by {user_obj.username}",
                    body="Manual test proposal",
                    creator_user_id=uid,
                )
                proposals_by_group[g.id].append(p)

        print("Proposals created:")
        for g_id, plist in proposals_by_group.items():
            for p in plist:
                print(f"Proposal {p.id} in group {g_id} by user {p.creator_user_id}")

        # -------------------------
        # STEP 7: Votes and comments
        # -------------------------
        for g in groups:
            members = group_members_map[g.id]
            for p in proposals_by_group[g.id]:
                for uid in members:
                    await vote_proposal_async(db, p.id, uid, score=10)
                commenter_id = members[0]
                c = await create_comment_async(
                    db=db,
                    proposal_id=p.id,
                    user_id=commenter_id,
                    text=f"Comment on proposal {p.id}",
                    parent_comment_id=None,
                )
                for uid in members:
                    await vote_comment_async(db, c.id, uid, vote=True)

        # STEP 7: Votes and comments
        for g in groups:
            members = group_members_map[g.id]

            # Create 5 proposals per group
            proposals_by_group[g.id] = []
            for i, uid in enumerate(members):
                p = await create_proposal_async(
                    db,
                    fractal_id=g.fractal_id,
                    round_id=g.round_id,
                    group_id=g.id,
                    creator_user_id=uid,
                    title=f"Proposal by user{uid}",
                    body=f"Body for proposal {i} by user {uid}",
                )
                proposals_by_group[g.id].append(p)

                # Comment by first member
                commenter_id = members[0]
                c = await create_comment_async(
                    db=db,
                    proposal_id=p.id,
                    user_id=commenter_id,
                    text=f"Comment on proposal {p.id}",
                    parent_comment_id=None,
                )

                # Replies from remaining members
                for reply_uid in members[1:]:
                    await create_comment_async(
                        db=db,
                        proposal_id=p.id,
                        user_id=reply_uid,
                        text=f"Reply by user {reply_uid} on comment for proposal {p.id}",
                        parent_comment_id=c.id,
                    )

                # Everyone votes on proposal
                for voter_id in members:
                    await vote_proposal_async(db, p.id, voter_id, score=10)

                # Everyone votes on first comment
                for voter_id in members:
                    await vote_comment_async(db, c.id, voter_id, vote=True)
        # -------------------------
        # STEP 7c: Representative votes
        # -------------------------
        for g in groups:
            members = group_members_map[g.id]
            candidate_id = members[0]  # first user
            for voter_id in members:
                await vote_representative_async(db, g.id, voter_id, candidate_id)

        # -------------------------
        # STEP 8: Print proposal vote totals
        # -------------------------
        print("Proposal vote totals:")
        for g in groups:
            for p in proposals_by_group[g.id]:
                res = await db.execute(select(func.sum(ProposalVote.score)).where(ProposalVote.proposal_id==p.id))
                total_votes = res.scalar() or 0
                print(f"Proposal {p.id} total votes: {total_votes}")


        # -------------------------
        # STEP 9: Close current round and promote to next round
        # -------------------------

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


        # -------------------------
        # STEP 10: List proposals and comments after closing round 0
        # -------------------------


        # Determine which round to display (new round if created, else the closed one)
        round_to_inspect = round0

        # Get groups for this round
        groups_in_round = await get_groups_for_round(db, round_to_inspect.id)

        for g in groups_in_round:
            print(f"\nGroup {g.id} (Round {round_to_inspect.id}):")
            members = await get_group_members(db, g.id)
            member_ids = [m.user_id for m in members]
            print(f"  Members: {member_ids}")

            # Get proposals with comments tree
            tree = await get_proposals_comments_tree(db, g.id)
            await print_proposals_comments_tree(tree)

async def print_proposals_comments_tree(tree):
    """
    Pretty print proposals with nested comments and votes.
    tree: output from get_proposals_comments_tree
    """
    def print_comments(comments, indent=4):
        for c_idx, c_dict in enumerate(comments):
            c = c_dict["comment"]
            votes = c_dict["votes"]
            yes_votes = votes.get("yes", 0)
            no_votes = votes.get("no", 0)
            total_votes = yes_votes + no_votes
            print(" " * indent + f"Comment {c_idx}: ID {c.id}, User {c.user_id}, "
                  f"Score per level: {c.score_per_level}, Text: {c.text}, "
                  f"Yes: {yes_votes}, No: {no_votes}, Total votes: {total_votes}")
            # Recurse into replies
            print_comments(c_dict.get("replies", []), indent=indent+2)

    for p_idx, p_dict in enumerate(tree):
        p = p_dict["proposal"]
        prop_votes = p_dict.get("votes", {})
        total_prop_votes = prop_votes.get("total", 0)
        print(f"Proposal {p_idx}: ID {p.id}, Title: {p.title}, Total votes: {total_prop_votes}")
        print_comments(p_dict.get("comments", []))



if __name__ == "__main__":
    asyncio.run(main())