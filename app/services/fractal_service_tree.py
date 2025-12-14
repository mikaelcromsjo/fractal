# services/fractal_tree_service.py

from typing import Any, Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import infrastructure.models as models


async def _get_comment_subtree(
    db: AsyncSession,
    proposal_id: int,
    group_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Nested comments for a proposal, with user info and per-voter votes.
    """
    Comment = models.Comment
    User = models.User
    CommentVote = models.CommentVote

    # Load all comments for this proposal (optionally limited by group)
    stmt = select(Comment, User).join(User, Comment.user_id == User.id).where(
        Comment.proposal_id == proposal_id
    )
    if group_id is not None:
        stmt = stmt.where(Comment.group_id == group_id)

    res = await db.execute(stmt)
    rows = res.all()

    # Collect comment ids
    comment_ids = [c.id for (c, _) in rows]
    votes_by_comment: Dict[int, List[Dict[str, Any]]] = {cid: [] for cid in comment_ids}

    if comment_ids:
        # Load all votes on these comments with voter info
        v_stmt = (
            select(CommentVote, User)
            .join(User, CommentVote.voter_user_id == User.id)
            .where(CommentVote.comment_id.in_(comment_ids))
        )
        v_res = await db.execute(v_stmt)
        for vote, voter in v_res.all():
            votes_by_comment.setdefault(vote.comment_id, []).append(
                {
                    "voter_user_id": vote.voter_user_id,
                    "voter_username": voter.username,
                    "vote": bool(vote.vote),
                    "created_at": vote.created_at.isoformat()
                    if getattr(vote, "created_at", None)
                    else None,
                }
            )

    # Build nodes
    by_id: Dict[int, Dict[str, Any]] = {}
    roots: List[Dict[str, Any]] = []

    for c, user in rows:
        node = {
            "comment_id": c.id,
            "proposal_id": c.proposal_id,
            "parent_comment_id": c.parent_comment_id,
            "user_id": c.user_id,
            "username": user.username,
            "text": c.text,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "votes": votes_by_comment.get(c.id, []),
            "replies": [],
        }
        by_id[c.id] = node

    # Nest by parent_comment_id
    for c, _ in rows:
        node = by_id[c.id]
        if c.parent_comment_id is None:
            roots.append(node)
        else:
            parent = by_id.get(c.parent_comment_id)
            if parent:
                parent["replies"].append(node)

    return roots


async def _get_proposal_subtree_for_group(
    db: AsyncSession,
    group_id: int,
    round_id: int,
) -> List[Dict[str, Any]]:
    """
    All proposals for a group in a given round, with user info,
    per-voter proposal scores, and nested comments.
    """
    Proposal = models.Proposal
    User = models.User
    ProposalVote = models.ProposalVote

    # Proposals with creator user
    stmt = (
        select(Proposal, User)
        .join(User, Proposal.creator_user_id == User.id)
        .where(
            Proposal.group_id == group_id,
            Proposal.round_id == round_id,
        )
        .order_by(Proposal.created_at.asc())
    )

    res = await db.execute(stmt)
    rows = res.all()
    proposals = [p for (p, _) in rows]
    proposal_ids = [p.id for p in proposals]

    # Per-voter scores
    votes_by_proposal: Dict[int, List[Dict[str, Any]]] = {
        pid: [] for pid in proposal_ids
    }

    if proposal_ids:
        v_stmt = (
            select(ProposalVote, User)
            .join(User, ProposalVote.voter_user_id == User.id)
            .where(ProposalVote.proposal_id.in_(proposal_ids))
        )
        v_res = await db.execute(v_stmt)
        for vote, voter in v_res.all():
            votes_by_proposal.setdefault(vote.proposal_id, []).append(
                {
                    "voter_user_id": vote.voter_user_id,
                    "voter_username": voter.username,
                    "score": vote.score,
                    "created_at": vote.created_at.isoformat()
                    if getattr(vote, "created_at", None)
                    else None,
                }
            )

    result: List[Dict[str, Any]] = []
    for p, creator in rows:
        comments_tree = await _get_comment_subtree(
            db,
            proposal_id=p.id,
            group_id=group_id,
        )
        result.append(
            {
                "proposal_id": p.id,
                "fractal_id": p.fractal_id,
                "group_id": p.group_id,
                "round_id": p.round_id,
                "creator_user_id": p.creator_user_id,
                "creator_username": creator.username,
                "title": p.title,
                "body": p.body,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "votes": votes_by_proposal.get(p.id, []),
                "comments": comments_tree,
            }
        )
    return result


async def _get_group_subtree_for_round(
    db: AsyncSession,
    fractal_id: int,
    round_id: int,
) -> List[Dict[str, Any]]:
    Group = models.Group
    GroupMember = models.GroupMember
    User = models.User

    # Groups in this round
    g_res = await db.execute(
        select(Group).where(
            Group.fractal_id == fractal_id,
            Group.round_id == round_id,
        )
    )
    groups = g_res.scalars().all()

    result: List[Dict[str, Any]] = []
    for g in groups:
        # Members with usernames
        gm_res = await db.execute(
            select(GroupMember, User)
            .join(User, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == g.id)
        )
        gm_rows = gm_res.all()
        members = [
            {
                "user_id": gm.user_id,
                "username": user.username,
            }
            for gm, user in gm_rows
        ]

        proposals = await _get_proposal_subtree_for_group(
            db,
            group_id=g.id,
            round_id=round_id,
        )

        result.append(
            {
                "group_id": g.id,
                "round_id": round_id,
                "fractal_id": fractal_id,
                "members": members,
                "proposals": proposals,
            }
        )

    return result


async def build_fractal_tree(
    db: AsyncSession,
    fractal_id: int,
    round_id: Optional[int] = None,
) -> Dict[str, Any]:
    Round = models.Round

    r_res = await db.execute(
        select(Round)
        .where(Round.fractal_id == fractal_id)
        .order_by(Round.level.asc())
    )
    all_rounds = r_res.scalars().all()

    if not all_rounds:
        return {"fractal_id": fractal_id, "rounds": []}

    # Pick a single round to build
    if round_id:
        round_obj = next(
            (r for r in all_rounds if r.id == round_id),
            all_rounds[0],
        )
    else:
        round_obj = all_rounds[0]

    groups_json = await _get_group_subtree_for_round(
        db,
        fractal_id=fractal_id,
        round_id=round_obj.id,
    )

    return {
        "fractal_id": fractal_id,
        "rounds": [
            {
                "round_id": round_obj.id,
                "level": round_obj.level,
                "status": round_obj.status,
                "groups": groups_json,
            }
        ],
    }