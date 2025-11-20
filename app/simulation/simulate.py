# app/simulation/simulate.py
"""
Simulation script: creates X AI users, joins a fractal, generates groups,
creates proposals/comments, casts votes, and selects representatives.

Uses services/repositories directly (no HTTP calls).
"""

import random
from faker import Faker
from app.services.fractal_service import FractalService
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.repositories import UserRepository, FractalRepository, GroupRepository, ProposalRepository, VoteRepository

fake = Faker()
NUM_USERS = 50
USERS_PER_GROUP = 5
PROPOSALS_PER_USER = 2
COMMENTS_PER_USER = 3

def run_simulation():
    db = SessionLocal()
    user_repo = UserRepository(db)
    fractal_repo = FractalRepository(db)
    group_repo = GroupRepository(db)
    proposal_repo = ProposalRepository(db)
    vote_repo = VoteRepository(db)
    service = FractalService(user_repo, fractal_repo, group_repo, proposal_repo, vote_repo)

    # Create fractal
    fractal = service.create_fractal(name="SimFractal", description="Simulation", start_date="2025-12-01")
    print(f"Created fractal {fractal.name}")

    # Create AI users
    users = []
    for _ in range(NUM_USERS):
        u = service.create_user(username=fake.user_name())
        users.append(u)
        service.join_fractal(fractal.id, u.id)

    # Create level 0 groups
    groups = service.create_level_groups(fractal.id, 0, USERS_PER_GROUP)

    # Each user creates proposals
    proposals = []
    for u in users:
        for _ in range(PROPOSALS_PER_USER):
            p = service.create_proposal(fractal.id, u.id, f"Prop-{fake.word()}", fake.sentence())
            proposals.append(p)

    # Each user comments randomly
    for u in users:
        for _ in range(COMMENTS_PER_USER):
            target = random.choice(proposals)
            service.create_comment(target.id, u.id, fake.sentence())

    # Cast random votes
    for u in users:
        for p in proposals:
            service.vote_proposal(u.id, p.id, random.randint(1, 10))

    # Select representatives per group
    for g in groups:
        rep = service.select_representative_for_group(g.id)
        print(f"Group {g.id} selected representative {rep.id} ({rep.username})")

    # Aggregate top proposals
    top_proposals = service.compute_top_proposals(fractal.id)
    print("Top proposals:")
    for p in top_proposals:
        print(f"- {p.name} votes: {p.vote_count}")

if __name__ == "__main__":
    run_simulation()
