from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import User
from typing import Optional, List

class UserRepo:
    def __init__(self, db=None):
        self.db = db or SessionLocal()

    def create(self, username: str = None, is_ai: bool = False) -> User:
        u = User(username=username, is_ai=1 if is_ai else 0)
        self.db.add(u)
        self.db.commit()
        self.db.refresh(u)
        return u

    def get(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def list_all(self) -> List[User]:
        return self.db.query(User).all()

    def update_current_group(self, user_id: int, group_id: int):
        u = self.get(user_id)
        if u:
            u.current_group_id = group_id
            self.db.add(u)
            self.db.commit()
            self.db.refresh(u)
        return u
