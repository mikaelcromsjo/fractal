#~~~{"id":"70515","variant":"standard","title":"Async Service Layer"} 
# app/domain/fractal_logic.py
from typing import List, Dict, Optional
import random
from datetime import datetime, timezone

# ----------------------------
# Grouping Logic
# ----------------------------
import math

def divide_into_groups(user_ids: List[int], group_size: int) -> List[List[int]]:
    """
    Divide users into groups as evenly as possible, randomly.
    Extra members are distributed to the first few groups.
    """
    if not user_ids:
        return []

    random.shuffle(user_ids)

    n = len(user_ids)
    num_groups = max(1, math.ceil(n / group_size))
    base_size = n // num_groups
    extra = n % num_groups  # first 'extra' groups get 1 more member

    groups = []
    idx = 0
    for i in range(num_groups):
        size = base_size + (1 if i < extra else 0)
        groups.append(user_ids[idx: idx + size])
        idx += size

    return groups




# ----------------------------
# Comment Tree
# ----------------------------
def build_comment_tree(comments: List[Dict]) -> List[Dict]:
    """
    comments: list of dicts {comment: Comment object, ...}
    Returns nested tree
    """
    comment_map = {c["comment"].id: c for c in comments}
    tree = []
    for c in comments:
        parent_id = c["comment"].parent_comment_id
        if parent_id:
            parent = comment_map.get(parent_id)
            if parent:
                parent.setdefault("replies", []).append(c)
        else:
            tree.append(c)
    return tree
