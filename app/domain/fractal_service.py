# app/domain/fractal_service.py
"""
Pure domain logic for Fractal Governance.

This module contains only pure functions, operating on plain Python data structures
(lists, dicts). Service-layer code should handle database access and call these
functions with data extracted from models.

Functions included:
- partition_into_groups
- balance_groups
- random_grouping
- select_representative_from_group
- compute_top_proposals
- propagate_proposals
- merge_proposals
- select_representatives_for_all_groups

All inputs/outputs use lists/dicts, no DB access.
"""
from typing import List, Dict, Optional
import random
from statistics import mean


def partition_into_groups(member_ids: List[int], group_size: int) -> List[List[int]]:
    """
    Partition a list of member IDs into sublists of at most `group_size`.
    Last group may be smaller.

    Example:
    >>> partition_into_groups([1,2,3,4,5], 2)
    [[1,2],[3,4],[5]]
    """
    return [member_ids[i:i + group_size] for i in range(0, len(member_ids), group_size)]


def balance_groups(groups: List[List[int]], target_size: int) -> List[List[int]]:
    """
    Redistribute members so groups are as equal as possible.
    Simple flatten + re-chunk method.

    Example:
    >>> balance_groups([[1,2],[3,4,5]], 2)
    [[1,2],[3,4],[5]]
    """
    flat = [u for g in groups for u in g]
    return [flat[i:i + target_size] for i in range(0, len(flat), target_size)]


def random_grouping(members: List[Dict], options: Dict) -> List[List[int]]:
    """
    Randomly group members using 'user_id' key.
    options: may contain 'group_size' and 'seed'.

    Example:
    >>> members = [{"user_id": 1}, {"user_id":2}, {"user_id":3}]
    >>> random_grouping(members, {"group_size":2, "seed":1})
    [[2,3],[1]]
    """
    ids = [m["user_id"] for m in members]
    seed = options.get("seed")
    rng = random.Random(seed)
    rng.shuffle(ids)
    groups = partition_into_groups(ids, options.get("group_size", 8))
    return balance_groups(groups, options.get("group_size", 8))


def select_representative_from_group(messages: List[Dict], members: List[int]) -> Optional[int]:
    """
    Choose a representative for a group based on proposal messages and votes.
    Each message: {'user_id': int, 'votes': {voter_id: score}}
    Returns user_id with highest average score. Falls back to first member.

    Example:
    >>> messages = [
    ...   {"user_id":1, "votes": {2: 8, 3:7}},
    ...   {"user_id":2, "votes": {1:9}}
    ... ]
    >>> select_representative_from_group(messages, [1,2,3])
    2
    """
    author_scores = {}
    for m in messages:
        votes = m.get("votes", {})
        if votes:
            avg = mean(votes.values())
            author_scores.setdefault(m["user_id"], []).append(avg)
    if author_scores:
        avg_scores = {uid: mean(vals) for uid, vals in author_scores.items()}
        best = max(avg_scores.items(), key=lambda kv: kv[1])[0]
        return best
    return members[0] if members else None


def compute_top_proposals(proposals: List[Dict], top_n: int) -> List[Dict]:
    """
    Compute top proposals based on average votes.
    Each proposal: {'id': int, 'votes': {user_id: score}}
    Returns top_n proposals sorted by avg score descending.

    Example:
    >>> proposals = [
    ...   {"id":1, "votes":{1:10,2:9}},
    ...   {"id":2, "votes":{1:5,2:6}}
    ... ]
    >>> compute_top_proposals(proposals, 1)
    [{'id': 1, 'votes': {1: 10, 2: 9}}]
    """
    scored = []
    for p in proposals:
        votes = p.get("votes", {})
        avg = mean(votes.values()) if votes else 0
        scored.append((avg, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_n]]


def propagate_proposals(top_proposals: List[Dict]) -> List[Dict]:
    """
    Convert top proposals to new round proposals (propagation).
    Keeps original title/body and adds 'type':'propagated'

    Example:
    >>> top = [{"id":1, "title":"A","body":"desc"}]
    >>> propagate_proposals(top)
    [{'id':1, 'title':'A', 'body':'desc', 'type':'propagated'}]
    """
    return [{"id": p["id"], "title": p["title"], "body": p.get("body",""), "type":"propagated"} for p in top_proposals]


def merge_proposals(proposals_to_merge: List[Dict], new_title: str, new_body: str) -> Dict:
    """
    Merge multiple proposals into a single proposal.
    Keeps track of merged_from ids.

    Example:
    >>> merge_proposals([{"id":1},{"id":2}], "New","Desc")
    {'title':'New','body':'Desc','type':'merged','merged_from':[1,2]}
    """
    return {
        "title": new_title,
        "body": new_body,
        "type": "merged",
        "merged_from": [p["id"] for p in proposals_to_merge]
    }


def select_representatives_for_all_groups(groups: List[Dict], top_proposals_per_group: Dict[int, List[Dict]]) -> Dict[int, int]:
    """
    For each group, select a representative based on its top proposals and votes.
    groups: [{'group_id': int, 'members':[user_ids]}]
    top_proposals_per_group: {group_id: [proposal dicts with votes]}
    Returns: {group_id: representative_user_id}

    Example:
    >>> groups = [{"group_id":1, "members":[1,2,3]}]
    >>> top = {1:[{"id":10,"user_id":2,"votes":{1:5,2:8}}]}
    >>> select_representatives_for_all_groups(groups, top)
    {1: 2}
    """
    result = {}
    for g in groups:
        proposals = top_proposals_per_group.get(g["group_id"], [])
        # collect messages for rep selection
        messages = [{"user_id": p["user_id"], "votes": p.get("votes",{})} for p in proposals]
        rep = select_representative_from_group(messages, g["members"])
        result[g["group_id"]] = rep
    return result

# This is a future feature if we do not want user votes

def select_representative_from_messages(messages: List[Dict], members: List[int]) -> Optional[int]:
    """
    Choose a representative for a group based on messages and their votes.
    messages: list of dicts with keys: user_id, votes (dict voter_id->score)
    members: list of user ids in the group (fallback)
    Returns selected user_id.
    """
    # aggregate average score per author
    author_scores = {}
    for m in messages:
        votes = m.get("votes", {})
        if votes:
            avg = mean(votes.values())
            author_scores.setdefault(m["user_id"], []).append(avg)
    if author_scores:
        avg_scores = {uid: mean(vals) for uid, vals in author_scores.items()}
        best = max(avg_scores.items(), key=lambda kv: kv[1])[0]
        return best
    # fallback: choose first member or None
    return members[0] if members else None
