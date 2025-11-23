# tests/test_domain.py
from app.domain.fractal_service import partition_into_groups

def test_partition_basic():
    members = [1,2,3,4,5]
    groups = partition_into_groups(members, 2)
    assert groups == [[1,2],[3,4],[5]]

def test_partition_empty():
    assert partition_into_groups([], 3) == []

def test_partition_group_size_larger_than_members():
    members = [1,2]
    groups = partition_into_groups(members, 5)
    assert groups == [[1,2]]

    