from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

class UserDTO(BaseModel):
    id: int
    username: Optional[str] = None
    is_ai: bool = False
    current_group_id: Optional[int] = None
    level: int = 0

class MessageDTO(BaseModel):
    id: int
    group_id: int
    user_id: int
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    votes: Dict[int, int] = Field(default_factory=dict)

class GroupDTO(BaseModel):
    id: int
    level: int
    members: List[int] = Field(default_factory=list)
    messages: List[MessageDTO] = Field(default_factory=list)
    representative: Optional[int] = None
    post_deadline: Optional[datetime] = None
    member_deadline: Optional[datetime] = None
