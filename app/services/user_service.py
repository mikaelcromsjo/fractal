from app.infrastructure.repositories.user_repo import UserRepo

class UserService:
    def __init__(self, repo: UserRepo = None):
        self.repo = repo or UserRepo()

    def create_user(self, username: str = None, is_ai: bool = False):
        return self.repo.create(username=username, is_ai=is_ai)

    def list_users(self):
        return self.repo.list_all()
