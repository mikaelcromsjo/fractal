# app/api/routers/proposals.py
"""
Proposal endpoints: create proposal, merge proposals.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.fractal_service import add_proposal
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import Proposal, ProposalMerge

router = APIRouter()


class ProposalCreateReq(BaseModel):
    fractal_id: int
    group_id: int
    round_id: int
    title: str
    body: str = ""
    creator_user_id: int = None


@router.post("", summary="Create a proposal (base rounds only)")
def create_proposal(req: ProposalCreateReq):
    pid = add_proposal(req.fractal_id, req.group_id, req.round_id, req.title, req.body, req.creator_user_id, ptype="base")
    return {"proposal_id": pid}


class MergeReq(BaseModel):
    ids: list[int]
    title: str
    body: str
    creator_user_id: int = None


@router.post("/{proposal_id}/merge", summary="Merge proposals into a new one")
def merge_proposal(proposal_id: int, req: MergeReq):
    """
    Create a merged proposal using existing proposal ids.
    The new proposal will get meta.merged_from = [...]
    """
    db = SessionLocal()
    try:
        # create new proposal
        new = Proposal(fractal_id=None, group_id=None, round_id=None, title=req.title, body=req.body, creator_user_id=req.creator_user_id, type="merged", meta={"merged_from": req.ids})
        db.add(new)
        db.commit()
        db.refresh(new)
        # add merge records
        for mid in req.ids:
            pm = ProposalMerge(new_proposal_id=new.id, merged_from_proposal_id=mid)
            db.add(pm)
        db.commit()
        return {"merged_proposal_id": new.id}
    finally:
        db.close()
