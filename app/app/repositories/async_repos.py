#~~~{"id":"70514","variant":"standard","title":"Async Repository Layer"} 
# app/repositories/async_repos.py
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, func
from app.infrastructure.models import (
    User, Fractal, FractalMember, Group, GroupMember, Proposal, Comment,
    ProposalVote, CommentVote, Round, RepresentativeSelection, RepresentativeVote
)
from datetime import datetime, timezone
from typing import List, Dict
from sqlalchemy import func, case, select, cast, Integer

# ----------------------------
# User
# ----------------------------
async def get_user_by_telegram_id(db: AsyncSession, telegram_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalars().first()

async def create_user(db: AsyncSession, user_info: Dict) -> User:
    user = User(
        username=user_info.get("username"),    
        telegram_id=user_info.get("telegram_id")
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def vote_representative(db: AsyncSession, group_id: int, voter_user_id: int, candidate_user_id: int):
    """
    Cast a vote for a representative in a group.
    If the voter already voted in this group, replace the old vote.
    """
    # Remove any existing vote from this voter in the group
    await db.execute(
        delete(RepresentativeVote)
        .where(
            (RepresentativeVote.group_id == group_id) &
            (RepresentativeVote.voter_user_id == voter_user_id)
        )
    )

    # Add the new vote
    vote = RepresentativeVote(
        group_id=group_id,
        voter_user_id=voter_user_id,
        candidate_user_id=candidate_user_id,
    )
    db.add(vote)
    await db.commit()
    await db.refresh(vote)
    return vote


async def select_representative(db: AsyncSession, group_id: int):
    res = await db.execute(
        select(
            RepresentativeVote.candidate_user_id,
            func.count(RepresentativeVote.id).label("votes")
        ).where(RepresentativeVote.group_id == group_id)
        .group_by(RepresentativeVote.candidate_user_id)
        .order_by(func.count(RepresentativeVote.id).desc())
    )
    row = res.first()
    return row.candidate_user_id if row else None

async def add_fractal_member(db: AsyncSession, fractal_id: int, user_id: int, role: str = "member") -> FractalMember:
    member = FractalMember(fractal_id=fractal_id, user_id=user_id, role=role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member

async def get_active_fractal_members(db: AsyncSession, fractal_id: int) -> List[FractalMember]:
    result = await db.execute(
        select(FractalMember).where(
            FractalMember.fractal_id == fractal_id,
            FractalMember.left_at.is_(None)
        )
    )
    return result.scalars().all()




## ROUND/FRACTAL

async def create_fractal(
    db: AsyncSession,
    name: str,
    description: str,
    start_date: datetime,
    status: Optional[str] = "waiting",
    settings: Optional[dict] = None
) -> Fractal:
    """
    Create a new Fractal in the database.
    """
    fractal = Fractal(
        name=name,
        description=description,
        start_date=start_date,
        status=status,
        meta=settings or {}
    )
    db.add(fractal)
    await db.commit()
    await db.refresh(fractal)
    return fractal

# ROUND

async def create_round(
    db: AsyncSession,
    fractal_id: int,
    level: int = 0,
    status: str = "open",
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None
) -> Round:
    """
    Create a new Round for a given Fractal.

    Args:
        db (AsyncSession): The async database session.
        fractal_id (int): ID of the parent fractal.
        level (int, optional): Level of the round. Defaults to 0.
        status (str, optional): Status of the round. Defaults to "open".
        started_at (datetime, optional): Optional start datetime.
        ended_at (datetime, optional): Optional end datetime.

    Returns:
        Round: The newly created Round object.
    """
    round_obj = Round(
        fractal_id=fractal_id,
        level=level,
        status=status,
        started_at=started_at,
        ended_at=ended_at
    )
    db.add(round_obj)
    await db.commit()
    await db.refresh(round_obj)
    return round_obj

async def close_round_repo(db: AsyncSession, round_id: int):
    """Mark a round as closed and set the end timestamp, then return the round."""
    stmt = (
        update(Round)
        .where(Round.id == round_id)
        .values(
            ended_at=datetime.now(timezone.utc),
            status="closed"
        )
        .returning(Round)  # RETURNING clause returns the updated row
    )
    result = await db.execute(stmt)
    await db.commit()
    closed_round = result.scalar_one()  # get the single updated Round object
    return closed_round


# ----------------------------
# Group
# ----------------------------
async def create_group(db: AsyncSession, fractal_id: int, round_id: int, level: int = 0, meta: dict = {}) -> Group:
    grp = Group(round_id=round_id, fractal_id=fractal_id, level=level, meta=meta)
    db.add(grp)
    await db.commit()
    await db.refresh(grp)
    return grp

async def add_group_member(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    gm = GroupMember(group_id=group_id, user_id=user_id)
    db.add(gm)
    await db.commit()
    await db.refresh(gm)
    return gm

async def get_groups_for_round_repo(db: AsyncSession, round_id: int):
    result = await db.execute(select(Group).where(Group.round_id == round_id))
    return result.scalars().all()

# ----------------------------
# Proposal
# ----------------------------
async def add_proposal(db: AsyncSession, fractal_id: int, group_id: int, round_id: int,
                       title: str, body: str, creator_user_id: int, ptype: str = "base") -> Proposal:
    proposal = Proposal(
        fractal_id=fractal_id, group_id=group_id, round_id=round_id,
        title=title, body=body, creator_user_id=creator_user_id, type=ptype,
        created_at=datetime.now(timezone.utc)
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal

async def get_proposals_for_group(db: AsyncSession, group_id: int) -> List[Proposal]:
    result = await db.execute(select(Proposal).where(Proposal.group_id == group_id))
    return result.scalars().all()

async def get_top_proposals(db: AsyncSession, group_id: int, top_count: int) -> List[Proposal]:
    """
    Get top proposals for a group, sorted by score at the group's level.
    
    Args:
        db: AsyncSession
        group_id: ID of the group
        top_count: how many top proposals to return
        
    Returns:
        List of Proposal objects
    """
    # Get the group to find its level
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one()
    group_level = group.level

    # Fetch proposals in this group
    result = await db.execute(select(Proposal).where(Proposal.group_id == group_id))
    proposals = result.scalars().all()

    # Sort proposals by score at group's level
    def proposal_score(p: Proposal):
        scores = p.score_per_level or []
        if not scores or group_level >= len(scores):
            return 0.0
        return scores[group_level]

    top_proposals = sorted(proposals, key=proposal_score, reverse=True)[:top_count]
    return top_proposals


# ----------------------------
# Comment
# ----------------------------
async def add_comment(db: AsyncSession, proposal_id: int, user_id: int, text: str, parent_comment_id: Optional[int] = None) -> Comment:
    comment = Comment(proposal_id=proposal_id, user_id=user_id, text=text, parent_comment_id=parent_comment_id,
                      created_at=datetime.now(timezone.utc))
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment

async def get_comments_for_proposal(db: AsyncSession, proposal_id: int) -> List[Comment]:
    """
    Fetch all comments for a proposal.
    Does NOT calculate vote totals.
    """
    result = await db.execute(
        select(Comment).where(Comment.proposal_id == proposal_id).order_by(Comment.created_at)
    )
    return result.scalars().all()

async def get_comments_tree(
    db: AsyncSession,
    proposal_id: int,
    voter_user_id: Optional[int] = None,
    group_user_ids: Optional[List[int]] = None
) -> List[Dict]:
    """
    Fetch visible comment tree for a proposal:
      - Only comments with more upvotes than downvotes OR in current group
      - Stop recursion at hidden comments
      - Include vote totals and current user vote
    """
    # Fetch all comments
    result = await db.execute(
        select(Comment).where(Comment.proposal_id == proposal_id).order_by(Comment.created_at)
    )
    comments = result.scalars().all()

    comment_ids = [c.id for c in comments]

    # voter_user_id: the current user for "my_vote"
    vote_stmt = select(
        CommentVote.comment_id,
        func.sum(case(
            (CommentVote.vote == True, 1),
            (CommentVote.vote == False, -1),
            else_=0
        )).label("vote_total"),
        func.max(
            case(
                (CommentVote.voter_user_id == voter_user_id, cast(CommentVote.vote, Integer)),
                else_=None
            )
        ).label("my_vote")
    ).where(CommentVote.comment_id.in_(comment_ids)).group_by(CommentVote.comment_id)

    vote_result = await db.execute(vote_stmt)
    vote_map = {vid: {"vote_total": vt, "my_vote": mv} for vid, vt, mv in vote_result.all()}

    # Build map id -> comment node
    comment_map = {}
    for c in comments:
        vote_info = vote_map.get(c.id, {"vote_total": 0, "my_vote": None})
        in_group = (group_user_ids and c.creator_user_id in group_user_ids)
        visible = vote_info["vote_total"] >= 0 or in_group
        comment_map[c.id] = {
            "comment": c,
            "replies": [],
            "vote_total": vote_info["vote_total"],
            "my_vote": vote_info["my_vote"],
            "hidden_children": False,
            "visible": visible
        }

    # Build tree, skip invisible comments but mark hidden_children
    tree = []
    for c in comments:
        node = comment_map[c.id]
        if c.parent_comment_id:
            parent = comment_map.get(c.parent_comment_id)
            if parent:
                if node["visible"]:
                    parent["replies"].append(node)
                else:
                    parent["hidden_children"] = True
        else:
            if node["visible"]:
                tree.append(node)
            elif node["hidden_children"]:
                # Show a placeholder for "load more"
                tree.append({"comment": None, "replies": [], "vote_total": 0,
                             "my_vote": None, "hidden_children": True})
    return tree


# ----------------------------
# Proposal Vote
# ----------------------------
async def cast_proposal_vote(db: AsyncSession, proposal_id: int, voter_user_id: int, score: int):
    result = await db.execute(
        select(ProposalVote).where(ProposalVote.proposal_id == proposal_id, ProposalVote.voter_user_id == voter_user_id)
    )
    pv = result.scalars().first()
    if pv:
        pv.score = score
        pv.created_at = datetime.now(timezone.utc)
        db.add(pv)
    else:
        pv = ProposalVote(proposal_id=proposal_id, voter_user_id=voter_user_id, score=score, created_at=datetime.now(timezone.utc))
        db.add(pv)
    await db.commit()
    return pv

# ----------------------------
# Comment Vote
# ----------------------------
async def cast_comment_vote(db: AsyncSession, comment_id: int, voter_user_id: int, vote: bool):
    result = await db.execute(
        select(CommentVote).where(CommentVote.comment_id == comment_id, CommentVote.voter_user_id == voter_user_id)
    )
    cv = result.scalars().first()
    if cv:
        cv.vote = vote
        cv.created_at = datetime.now(timezone.utc)
        db.add(cv)
    else:
        cv = CommentVote(comment_id=comment_id, voter_user_id=voter_user_id, vote=vote, created_at=datetime.now(timezone.utc))
        db.add(cv)
    await db.commit()
    return cv

# ----------------------------
# Pending Proposals/Comments for a user
# ----------------------------
async def get_pending_proposals(db: AsyncSession, user_id: int) -> List[Proposal]:
    # proposals where user has not voted yet
    subq = select(ProposalVote.proposal_id).where(ProposalVote.voter_user_id == user_id)
    result = await db.execute(select(Proposal).where(~Proposal.id.in_(subq)))
    return result.scalars().all()

async def get_pending_comments(db: AsyncSession, user_id: int) -> List[Comment]:
    subq = select(CommentVote.comment_id).where(CommentVote.voter_user_id == user_id)
    result = await db.execute(select(Comment).where(~Comment.id.in_(subq)))
    return result.scalars().all()


async def get_group_members(db: AsyncSession, group_id: int) -> List[GroupMember]:
    """
    Returns a list of GroupMember objects for the given group_id.
    """
    result = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id)
    )
    return result.scalars().all()


# -----------------------------
# Proposal scores with list
# -----------------------------
async def save_proposal_score(db: AsyncSession, proposal_id: int, level: int, score: float):
    result = await db.execute(select(Proposal.score_per_level).where(Proposal.id == proposal_id))
    score_list = result.scalar() or []
    
    # Extend the list if needed
    while len(score_list) <= level:
        score_list.append(None)
    score_list[level] = score
    
    await db.execute(
        update(Proposal)
        .where(Proposal.id == proposal_id)
        .values(score_per_level=score_list)
    )
    await db.commit()

async def get_proposal_score(db: AsyncSession, proposal_id: int, level: int) -> float | None:
    result = await db.execute(select(Proposal.score_per_level).where(Proposal.id == proposal_id))
    score_list = result.scalar() or []
    return score_list[level] if level < len(score_list) else None

# -----------------------------
# Comment scores with list
# -----------------------------
async def save_comment_score(db: AsyncSession, comment_id: int, level: int, score: float):
    result = await db.execute(select(Comment.score_per_level).where(Comment.id == comment_id))
    score_list = result.scalar() or []
    
    while len(score_list) <= level:
        score_list.append(None)
    score_list[level] = score
    
    await db.execute(
        update(Comment)
        .where(Comment.id == comment_id)
        .values(score_per_level=score_list)
    )
    await db.commit()

async def get_comment_score(db: AsyncSession, comment_id: int, level: int) -> float | None:
    result = await db.execute(select(Comment.score_per_level).where(Comment.id == comment_id))
    score_list = result.scalar() or []
    return score_list[level] if level < len(score_list) else None

#----------------------------
# Proposal votes
# ----------------------------
async def get_votes_for_proposal(db: AsyncSession, proposal_id: int) -> List[ProposalVote]:
    """Return all ProposalVote objects for a given proposal."""
    result = await db.execute(
        select(ProposalVote).where(ProposalVote.proposal_id == proposal_id)
    )
    return result.scalars().all()


# ----------------------------
# Comment votes
# ----------------------------
async def get_votes_for_comment(db: AsyncSession, comment_id: int) -> List[CommentVote]:
    """Return all CommentVote objects for a given comment."""
    result = await db.execute(
        select(CommentVote).where(CommentVote.comment_id == comment_id)
    )
    return result.scalars().all()

async def get_round_by_id(db: AsyncSession, round_id: int) -> Round | None:
    """
    Fetch a Round object by its ID.
    Returns None if not found.
    """
    result = await db.execute(
        select(Round).where(Round.id == round_id)
    )
    return result.scalar_one_or_none()