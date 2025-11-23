# app/api/routers/proposals.py
"""
Proposal endpoints: create proposal, merge proposals.
"""
from fastapi import APIRouter, HTTPException
from fastapi import Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.services.fractal_service import add_proposal
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import (
    Fractal, FractalMember, User, Group, GroupMember, Proposal, ProposalVote, Comment, CommentVote, Round
)
from sqlalchemy import func
from app.infrastructure.db.session import get_db

router = APIRouter()


class ProposalCreateReq(BaseModel):
    creator_user_id: int
    title: str
    body: str = ""

@router.post("/", summary="Create a proposal (auto group/round detection)")
def create_proposal(req: ProposalCreateReq, db: Session = Depends(get_db)):
    try:
        # -------------------------
        # 1. Find active fractal
        # -------------------------
        fractal = (
            db.query(Fractal)
            .join(FractalMember)
            .filter(
                FractalMember.user_id == req.creator_user_id,
                Fractal.status == "in_progress"
            )
            .first()
        )

        if not fractal:
            raise HTTPException(400, "User is not part of an active fractal")

        # Capture ID early to avoid DetachedInstanceError
        fid = fractal.id

        # -------------------------
        # 2. Find active round
        # -------------------------
        round_obj = (
            db.query(Round)
            .filter(
                Round.fractal_id == fid,
                Round.status == "open"
            )
            .order_by(Round.level.desc())
            .first()
        )

        if not round_obj:
            raise HTTPException(400, "No open round exists")

        rid = round_obj.id

        # enforce that round 0 only happens once
        first_round_level = (
            db.query(func.min(Round.level))
            .filter(Round.fractal_id == fid)
            .scalar()
        )
        if round_obj.level == 0 and first_round_level != 0:
            raise HTTPException(400, "Round 0 invalid (not the first round)")

        # -------------------------
        # 3. Verify user is in the fractal
        # -------------------------
        fm = (
            db.query(FractalMember)
            .filter(
                FractalMember.fractal_id == fid,
                FractalMember.user_id == req.creator_user_id
            )
            .first()
        )
        if not fm:
            print("DEBUG: User is not a member of fractal")
            raise HTTPException(403, "User is not a member of this fractal")

        # -------------------------
        # 4. Find user's group in this round
        # -------------------------
        gm = (
            db.query(GroupMember)
            .join(Group)
            .filter(
                Group.round_id == rid,
                GroupMember.user_id == req.creator_user_id
            )
            .first()
        )
        if not gm:
            print("DEBUG: User is not in a group for this round")
            print(f"rid (round_id): {rid}, fid (fractal_id): {fid}, creator_user_id: {req.creator_user_id}")
            raise HTTPException(403, "User is not assigned to a group in this round")

        gid = gm.group_id

        # -------------------------
        # 5. Create proposal
        # -------------------------
        pid = add_proposal(
            db,
            fractal_id=fid,
            group_id=gid,
            round_id=rid,
            title=req.title,
            body=req.body,
            creator_user_id=req.creator_user_id,
            ptype="base"
        )

        return {
            "proposal_id": pid,
            "fractal_id": fid,
            "round_id": rid,
            "group_id": gid
        }

    finally:
        db.close()

class MergeReq(BaseModel):
    ids: list[int]
    title: str
    body: str
    creator_user_id: int = None


@router.post("/{proposal_id}/merge", summary="Merge proposals into a new one")
def merge_proposal(proposal_id: int, req: MergeReq, db: Session = Depends(get_db)):
    """
    Create a merged proposal using existing proposal ids.
    The new proposal will get meta.merged_from = [...]
    """
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
