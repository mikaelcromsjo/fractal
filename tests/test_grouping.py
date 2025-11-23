# tests/test_partition.py
import pytest
from app.domain.fractal_service import partition_into_groups

# -------------------------------
# Basic cases
# -------------------------------

def test_partition_exact_multiple():
    # 21 members, target 7 → exactly 3 groups of 7
    members = list(range(1, 22))
    groups = partition_into_groups(members, 7)
    sizes = [len(g) for g in groups]
    assert sizes == [7, 7, 7]

def test_partition_small_list():
    # 5 members, target 7 → only 1 group
    members = list(range(1, 6))
    groups = partition_into_groups(members, 7)
    sizes = [len(g) for g in groups]
    assert sizes == [5]

# -------------------------------
# Leftover handling
# -------------------------------

def test_partition_leftover_last_small():
    # 16 members, target 7 → expect [6,5,5]
    members = list(range(1, 17))
    groups = partition_into_groups(members, 7)
    sizes = [len(g) for g in groups]
    assert sizes == [6, 5, 5]

def test_partition_leftover_last_large():
    # 23 members, target 7 → last group would be bigger if naive
    # Ideal: distribute so sizes differ by at most 1
    members = list(range(1, 24))
    groups = partition_into_groups(members, 7)
    sizes = [len(g) for g in groups]
    assert sizes == [6, 6, 6, 5]

# -------------------------------
# Realistic large case
# -------------------------------

def test_partition_50_users():
    members = list(range(1, 51))
    groups = partition_into_groups(members, 7)
    sizes = [len(g) for g in groups]
    # 50 / 7 → 7 groups of 7 or 8
    assert sizes == [7, 7, 6, 6, 6, 6, 6, 6]
# -------------------------------
# Edge case: target size 1
# -------------------------------

def test_partition_target_one():
    members = list(range(1, 5))
    groups = partition_into_groups(members, 1)
    sizes = [len(g) for g in groups]
    assert sizes == [1, 1, 1, 1]

# -------------------------------
# Edge case: empty list
# -------------------------------

def test_partition_empty():
    groups = partition_into_groups([], 7)
    assert groups == []
