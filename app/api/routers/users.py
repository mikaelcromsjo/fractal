# app/api/routers/users.py
"""
User endpoints: create users, list users, set prefs.
"""
from fastapi import APIRouter, HTTPException
from fastapi import Depends
from sqlalchemy.orm import Session

from pydantic import BaseModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import User, Proposal, FractalMember
from app.infrastructure.db.session import get_db

router = APIRouter()


class UserCreateReq(BaseModel):
    username: str = None
    telegram_id: str = None
    discord_id: str = None
    other_id: str = None
    is_ai: bool = False

@router.post("/", summary="Create a user")
def create_user(req: UserCreateReq, db: Session = Depends(get_db)):
    try:
        # --- Check if a user already exists on any platform ---
        user = None
        if req.telegram_id:
            user = db.query(User).filter(User.telegram_id == req.telegram_id).first()
        elif req.discord_id:
            user = db.query(User).filter(User.discord_id == req.discord_id).first()
        elif req.other_id:
            user = db.query(User).filter(User.other_id == req.other_id).first()
        elif req.is_ai:
            if req.username:
                user = db.query(User).filter(User.username == req.username, User.is_ai == True).first()

        # --- Return existing user if found ---
        if user:
            return {"id": user.id, "username": user.username, "info": "Already exists"}

        # --- Create new user ---
        user = User(
            username=req.username or "Anonymous",
            telegram_id=req.telegram_id,
            discord_id=req.discord_id,
            other_id=req.other_id,
            is_ai=req.is_ai
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"id": user.id, "username": user.username}

    finally:
        db.close()

@router.get("/", summary="List users")
def list_users(db: Session = Depends(get_db)):
    try:
        rows = db.query(User).all()
        return {"users": [{"id": r.id, "username": r.username, "telegram_id": r.telegram_id} for r in rows]}
    finally:
        db.close()

# api/routers/users.py
@router.get("/{user_id}/todo", summary="Get TODO items for a user")
def get_todo(user_id: int, db: Session = Depends(get_db)):
    try:
        # For simplicity: return proposals/comments user can vote on
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # Example: proposals in user's fractals without user vote
        proposals = db.query(Proposal).join(FractalMember, Proposal.fractal_id == FractalMember.fractal_id)\
            .filter(FractalMember.user_id == user_id).all()
        todo_list = [{"proposal_id": p.id, "title": p.title} for p in proposals]
        return todo_list
    finally:
        db.close()        
