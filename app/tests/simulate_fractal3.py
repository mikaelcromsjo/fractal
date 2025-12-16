import asyncio
from datetime import datetime, timezone
import asyncpg
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from services.fractal_service import (
    join_fractal,
    start_fractal,
    get_groups_for_round,
    create_proposal,
    create_comment,
    vote_proposal,
    vote_comment,
    vote_representative,
    close_round,
    create_fractal,
    get_group_members,
    get_proposals_comments_tree,
)
from infrastructure.models import ProposalVote, CommentVote, Base

DATABASE_ADMIN_URL = "postgresql://fractal_user:fractal_pass@db:5432/postgres"
TEST_DB_NAME = "test_fractal_db"
DATABASE_URL = f"postgresql+asyncpg://fractal_user:fractal_pass@db:5432/{TEST_DB_NAME}"

async def recreate_test_db():
    conn = await asyncpg.connect(DATABASE_ADMIN_URL)
    await conn.execute(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid();
    """)
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

async def pause(label: str = ""):
    if label:
        print(f"\n=== PAUSE: {label} ===")
    print("Press Enter to continue...")
    await asyncio.to_thread(input)

async def print_proposals_comments_tree(tree):
    def print_comments(comments, indent=4):
        for c_idx, c_dict in enumerate(comments):
            c = c_dict["comment"]
            votes = c_dict["votes"]
            yes_votes = votes.get("yes", 0)
            no_votes = votes.get("no", 0)
            total_votes = yes_votes + no_votes
            print(
                " " * indent
                + f"Comment {c_idx}: ID {c.id}, User {c.user_id}, "
                f"Score per level: {c.score_per_level}, Text: {c.text}, "
                f"Yes: {yes_votes}, No: {no_votes}, Total votes: {total_votes}"
            )
            print_comments(c_dict.get("replies", []), indent=indent + 2)

    for p_idx, p_dict in enumerate(tree):
        p = p_dict["proposal"]
        prop_votes = p_dict.get("votes", {})
        total_prop_votes = prop_votes.get("total", 0)
        print(
            f"Proposal {p_idx}: ID {p.id}, "
            f"Title: {p.title}, Total votes: {total_prop_votes}"
        )
        print_comments(p_dict.get("comments", []))

async def main():
    await recreate_test_db()
    await create_tables()

    async with AsyncSessionLocal() as db:
        # Create fractal
        fractal = await create_fractal(
            db,
            name="3x3 Test Fractal",
            description="Test with 3 groups of 3 users each",
            start_date=datetime.now(timezone.utc),
            status="waiting",
            settings={"group_size": 3},
        )
        print(f"Created fractal {fractal.id}")

        # Join exactly 9 simulation users (3 groups x 3 users)
        users = []
        for i in range(25):
            u = await join_fractal(
                db,
                {"username": f"sim_user{i+1}", "telegram_id": str(30000 + i)},
                fractal.id,
            )
            users.append(u)
        print(f"Joined 25 simulation users: {[u.username for u in users]}")

        # PAUSE 1: Login as real Telegram user before starting
        await pause("Login as real Telegram user now - fractal is waiting")

        # Start fractal - creates Round 0 with 3 groups of 3
        round0 = await start_fractal(db, fractal.id)
        print(f"Round 0 ID: {round0.id}")

        # Get groups and members
        groups = await get_groups_for_round(db, round0.id)
        print(f"Created {len(groups)} groups")
        
        group_members_map = {}
        for g in groups:
            members = await get_group_members(db, g.id)
            member_ids = [m.user_id for m in members]
            group_members_map[g.id] = [u.id for u in users if u.id in member_ids]
            print(f"Group {g.id} simulation members: {group_members_map[g.id]}")

        # PAUSE 2: First break - real user can now create proposal
        await pause("BREAK 1: Test user can create proposal now")

        # STEP 1: Create 3 proposals (one per group from first sim user)
        proposals_by_group = {}
        for g in groups:
            g_proposals = []
            first_user_id = group_members_map[g.id][0]
            p = await create_proposal(
                db=db,
                fractal_id=fractal.id,
                group_id=g.id,
                round_id=round0.id,
                title=f"Sim Proposal 1 - Group {g.id}",
                body="Initial proposal for 3x3 testing",
                creator_user_id=first_user_id,
            )
            g_proposals.append(p)
            proposals_by_group[g.id] = g_proposals

        print("Created 3 initial proposals:")
        for g_id, props in proposals_by_group.items():
            for p in props:
                print(f"  Group {g_id}: Proposal {p.id}")

        # PAUSE 3: Second break
        await pause("BREAK 2: Check real user proposal, then press enter")

        # STEP 2: Add exactly 2 comments per proposal
        for g_id, proposals in proposals_by_group.items():
            for p in proposals:
                members = group_members_map[g_id]
                # Comment 1 by second user
                c1 = await create_comment(
                    db=db,
                    proposal_id=p.id,
                    user_id=members[1],
                    text=f"First comment on proposal {p.id}",
                    parent_comment_id=None,
                    group_id=g_id,
                )
                # Comment 2 by third user  
                c2 = await create_comment(
                    db=db,
                    proposal_id=p.id,
                    user_id=members[2],
                    text=f"Second comment on proposal {p.id}",
                    parent_comment_id=None,
                    group_id=g_id,
                )
                print(f"Group {g_id} Proposal {p.id}: Added comments {c1.id}, {c2.id}")

        # PAUSE 4: Third break - now real user gets 4 comments
        await pause("BREAK 3: Find real user proposal ID, then press enter")

        # STEP 3: Find real user's proposal and add 4 comments to it
        # Look for proposal not created by sim_users (user_ids 1-9)
        sim_user_ids = {u.id for u in users}
        
        real_user_proposal = None
        for g in groups:
            tree = await get_proposals_comments_tree(db, g.id)
            for p_dict in tree:
                p = p_dict["proposal"]
                if p.creator_user_id not in sim_user_ids:
                    real_user_proposal = p
                    print(f"Found real user proposal: {p.id} (Group {g.id})")
                    break
            if real_user_proposal:
                break

        if real_user_proposal:
            # Add 4 comments from simulation users to real user's proposal
            comment_group_id = real_user_proposal.group_id
            available_users = group_members_map[comment_group_id]
            
            comment_texts = [
                "Great real user proposal!",
                "This deserves attention", 
                "Strong idea for the group",
                "I support this direction"
            ]
            
            for i, user_id in enumerate(available_users[:4]):  # Use up to 4 users
                await create_comment(
                    db=db,
                    proposal_id=real_user_proposal.id,
                    user_id=user_id,
                    text=comment_texts[i % len(comment_texts)],
                    parent_comment_id=None,
                    group_id=comment_group_id,
                )
            print(f"Added 4 comments to real user proposal {real_user_proposal.id}")
        else:
            print("No real user proposal found - check if user created one")

        # Final summary
        print("\n=== FINAL STATE ===")
        for g in groups:
            print(f"\nGroup {g.id}:")
            tree = await get_proposals_comments_tree(db, g.id)
            await print_proposals_comments_tree(tree)

if __name__ == "__main__":
    asyncio.run(main())
