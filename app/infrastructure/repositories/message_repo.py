from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import Message
from typing import Optional, List

class MessageRepo:
    def __init__(self, db=None):
        self.db = db or SessionLocal()

    def create(self, group_id: int, user_id: int, text: str) -> Message:
        m = Message(group_id=group_id, user_id=user_id, text=text)
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return m

    def list_by_group(self, group_id: int) -> List[Message]:
        return self.db.query(Message).filter(Message.group_id == group_id).all()

    def get(self, message_id: int) -> Optional[Message]:
        return self.db.query(Message).filter(Message.id == message_id).first()

    def save(self, message: Message):
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
