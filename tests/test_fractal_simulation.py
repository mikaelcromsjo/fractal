# tests/test_ai_simulation_integration.py
import pytest
import asyncio
import random
from faker import Faker
import httpx
from main import app  # adjust if your FastAPI instance is elsewhere
from httpx import ASGITransport

FAKE = Faker()
NR_USERS = 10
PROPOSALS_PER_USER = 2
USERS = {}

BASE_URL = "http://localhost:8030/"

@pytest.fixture(scope="module")
async def async_client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client

@pytest.fixture(scope="module")
async def create_users():
    """
    Create NR_USERS mock AI users locally.
    No API calls, no backend dependencies.

    Returns:
        Dict[int, Dict]: A dictionary indexed 1..NR_USERS,
        each entry containing:
            {
                "id": int,          # simulated user ID
                "name": str,        # fake name
                "is_ai": True,
                "other_id": str     # stable reference ID
            }
    """
    USERS = {}

    for i in range(1, NR_USERS + 1):
        username = FAKE.name()
        USERS[i] = {
            "id": i,                      # local simulated ID
            "name": username,
            "is_ai": True,
            "other_id": f"ai_{i}",
        }

    return USERS


@pytest.mark.anyio
async def test_full_fractal_flow(async_client, create_users):
    users = create_users

    # 1️⃣ Create a fractal
    fractal_data = {
        "name": FAKE.word(),
        "description": FAKE.sentence(),
        "start_date": "2025-11-21T00:00:00",
        "settings": {}
    }
    resp = await async_client.post("/fractals/", json=fractal_data)
    assert resp.status_code == 200
    fractal = resp.json()
    fractal_id = fractal["id"]

    # 2️⃣ Join all users properly and store assigned user_ids
    for i, u in users.items():
        resp = await async_client.post(
            f"/fractals/{fractal_id}/join",
            json={
                "username": u["name"],
                "other_id": f"ai_{i}",
                "is_ai": True
            }
        )

        # Ensure no crash if backend returns an error
        data = resp.json()
        if resp.status_code != 200:
            print(f"[ERROR] join user {i}: {data}")
            continue

        # Extract assigned user_id and store in users dict
        joined_id = data.get("user_id") or data.get("id")
        if joined_id is None:
            print(f"[ERROR] join user {i}: missing user_id")
            continue

        USERS[i]["id"] = joined_id

    # 3️⃣ Start the fractal
    resp = await async_client.post(f"/fractals/{fractal_id}/start")
    assert resp.status_code == 200

    round_number = 1
    while True:
        print(f"\n=== Round {round_number} ===")

        # 4️⃣ Users submit proposals
        for i, u in users.items():
            for p in range(PROPOSALS_PER_USER):
                await async_client.post("/proposals/", json={
                    "creator_user_id": u["id"],
                    "title": FAKE.sentence(),
                    "body": FAKE.paragraph()
                })

        # 5️⃣ Users comment on all proposals in their group
        for i, u in users.items():
            status_resp = await async_client.get(f"/fractals/{fractal_id}/users/{u['id']}/status")
            status = status_resp.json()
            proposals_in_group = status.get("proposals", [])
            for p in proposals_in_group:
                await async_client.post("/comments/", json={
                    "proposal_id": p["id"],
                    "user_id": u["id"],
                    "text": FAKE.sentence()
                })

        # 6️⃣ Users vote on proposals and comments
        for i, u in users.items():
            status_resp = await async_client.get(f"/fractals/{fractal_id}/users/{u['id']}/status")
            status = status_resp.json()
            members = status.get("members", [])
            proposals_in_group = status.get("proposals", [])

            # Vote on proposals
            for p in proposals_in_group:
                for m in members:
                    if m["id"] != p["creator_user_id"]:
                        await async_client.post("/votes/proposal", json={
                            "user_id": m["id"],
                            "proposal_id": p["id"],
                            "score": random.randint(1, 5)
                        })

            # Vote on comments
            for p in proposals_in_group:
                for c in p.get("comments", []):
                    for m in members:
                        if m["id"] != c["user_id"]:
                            await async_client.post("/votes/comment", json={
                                "user_id": m["id"],
                                "comment_id": c["id"],
                                "vote": random.choice([True, False])
                            })

        # 7️⃣ Users vote for representatives
        for i, u in users.items():
            status_resp = await async_client.get(f"/fractals/{fractal_id}/users/{u['id']}/status")
            members = status_resp.json().get("members", [])
            for m in members:
                if m["id"] != u["id"]:
                    await async_client.post(
                        f"/fractals/{fractal_id}/users/{u['id']}/vote_representative",
                        json={
                            "user_id": u["id"],
                            "voted_user_id": m["id"]
                        }
                    )

        # 8️⃣ Close round
        resp = await async_client.post(f"/fractals/{fractal_id}/close_round")
        round_info = resp.json()
        print(f"Round {round_number} closed:", round_info)

        # 9️⃣ Stop if no next round
        if not round_info.get("next_round_started"):
            print("Fractal ended: only one group remains.")
            break

        round_number += 1

