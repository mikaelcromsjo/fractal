#~~~{"id":"70515","variant":"standard","title":"Async Service Layer"} 
# app/domain/fractal_logic.py
from typing import List, Dict, Optional
import random
from datetime import datetime, timezone
from datetime import datetime, timedelta

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


def get_round_index(fractal, now=None):
    """Returns how many full rounds have elapsed since start_date."""
    now = now or datetime.utcnow()
    if not fractal.start_date or "round_time" not in fractal.meta:
        return None
    
    # ✅ round_time is MINUTES → convert to timedelta(minutes=)
    round_time_minutes = fractal.meta["round_time"]
    round_duration = timedelta(minutes=round_time_minutes)
    
    elapsed = now - fractal.start_date
    full_rounds = int(elapsed // round_duration)
    return full_rounds


def get_round_times(fractal):
    """Returns round_time as timedelta and half_time as timedelta"""
    # ✅ round_time is MINUTES → convert to timedelta(minutes=)
    round_time_minutes = fractal.meta["round_time"]
    round_duration = timedelta(minutes=round_time_minutes)
    half_time = round_duration / 2
    return round_duration, half_time

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

