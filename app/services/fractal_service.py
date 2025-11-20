# app/services/fractal_service.py
"""
Service layer that uses the domain fractal logic and the DB models.
Contains functions that perform common workflows: create groups, add proposals,
select representatives and promote to next round.

These functions use SQLAlchemy sessions and models in app.infrastructure.models.
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.infrastructure.models import Group, GroupMember, Round, Proposal, Fractal, FractalMember, ProposalMerge, RepresentativeSelection, ProposalVote
from app.infrastructure.db.session import SessionLocal
from app.domain import fractal_service as domain
from app.config.settings import settings
from datetime import datetime


def _get_session() -> Session:
    return SessionLocal()


def create_level_groups(fractal_id: int, round_level: int, algorithm: str = "random", options: Dict = None) -> List[int]:
    """
    Create groups for the given fractal and round using the specified algorithm.
    Returns list of created group ids.
    """
    options = options or {}
    db = _get_session()
    try:
        # collect members for fractal
        members = db.query(FractalMember).filter(FractalMember.fractal_id == fractal_id, FractalMember.left_at == None).all()
        member_objs = []
        for m in members:
            user = db.query(FractalMember).get(m.id)  # not necessary; keep minimal
        # simple: use user ids from FractalMember rows
        user_ids = [m.user_id for m in members]
        # domain grouping (members need dicts)
        member_dicts = [{"user_id": uid, "prefs": {}} for uid in user_ids]
        options.setdefault("group_size", settings.GROUP_SIZE_DEFAULT)
        groups_flat = domain.random_grouping(member_dicts, options)  # currently random
        created_group_ids = []
        # create DB round if not exists
        rnd = Round(fractal_id=fractal_id, level=round_level, started_at=datetime.utcnow(), status="open")
        db.add(rnd)
        db.commit()
        db.refresh(rnd)
        for g in groups_flat:
            grp = Group(round_id=rnd.id, level=round_level, meta={})
            db.add(grp)
            db.commit()
            db.refresh(grp)
            # add group members
            for uid in g:
                gm = GroupMember(group_id=grp.id, user_id=uid)
                db.add(gm)
            db.commit()
            created_group_ids.append(grp.id)
        return created_group_ids
    finally:
        db.close()


def add_proposal(fractal_id: int, group_id: int, round_id: int, title: str, body: str, creator_user_id: int, ptype: str = "base") -> int:
    """
    Create a proposal record.
    """
    db = _get_session()
    try:
        p = Proposal(fractal_id=fractal_id, group_id=group_id, round_id=round_id, title=title, body=body, creator_user_id=creator_user_id, type=ptype, created_at=datetime.utcnow())
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def add_comment(proposal_id: int, user_id: int, text: str, parent_comment_id: int = None) -> int:
    """
    Create comment under a proposal or comment (thread).
    """
    from app.infrastructure.models import Comment
    db = _get_session()
    try:
        c = Comment(proposal_id=proposal_id, parent_comment_id=parent_comment_id, user_id=user_id, text=text, created_at=datetime.utcnow())
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id
    finally:
        db.close()


def cast_proposal_vote(proposal_id: int, voter_user_id: int, score: int):
    """
    Cast or update a proposal vote. Score should be between 1 and 10.
    """
    from app.infrastructure.models import ProposalVote
    db = _get_session()
    try:
        # upsert behavior: attempt to find existing
        pv = db.query(ProposalVote).filter(ProposalVote.proposal_id == proposal_id, ProposalVote.voter_user_id == voter_user_id).first()
        if pv:
            pv.score = int(score)
            pv.created_at = datetime.utcnow()
            db.add(pv)
        else:
            pv = ProposalVote(proposal_id=proposal_id, voter_user_id=voter_user_id, score=int(score), created_at=datetime.utcnow())
            db.add(pv)
        db.commit()
        return True
    finally:
        db.close()


def cast_comment_vote(comment_id: int, voter_user_id: int, vote: bool):
    """
    Cast or update comment vote (yes/no).
    """
    from app.infrastructure.models import CommentVote
    db = _get_session()
    try:
        cv = db.query(CommentVote).filter(CommentVote.comment_id == comment_id, CommentVote.voter_user_id == voter_user_id).first()
        if cv:
            cv.vote = bool(vote)
            cv.created_at = datetime.utcnow()
            db.add(cv)
        else:
            cv = CommentVote(comment_id=comment_id, voter_user_id=voter_user_id, vote=bool(vote), created_at=datetime.utcnow())
            db.add(cv)
        db.commit()
        return True
    finally:
        db.close()


def select_representative_for_group(group_id: int) -> int:
    """
    Compute representative for a group by collecting proposal messages/votes in that group.
    Returns selected user id or None.
    """
    db = _get_session()
    try:
        # collect messages (proposals) under group's round and group
        group = db.query(Group).get(group_id)
        if not group:
            return None
        proposals = db.query(Proposal).filter(Proposal.group_id == group_id).all()
        messages = []
        for p in proposals:
            votes = db.query(ProposalVote).filter(ProposalVote.proposal_id == p.id).all()
            votes_map = {v.voter_user_id: v.score for v in votes}
            messages.append({"user_id": p.creator_user_id, "votes": votes_map})
        # collect member ids
        gm_rows = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
        members = [g.user_id for g in gm_rows]
        rep = domain.select_representative_from_messages(messages, members)
        # persist rep
        sel = RepresentativeSelection(group_id=group_id, representative_user_id=rep, created_at=datetime.utcnow(), method="vote")
        db.add(sel)
        db.commit()
        return rep
    finally:
        db.close()


def promote_representatives_to_next_round(db: Session, fractal_id: int, current_level: int = 0) -> List[int]:
    
    """
    Collect representatives from groups of current level and create groups for the next level.
    Returns created group ids.
    """
    try:
        # find groups in current level for the fractal
        rounds = db.query(Round).filter(Round.fractal_id == fractal_id, Round.level == current_level).all()
        rep_user_ids = []
        for r in rounds:
            groups = db.query(Group).filter(Group.round_id == r.id).all()
            for g in groups:
                sel = db.query(RepresentativeSelection).filter(RepresentativeSelection.group_id == g.id).order_by(RepresentativeSelection.created_at.desc()).first()
                if sel and sel.representative_user_id:
                    rep_user_ids.append(sel.representative_user_id)
        # create next-level groups
        next_level = current_level + 1
        # delegate to create_level_groups but pass member ids as FractalMembers (we bypassed)
        member_dicts = [{"user_id": uid, "prefs": {}} for uid in rep_user_ids]
        options = {"group_size": settings.GROUP_SIZE_DEFAULT}
        groups = domain.random_grouping(member_dicts, options)
        created_ids = []
        # create Round entry
        rnd = Round(fractal_id=fractal_id, level=next_level, started_at=datetime.utcnow(), status="open")
        db.add(rnd)
        db.commit()
        db.refresh(rnd)
        for g in groups:
            grp = Group(round_id=rnd.id, level=next_level, meta={})
            db.add(grp)
            db.commit()
            db.refresh(grp)
            for uid in g:
                gm = GroupMember(group_id=grp.id, user_id=uid)
                db.add(gm)
            db.commit()
            created_ids.append(grp.id)
        return created_ids
    finally:
        db.close()

def calculate_proposal_scores(db: Session, fractal_id: int, round_level: int):
    """Calculate and save total score per proposal for a given fractal and round."""
    proposals = db.query(Proposal).filter(Proposal.fractal_id == fractal_id, Proposal.round_id == round_level).all()
    for p in proposals:
        votes = db.query(ProposalVote).filter(ProposalVote.proposal_id == p.id).all()
        total_score = sum(v.score for v in votes)
        if not hasattr(p, "score_per_level") or p.score_per_level is None:
            p.score_per_level = {}
        p.score_per_level[round_level] = total_score
        db.add(p)
    db.commit()


def calculate_comment_votes(db: Session, fractal_id: int, round_level: int):
    """Calculate and save yes/no votes per comment for a given fractal and round."""
    comments = (
        db.query(Comment)
        .join(Proposal)
        .filter(Proposal.fractal_id == fractal_id, Proposal.round_id == round_level)
        .all()
    )
    for c in comments:
        votes = db.query(CommentVote).filter(CommentVote.comment_id == c.id).all()
        yes_count = sum(1 for v in votes if v.vote)
        no_count = sum(1 for v in votes if not v.vote)
        if not hasattr(c, "votes_per_level") or c.votes_per_level is None:
            c.votes_per_level = {}
        c.votes_per_level[round_level] = {"yes": yes_count, "no": no_count}
        db.add(c)
    db.commit()