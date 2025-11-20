# app/api/routers/votes.py
"""
Vote endpoints for proposals and comments.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.fractal_service import cast_proposal_vote, cast_comment_vote

router = APIRouter()


class ProposalVoteReq(BaseModel):
    user_id: int
    proposal_id: int
    score: int  # 1..10


@router.post("/proposal", summary="Cast a vote on a proposal")
def vote_proposal(req: ProposalVoteReq):
    if not (1 <= req.score <= 10):
        raise HTTPException(status_code=400, detail="score must be 1..10")
    cast_proposal_vote(req.proposal_id, req.user_id, req.score)
    return {"ok": True}


class CommentVoteReq(BaseModel):
    user_id: int
    comment_id: int
    vote: bool


@router.post("/comment", summary="Cast a vote on a comment")
def vote_comment(req: CommentVoteReq):
    cast_comment_vote(req.comment_id, req.user_id, req.vote)
    return {"ok": True}
