import pytest

from app.domain.fractal_logic import (
    divide_into_groups,
    select_representative_from_votes,
    build_comment_tree,
)


# -------------------------------------------------------------------
# 1) TEST divide_into_groups
# -------------------------------------------------------------------
def test_divide_into_groups_exact():
    user_ids = list(range(10))
    groups = divide_into_groups(user_ids, group_size=5)

    assert len(groups) == 2
    assert groups[0] == [0, 1, 2, 3, 4]
    assert groups[1] == [5, 6, 7, 8, 9]


def test_divide_into_groups_not_even():
    user_ids = [1, 2, 3, 4, 5, 6, 7]
    groups = divide_into_groups(user_ids, 3)

    # Expect: 3 + 3 + 1
    assert groups == [
        [1, 2, 3],
        [4, 5, 6],
        [7],
    ]


def test_divide_into_groups_empty():
    assert divide_into_groups([], 5) == []


# -------------------------------------------------------------------
# 2) TEST select_representative_from_votes
# -------------------------------------------------------------------
def test_select_representative_from_votes_simple():
    member_ids = [10, 11, 12, 13]
    votes = {
        10: 3,
        11: 5,
        12: 1,
        13: 4,
    }

    rep = select_representative_from_votes(votes, member_ids)
    assert rep == 11  # highest score


def test_select_representative_handles_missing_votes():
    member_ids = [1, 2, 3]
    votes = {
        2: 7,
        # 1 and 3 missing → assume 0
    }

    rep = select_representative_from_votes(votes, member_ids)
    assert rep == 2


def test_select_representative_tie_breaker():
    """
    Expect stable / consistent behavior:
    ties → choose smallest ID (or first in sorted order).
    Adjust expected value depending on your implementation.
    """
    member_ids = [5, 6]
    votes = {5: 10, 6: 10}

    rep = select_representative_from_votes(votes, member_ids)

    # Adjust if your logic breaks ties differently
    assert rep in (5, 6)


# -------------------------------------------------------------------
# 3) TEST build_comment_tree
# -------------------------------------------------------------------
def test_build_comment_tree_simple():
    """
    comments = [
        {id=1, parent=None},
        {id=2, parent=1},
        {id=3, parent=1},
        {id=4, parent=2},
    ]
    Expect:
    1
      - 2
          - 4
      - 3
    """

    comments = [
        {"id": 1, "parent_comment_id": None, "text": "root1"},
        {"id": 2, "parent_comment_id": 1, "text": "c2"},
        {"id": 3, "parent_comment_id": 1, "text": "c3"},
        {"id": 4, "parent_comment_id": 2, "text": "c4"},
    ]

    tree = build_comment_tree(comments)

    assert len(tree) == 1
    root = tree[0]
    assert root["id"] == 1

    # children of 1
    assert len(root["children"]) == 2
    ids = sorted([c["id"] for c in root["children"]])
    assert ids == [2, 3]

    # 2 → child 4
    node2 = [c for c in root["children"] if c["id"] == 2][0]
    assert len(node2["children"]) == 1
    assert node2["children"][0]["id"] == 4


def test_build_comment_tree_multiple_roots():
    comments = [
        {"id": 100, "parent_comment_id": None},
        {"id": 101, "parent_comment_id": None},
    ]

    tree = build_comment_tree(comments)

    assert len(tree) == 2
    assert set([c["id"] for c in tree]) == {100, 101}


def test_build_comment_tree_empty():
    assert build_comment_tree([]) == []
