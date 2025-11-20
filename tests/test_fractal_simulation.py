# tests/test_fractal_simulation.py
"""
Simulation test harness for Fractal Governance backend.

- Mocks 128 AI users
- Creates fractal, groups, proposals, comments
- Casts votes
- Forces round progression
- Aggregates results
"""

import asyncio
import random
from faker import Faker
import pytest
from httpx import AsyncClient
from main import app

NUM_USERS = 128
USERS_PER_GROUP = 8
PROPOSALS_PER_USER = 2
COMMENTS_PER_USER = 3
faker = Faker()

@pytest.mark.asyncio
async def test_full_fractal_simulation():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # 1) Create fractal
        fractal_resp = await ac.post("/fractal/", json={
            "name": "Simulated Fractal",
            "description": "Full test simulation",
            "start_date": "2025-11-20T12:00:00"
        })
        fractal_data = fractal_resp.json()
        fractal_id = fractal_data["id"]

        # 2) Create users and join fractal
        user_ids = []
        for _ in range(NUM_USERS):
            user_name = faker.first_name()
            resp = await ac.post(f"/fractal/{fractal_id}/join", json={"user_name": user_name})
            user_data = resp.json()
            user_ids.append(user_data["id"])

        # 3) Create level 0 groups
        groups_resp = await ac.post(f"/fractal/{fractal_id}/groups", json={"users_per_group": USERS_PER_GROUP})
        groups = groups_resp.json()

        # 4) Each user creates proposals
        proposal_ids = []
        for uid in user_ids:
            for _ in range(PROPOSALS_PER_USER):
                title = faker.sentence(nb_words=4)
                desc = faker.text(max_nb_chars=50)
                resp = await ac.post(f"/fractal/{fractal_id}/proposal", json={
                    "user_id": uid,
                    "title": title,
                    "description": desc
                })
                proposal_data = resp.json()
                proposal_ids.append(proposal_data["id"])

        # 5) Users comment randomly
        comment_ids = []
        for uid in user_ids:
            for _ in range(COMMENTS_PER_USER):
                target = random.choice(proposal_ids)
                comment_text = faker.sentence(nb_words=6)
                resp = await ac.post(f"/comment", json={
                    "user_id": uid,
                    "target_id": target,
                    "text": comment_text
                })
                comment_data = resp.json()
                comment_ids.append(comment_data["id"])

        # 6) Users vote randomly on proposals
        for uid in user_ids:
            for pid in proposal_ids:
                vote = random.randint(1,10)
                await ac.post(f"/proposal_vote", json={"user_id": uid, "proposal_id": pid, "vote": vote})

        # 7) Users vote randomly on comments
        for uid in user_ids:
            for cid in comment_ids:
                vote = random.choice(["yes","no"])
                await ac.post(f"/comment_vote", json={"user_id": uid, "comment_id": cid, "vote": vote})

        # 8) Force round progression: select representatives
        reps_resp = await ac.post(f"/fractal/{fractal_id}/representatives")
        reps_data = reps_resp.json()
        assert len(reps_data) > 0

        # 9) Print summary
        print(f"Total users: {NUM_USERS}")
        print(f"Total proposals: {len(proposal_ids)}")
        print(f"Total comments: {len(comment_ids)}")
        print(f"Representatives selected: {len(reps_data)}")
