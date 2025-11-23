# app/api/routers/fractals.py
"""
Router for fractal lifecycle: create fractal, join, start/force start.
"""
from fastapi import APIRouter, HTTPException
from fastapi import Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone
from app.infrastructure.db.session import get_db

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.models import (
    Fractal, FractalMember, User, Group, GroupMember, Proposal, ProposalVote, Comment, CommentVote, Round, RepresentativeSelection
)

from app.services.fractal_service import (
    promote_representatives_to_next_round,
    calculate_proposal_scores,
    calculate_comment_votes,
    create_level_groups
)

DEBUG = False
router = APIRouter()


class FractalCreateRequest(BaseModel):
    name: str
    description: str = ""
    start_date: datetime
    settings: dict = {}


@router.get("/", summary="List all fractals")
def list_fractals(db: Session = Depends(get_db)):
    """
    Return a list of all fractals.
    """
    try:
        fractals = db.query(Fractal).all()
        return [
            {
                "id": f.id,
                "name": f.name,
                "description": f.description,
                "start_date": str(f.start_date),
                "created_at": str(f.created_at),
                "status": f.status
            }
            for f in fractals
        ]
    finally:
        db.close()

@router.post("/", summary="Create a new fractal")
def create_fractal(req: FractalCreateRequest, db: Session = Depends(get_db)):
    """
    Create a fractal with a start_date. Members can join until start_date.
    """
    try:
        f = Fractal(name=req.name, description=req.description, start_date=req.start_date, settings=req.settings)
        db.add(f)
        db.commit()
        db.refresh(f)
        return {"id": f.id, "name": f.name, "start_date": str(f.start_date)}
    finally:
        db.close()


class JoinRequest(BaseModel):
    telegram_id: str = None
    discord_id: str = None
    other_id: str = None
    username: str = None
    is_ai: bool = False


@router.post("/{fractal_id}/join", summary="Join a fractal")
def join_fractal(fractal_id: int, req: JoinRequest, db: Session = Depends(get_db)):
    """
    Add a user to a fractal. 
    If the user does not exist on any platform, create them.
    """
    try:
        fractal = db.query(Fractal).get(fractal_id)
        if not fractal:
            raise HTTPException(status_code=404, detail="Fractal not found")

        # --- Debug print ---
        if DEBUG: print(f"[DEBUG] Searching user: {req.dict()}")

        # --- Look for existing user on any platform ---
        user = None
        if req.telegram_id:
            user = db.query(User).filter(User.telegram_id == req.telegram_id).first()
        if not user and req.discord_id:
            user = db.query(User).filter(User.discord_id == req.discord_id).first()
        if not user and req.other_id:
            user = db.query(User).filter(User.other_id == req.other_id).first()
        if not user and req.is_ai and req.username:
            user = db.query(User).filter(User.username == req.username, User.is_ai == True).first()

        # --- Create new user if not exists ---
        if not user:
            user = User(
                username=req.username or f"AIUser_{random.randint(1000,9999)}",
                telegram_id=req.telegram_id,
                discord_id=req.discord_id,
                other_id=req.other_id,
                is_ai=req.is_ai
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[INFO] Created new user: {user.id}")

        # --- Check if already a member of this fractal ---
        fm = db.query(FractalMember).filter(
            FractalMember.fractal_id == fractal_id,
            FractalMember.user_id == user.id
        ).first()
        if fm:
            return {"ok": True, "member_id": fm.id, "info": "Already a member"}


        status = db.query(Fractal.status).filter_by(id=fractal_id).scalar()
        if status != "waiting":
            return {"ok": False, "info": "Fractal is not open"}

        # --- Add as member ---
        fm = FractalMember(fractal_id=fractal_id, user_id=user.id)
        db.add(fm)
        db.commit()
        db.refresh(fm)
        return {"ok": True, "member_id": fm.id}

    finally:
        db.close()

@router.post("/{fractal_id}/start", summary="Force start fractal (admin)")
def start_fractal(fractal_id: int, db: Session = Depends(get_db)):
    """
    Force-start a fractal: create round 0 and groups.
    Uses existing service-layer functions only.
    """
    try:
        # --- 1. Load fractal ---
        fractal = db.query(Fractal).filter(Fractal.id == fractal_id).first()
        if not fractal:
            raise HTTPException(status_code=404, detail="Fractal not found")

        # --- 2. Mark fractal as running ---
        fractal.status = "in_progress"
        db.add(fractal)

        # Capture primitive values before commit to avoid DetachedInstanceError
        fid = fractal.id

        db.commit()  # commit changes

        # --- 3. Start round 0 and create groups ---
        create_level_groups(
            db,
            fractal_id=fid,   # use captured primitive ID
            round_level=0,
            algorithm="random",
            options={}
        )
        

        return {
            "ok": True,
            "fractal_id": fid,
            "round_started": 0
        }

    finally:
        db.close()

@router.post("/{fractal_id}/users/{user_id}/vote_representative", summary="Vote for a representative in current group")
def vote_representative(fractal_id: int, user_id: int, voted_user_id: int, db: Session = Depends(get_db)):
    """
    Let a user vote for a representative within their current group in the given fractal.
    Rules:
        - User cannot vote for themselves
        - Only members of the group can vote
    """
    # --- Find current round ---
    current_round = db.query(Round).filter(Round.fractal_id == fractal_id).order_by(Round.level.desc()).first()
    if not current_round:
        raise HTTPException(status_code=404, detail="No active round in fractal")

    # --- Find the user's group in the current round ---
    group_member = db.query(GroupMember).join(Group).filter(
        Group.round_id == current_round.id,
        GroupMember.user_id == user_id
    ).first()
    if not group_member:
        raise HTTPException(status_code=403, detail="User not assigned to a group in current round")

    group_id = group_member.group_id

    # --- Check voted user is in the same group ---
    voted_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == voted_user_id
    ).first()
    if not voted_member:
        raise HTTPException(status_code=400, detail="Voted user not in your group")

    if user_id == voted_user_id:
        raise HTTPException(status_code=400, detail="Cannot vote for yourself")

    # --- Record the vote ---
    vote = RepresentativeSelection(
        group_id=group_id,
        representative_user_id=voted_user_id,
        method="vote"
    )
    db.add(vote)
    db.commit()

    return {"ok": True, "voter_id": user_id, "voted_for": voted_user_id, "group_id": group_id}


@router.get("/{fractal_id}/users/{user_id}/status", summary="Get current group status for a user")
def user_group_status(fractal_id: int, user_id: int, db: Session = Depends(get_db)):
    try:
        # --- Check fractal exists ---
        fractal = db.query(Fractal).get(fractal_id)
        if not fractal:
            raise HTTPException(status_code=404, detail="Fractal not found")

        # --- Determine current round/level ---
        current_round = db.query(Round).filter(Round.fractal_id == fractal_id).order_by(Round.level.desc()).first()
        if current_round:
            current_level = current_round.level
        else:
            current_level = 0

        # --- Find the user's group in current round ---
        group_member = db.query(GroupMember).join(Group).filter(
            Group.round_id == (current_round.id if current_round else None),
            GroupMember.user_id == user_id
        ).first()

        if not group_member:
            return {"group": None, "message": "User is not assigned to a group in current round"}

        group = db.query(Group).get(group_member.group_id)

        # --- Users in group ---
        group_members = db.query(User).join(GroupMember).filter(GroupMember.group_id == group.id).all()
        users_info = [{"id": u.id, "username": u.username, "is_ai": u.is_ai} for u in group_members]

        # --- Proposals in group ---
        proposals = db.query(Proposal).filter(Proposal.group_id == group.id).all()
        proposal_info = []
        for p in proposals:
            votes = db.query(ProposalVote).filter(ProposalVote.proposal_id == p.id).all()
            total_score = sum(v.score for v in votes) if votes else None

            # --- Comments (threaded) ---
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

            comments = db.query(Comment).filter(Comment.proposal_id == p.id, Comment.parent_comment_id == None).all()
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
            "fractal_id": fractal.id,
            "group_id": group.id,
            "level": group.level,
            "members": users_info,
            "proposals": proposal_info
        }
    finally:
        db.close()


@router.get("/{fractal_id}/status", summary="Get current fractal status with group details")
def fractal_status(fractal_id: int, db: Session = Depends(get_db)):
    try:
        fractal = db.query(Fractal).get(fractal_id)
        if not fractal:
            raise HTTPException(status_code=404, detail="Fractal not found")

        # --- Fractal members ---
        members = db.query(FractalMember).filter(FractalMember.fractal_id == fractal_id).all()
        member_ids = [m.user_id for m in members]

        # --- Determine current round/level ---
        current_round = db.query(Round).filter(Round.fractal_id == fractal_id).order_by(Round.level.desc()).first()
        if current_round:
            current_level = current_round.level
        else:
            current_level = 0

        # --- Groups in current level ---
        groups = db.query(Group).filter(Group.round_id == current_round.id if current_round else None).all()

        group_info = []
        for g in groups:
            # --- Users in group ---
            group_members = db.query(User).join(GroupMember).filter(GroupMember.group_id == g.id).all()
            users_info = [{"id": u.id, "username": u.username, "is_ai": u.is_ai} for u in group_members]

            # --- Proposals ---
            proposals = db.query(Proposal).filter(Proposal.group_id == g.id).all()
            proposal_info = []
            for p in proposals:
                votes = db.query(ProposalVote).filter(ProposalVote.proposal_id == p.id).all()
                total_score = sum(v.score for v in votes) if votes else None

                # --- Comments (threaded) ---
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

                comments = db.query(Comment).filter(Comment.proposal_id == p.id, Comment.parent_comment_id == None).all()
                serialized_comments = [serialize_comment(c) for c in comments]

                proposal_info.append({
                    "id": p.id,
                    "title": p.title,
                    "body": p.body,
                    "creator_user_id": p.creator_user_id,
                    "total_score": total_score,
                    "comments": serialized_comments
                })

            group_info.append({
                "group_id": g.id,
                "level": g.level,
                "members": users_info,
                "proposals": proposal_info
            })

        return {
            "fractal_id": fractal.id,
            "name": fractal.name,
            "status": fractal.status,
            "current_level": current_level,
            "total_members": len(member_ids),
            "groups_count": len(group_info),
            "groups": group_info
        }
    finally:
        db.close()
        

@router.post("/{fractal_id}/close_round", summary="Close current round and start next")
def close_round(fractal_id: int, db: Session = Depends(get_db)):
    try:
        # --- 1. Find the highest open round ---
        current_round = (
            db.query(Round)
            .filter(Round.fractal_id == fractal_id, Round.status == "open")
            .order_by(Round.level.desc())
            .first()
        )

        if not current_round:
            raise HTTPException(400, "No open round to close")

        current_level = current_round.level

        # --- 2. Close the round ---
        calculate_proposal_scores(db, fractal_id, current_level)
        calculate_comment_votes(db, fractal_id, current_level)
        promote_representatives_to_next_round(db, fractal_id)

        current_round.status = "closed"
        current_round.ended_at = datetime.now(timezone.utc)
        db.add(current_round)
        db.commit()

        # --- 3. Check how many groups were in this round ---
        groups_count = db.query(Group).filter(Group.round_id == current_round.id).count()

        next_round_started = False
        next_level = current_level + 1

        if groups_count > 1:
            # --- 4. Create next round ---
            create_level_groups(
                db,
                fractal_id=fractal_id,
                round_level=next_level,
                algorithm="random",
                options={}
            )
            next_round_started = True

        return {
            "ok": True,
            "fractal_id": fractal_id,
            "level_closed": current_level,
            "next_round_started": next_round_started,
            "next_level": next_level if next_round_started else None
        }

    finally:
        db.close()

@router.get("/{fractal_id}/members/{user_id}")
def get_member_context(fractal_id: int, user_id: int, db: Session = Depends(get_db)):
    """
    Returns the user's state inside a fractal:
    - current round
    - group in that round
    - user prefs (if any)
    - username
    """

    # --- 1. Verify user is a member ---
    fm = db.query(FractalMember).filter(
        FractalMember.fractal_id == fractal_id,
        FractalMember.user_id == user_id,
        FractalMember.left_at == None
    ).first()


    # --- 1. Verify user is a user ---
    u = db.query(User).filter(
        User.id == user_id,
    ).first()


    if not fm:
        raise HTTPException(status_code=404, detail="User is not an active member of this fractal")

    # --- 2. Get active/open round ---
    rnd = db.query(Round).filter(
        Round.fractal_id == fractal_id
    ).order_by(Round.level.desc()).first()

    if not rnd:
        raise HTTPException(status_code=404, detail="No round exists for this fractal")

    # If latest round is closed → no open round
    if rnd.status != "open":
        return {
            "ok": True,
            "username": u.username,
            "round_id": None,
            "round_level": None,
            "group_id": None,
            "prefs": u.prefs or {}
        }

    # --- 3. Find group for this user in this round ---
    gm = db.query(GroupMember).join(Group).filter(
        Group.round_id == rnd.id,
        GroupMember.user_id == user_id
    ).first()

    group_id = gm.group_id if gm else None

    # --- 4. Return result ---
    return {
        "ok": True,
        "username": u.username,
        "round_id": rnd.id,
        "round_level": rnd.level,
        "group_id": group_id,
        "prefs": u.prefs or {}
    }
