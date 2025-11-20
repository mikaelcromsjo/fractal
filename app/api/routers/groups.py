# app/api/routers/groups.py
"""
Group endpoints: create groups for a round (uses service), get group details.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.fractal_service import create_level_groups, promote_representatives_to_next_round, select_representative_for_group
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import Group, GroupMember, User, Proposal, Comment, ProposalVote, CommentVote


router = APIRouter()


class CreateGroupsReq(BaseModel):
    fractal_id: int
    round_level: int = 0
    algorithm: str = "random"
    options: dict = {}


@router.post("/create", summary="Create level groups for a fractal (run grouping algorithm)")
def create_groups(req: CreateGroupsReq):
    created = create_level_groups(req.fractal_id, req.round_level, req.algorithm, req.options)
    return {"created_group_ids": created}


@router.get("/{group_id}", summary="Get group details")
def get_group(group_id: int):
    db = SessionLocal()
    try:
        g = db.query(Group).get(group_id)
        if not g:
            raise HTTPException(status_code=404, detail="group not found")
        members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
        return {"id": g.id, "level": g.level, "members": [m.user_id for m in members]}
    finally:
        db.close()


@router.post("/{group_id}/select_representative", summary="Calculate representative for group")
def select_rep(group_id: int):
    rep = select_representative_for_group(group_id)
    if not rep:
        raise HTTPException(status_code=404, detail="no representative selected")
    return {"group_id": group_id, "representative": rep}


@router.get("/{group_id}/status", summary="Get status of a group")
def group_status(group_id: int):
    db: Session = SessionLocal()
    try:
        group = db.query(Group).get(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        # --- Users in the group ---
        members = (
            db.query(User)
            .join(GroupMember, GroupMember.user_id == User.id)
            .filter(GroupMember.group_id == group_id)
            .all()
        )
        users_info = [{"id": u.id, "username": u.username, "is_ai": u.is_ai} for u in members]

        # --- Proposals in the group ---
        proposals = db.query(Proposal).filter(Proposal.group_id == group_id).all()
        proposal_info = []
        for p in proposals:
            votes = db.query(ProposalVote).filter(ProposalVote.proposal_id == p.id).all()
            total_score = sum(v.score for v in votes) if votes else None

            # --- Comments for the proposal (threaded) ---
            comments = db.query(Comment).filter(Comment.proposal_id == p.id, Comment.parent_comment_id == None).all()
            def serialize_comment(c):
                votes_c = db.query(CommentVote).filter(CommentVote.comment_id == c.id).all()
                yes_count = sum(1 for v in votes_c if v.vote)
                no_count = sum(1 for v in votes_c if not v.vote)
                children = db.query(Comment).filter(Comment.parent_comment_id == c.id).all()
                return {
                    "id": c.id,
                    "user_id": c.user_id,
                    "text": c.text,
                    "votes": {"yes": yes_count, "no": no_count} if votes_c else None,
                    "replies": [serialize_comment(ch) for ch in children]
                }

            serialized_comments = [serialize_comment(c) for c in comments]

            proposal_info.append({
                "id": p.id,
                "title": p.title,
                "body": p.body,
                "creator_user_id": p.creator_user_id,
                "total_score": total_score,
                "comments": serialized_comments
            })

        return {
            "group_id": group.id,
            "level": group.level,
            "members": users_info,
            "proposals": proposal_info,
        }
    finally:
        db.close()
