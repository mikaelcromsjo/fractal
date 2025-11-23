# app/api/routers/votes.py
"""
Vote endpoints for proposals and comments.
"""
from fastapi import APIRouter, HTTPException
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.services.fractal_service import cast_proposal_vote, cast_comment_vote
from app.infrastructure.db.session import get_db

router = APIRouter()


class ProposalVoteReq(BaseModel):
    user_id: int
    proposal_id: int
    score: int  # 1..10


@router.post("/proposal", summary="Cast a vote on a proposal")
def vote_proposal(req: ProposalVoteReq, db: Session = Depends(get_db)):
    if not (1 <= req.score <= 10):
        raise HTTPException(status_code=400, detail="score must be 1..10")
    cast_proposal_vote(db, req.proposal_id, req.user_id, req.score)
    return {"ok": True}


class CommentVoteReq(BaseModel):
    user_id: int
    comment_id: int
    vote: bool


@router.post("/comment", summary="Cast a vote on a comment")
def vote_comment(req: CommentVoteReq, db: Session = Depends(get_db)):
    cast_comment_vote(db, req.comment_id, req.user_id, req.vote)
    return {"ok": True}
