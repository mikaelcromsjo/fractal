# app/api/routers/comments.py
"""
Comment endpoints.
"""
from fastapi import APIRouter, HTTPException
from fastapi import Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.services.fractal_service import add_comment
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import Comment
from app.infrastructure.db.session import get_db

router = APIRouter()


class CommentCreateReq(BaseModel):
    proposal_id: int
    user_id: int
    text: str
    parent_comment_id: int | None = None


@router.post("/", summary="Create a comment")
def create_comment(req: CommentCreateReq, db: Session = Depends(get_db)):
    cid = add_comment(db, req.proposal_id, req.user_id, req.text, parent_comment_id=req.parent_comment_id)
    return {"comment_id": cid}


@router.get("/{comment_id}", summary="Get comment")
def get_comment(comment_id: int, db: Session = Depends(get_db)):
    try:
        c = db.query(Comment).get(comment_id)
        if not c:
            raise HTTPException(status_code=404, detail="comment not found")
        return {"id": c.id, "text": c.text, "user_id": c.user_id}
    finally:
        db.close()
