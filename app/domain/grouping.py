# app/domain/grouping.py

from typing import List, Dict, Callable, Any
from dataclasses import dataclass

@dataclass
class GroupingOptions:
    group_size: int
    preferences_key_weights: Dict[str, float] = None
    allow_mix: bool = True
    random_seed: int = None

# each algorithm must implement:
# def algorithm(members: List[Dict], options: GroupingOptions) -> List[List[int]]
# members: list of user dicts: {"user_id": int, "prefs": {...}, "meta": {...}}

Algorithm = Callable[[List[Dict], GroupingOptions], List[List[int]]]
