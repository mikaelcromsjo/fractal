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
    vote_representative_repo,
    close_last_round,
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

        # Join exactly 25 simulation users
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

        # Start fractal - creates Round 0
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

        # STEP 1: Create ~4 proposals per group, from first 4 sim users in that group
        proposals_by_group = {}
        for g in groups:
            g_proposals = []
            member_ids = group_members_map[g.id]
            # Use up to 4 members in each group to create proposals
            for idx, user_id in enumerate(member_ids[:4]):
                p = await create_proposal(
                    db=db,
                    fractal_id=fractal.id,
                    group_id=g.id,
                    round_id=round0.id,
                    title=f"Sim Proposal {idx+1} - Group {g.id}",
                    body=f"Fun and experimental proposal #{idx+1} for group {g.id}",
                    creator_user_id=user_id,
                )
                g_proposals.append(p)
            proposals_by_group[g.id] = g_proposals

        print("Created proposals per group:")
        for g_id, props in proposals_by_group.items():
            for p in props:
                print(f"  Group {g_id}: Proposal {p.id} - {p.title}")

        # NEW PAUSE between proposals and comments
        await pause("BREAK 2b: Explore proposals in UI, then press enter")

        # STEP 2: Add about 4 comments per proposal
        fun_comment_texts = [
            "Love where this is going 🚀",
            "This could shake up the next round in a good way.",
            "Spicy take, but it might just work.",
            "I would totally vote for this on a Monday.",
            "Plot twist: this proposal actually makes sense!",
        ]

        for g_id, proposals in proposals_by_group.items():
            members = group_members_map[g_id]
            # Spread comments among group members
            for p in proposals:
                for i in range(4):  # ~4 comments per proposal
                    author = members[(i + 1) % len(members)]  # rotate authors
                    text = fun_comment_texts[i % len(fun_comment_texts)]
                    c = await create_comment(
                        db=db,
                        proposal_id=p.id,
                        user_id=author,
                        text=f"{text} (on proposal {p.id})",
                        parent_comment_id=None,
                        group_id=g_id,
                    )
                    print(
                        f"Group {g_id} Proposal {p.id}: Added comment {c.id} "
                        f"from user {author}"
                    )

        # PAUSE 3: Third break - now real user gets a bunch of comments
        await pause("BREAK 3: Check comments on proposals in the UI, then press enter")

        # STEP 3: Find real user's proposal and add 4 comments to it
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
            comment_group_id = real_user_proposal.group_id
            available_users = group_members_map[comment_group_id]

            real_comment_texts = [
                "Great real user proposal! Feels very on point.",
                "This deserves extra attention in the next round.",
                "Strong idea, would love to iterate on this.",
                "I support this direction, let’s make it happen.",
            ]

            for i in range(4):
                user_id = available_users[i % len(available_users)]
                await create_comment(
                    db=db,
                    proposal_id=real_user_proposal.id,
                    user_id=user_id,
                    text=real_comment_texts[i],
                    parent_comment_id=None,
                    group_id=comment_group_id,
                )
            print(f"Added 4 comments to real user proposal {real_user_proposal.id}")
        else:
            print("No real user proposal found - check if user created one")

        # NEW EXTRA PAUSE before final summary
        await pause(
            "BREAK 4: Final look in the UI (proposals + comments tree), then press enter"
        )

        # Final summary
        print("\n=== FINAL STATE ===")
        for g in groups:
            print(f"\nGroup {g.id}:")
            tree = await get_proposals_comments_tree(db, g.id)
            await print_proposals_comments_tree(tree)

if __name__ == "__main__":
    asyncio.run(main())
