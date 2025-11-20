# tests/test_basic.py
"""
Minimal starter tests for Fractal Governance backend.
- Test FastAPI endpoints (create fractal, join user)
- Test domain logic (partition_into_groups)
"""

import pytest
from httpx import AsyncClient
from fastapi import status

from main import app
from app.domain.fractal_service import partition_into_groups

# ------------------------
# Domain Logic Test
# ------------------------

def test_partition_into_groups_basic():
    members = [1, 2, 3, 4, 5]
    groups = partition_into_groups(members, 2)
    # Expected groups: [[1,2],[3,4],[5]]
    assert groups == [[1,2],[3,4],[5]]

# ------------------------
# FastAPI Endpoint Tests
# ------------------------

@pytest.mark.asyncio
async def test_create_and_join_fractal():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create a fractal
        response = await ac.post("/fractal/", json={
            "name": "Test Fractal",
            "description": "A simple test",
            "start_date": "2025-11-20T12:00:00"
        })
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        fractal_id = data["id"]
        assert data["name"] == "Test Fractal"

        # Join a user
        response2 = await ac.post(f"/fractal/{fractal_id}/join", json={
            "user_name": "Alice"
        })
        assert response2.status_code == status.HTTP_200_OK
        user_data = response2.json()
        assert user_data["user_name"] == "Alice"
        assert "id" in user_data
