from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import Group
from typing import Optional, List
from datetime import datetime, timedelta
from app.config.settings import settings

class GroupRepo:
    def __init__(self, db=None):
        self.db = db or SessionLocal()

    def create(self, members: List[int], level: int = 0) -> Group:
        g = Group(
            level=level,
            members=members,
            post_deadline=datetime.utcnow() + timedelta(seconds=settings.POST_DEADLINE_SECONDS),
            member_deadline=datetime.utcnow() + timedelta(seconds=settings.MEMBER_DEADLINE_SECONDS)
        )
        self.db.add(g)
        self.db.commit()
        self.db.refresh(g)
        return g

    def get(self, group_id: int) -> Optional[Group]:
        return self.db.query(Group).filter(Group.id == group_id).first()

    def list_by_level(self, level: int) -> List[Group]:
        return self.db.query(Group).filter(Group.level == level).all()

    def save(self, group: Group):
        self.db.add(group)
        self.db.commit()
        self.db.refresh(group)
        return group
