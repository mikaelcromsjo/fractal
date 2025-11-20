from typing import List
from app.infrastructure.repositories.group_repo import GroupRepo
from app.infrastructure.repositories.user_repo import UserRepo
from app.infrastructure.repositories.message_repo import MessageRepo
from app.domain.fractal_service import partition_into_groups, select_representative_from_group
from app.config.settings import settings

class GroupService:
    def __init__(self, group_repo: GroupRepo = None, user_repo: UserRepo = None, msg_repo: MessageRepo = None):
        self.group_repo = group_repo or GroupRepo()
        self.user_repo = user_repo or UserRepo()
        self.msg_repo = msg_repo or MessageRepo()

    def create_level0_from_users(self, user_ids: List[int]) -> List[int]:
        chunks = partition_into_groups(user_ids, settings.GROUP_SIZE)
        created = []
        for c in chunks:
            g = self.group_repo.create(members=c, level=0)
            for uid in c:
                self.user_repo.update_current_group(uid, g.id)
            created.append(g.id)
        return created

    def add_post(self, user_id: int, text: str):
        user = self.user_repo.get(user_id)
        if not user or not user.current_group_id:
            raise ValueError("User not in group")
        m = self.msg_repo.create(group_id=user.current_group_id, user_id=user_id, text=text)
        return m

    def vote(self, user_id: int, message_id: int, score: int):
        m = self.msg_repo.get(message_id)
        if not m:
            raise ValueError("Message not found")
        votes = m.votes or {}
        votes[str(user_id)] = int(score)
        m.votes = votes
        self.msg_repo.save(m)
        return m

    def select_representative(self, group_id: int):
        g = self.group_repo.get(group_id)
        if not g:
            return None
        # build messages list for domain function
        msgs = []
        for m in self.msg_repo.list_by_group(group_id):
            msgs.append({"user_id": m.user_id, "votes": {int(k): v for k, v in (m.votes or {}).items()}})
        rep = select_representative_from_group(msgs, g.members)
        g.representative = rep
        self.group_repo.save(g)
        return rep
