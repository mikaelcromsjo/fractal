# tests/test_adapter_integration.py
"""
Integration tests for Fractal Governance backend and adapters.

This harness uses FastAPI TestClient to simulate user interactions
and verifies the flow:
- Create fractal
- Add users
- Create groups
- Create proposals
- Vote
- Select representatives
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_fractal_flow():
    # Step 1: Create a fractal
    response = client.post("/fractals/create", json={
        "name": "TestFractal",
        "description": "Integration Test",
        "start_date": "2025-12-01"
    })
    assert response.status_code == 200
    fractal = response.json()
    fractal_id = fractal["id"]

    # Step 2: Create users
    user_ids = []
    for i in range(5):
        resp = client.post("/users/create", json={"username": f"user{i}"})
        assert resp.status_code == 200
        user_ids.append(resp.json()["id"])

    # Step 3: Users join fractal
    for uid in user_ids:
        resp = client.post(f"/fractals/{fractal_id}/join", json={"user_id": uid})
        assert resp.status_code == 200

    # Step 4: Create level 0 groups
    resp = client.post(f"/groups/create_level", json={
        "fractal_id": fractal_id,
        "level": 0,
        "users_per_group": 2
    })
    assert resp.status_code == 200
    groups = resp.json()
    assert len(groups) > 0

    # Step 5: Create a proposal by first user
    resp = client.post("/proposals/create", json={
        "user_id": user_ids[0],
        "fractal_id": fractal_id,
        "name": "Test Proposal",
        "description": "Test Description"
    })
    assert resp.status_code == 200
    proposal_id = resp.json()["id"]

    # Step 6: Users vote on the proposal
    for uid in user_ids:
        resp = client.post("/proposals/vote", json={
            "user_id": uid,
            "proposal_id": proposal_id,
            "vote": 7
        })
        assert resp.status_code == 200

    # Step 7: Select representatives
    resp = client.post(f"/groups/{groups[0]['id']}/select_representative")
    assert resp.status_code == 200
    rep_id = resp.json()["representative_id"]
    assert rep_id in user_ids
