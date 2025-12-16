#~~~{"id":"70514","variant":"standard","title":"Async Repository Layer"} 
# app/repositories/fractal_repos.py
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, func
from infrastructure.models import (
    User, Fractal, FractalMember, Group, GroupMember, Proposal, Comment,
    ProposalVote, CommentVote, Round, RepresentativeSelection, RepresentativeVote, QueueItem, 
)
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.sql import exists

import infrastructure.models as models

from services.fractal_service_tree import build_fractal_tree

from datetime import datetime, timezone
from typing import List, Dict
from typing import Optional, Union
from sqlalchemy import func, case, select, cast, Integer
from sqlalchemy import select, desc

# ----------------------------
# User
# ----------------------------

async def create_user_repo(db: AsyncSession, user_info: Dict) -> User:
    user = User(
        username=user_info.get("username"),    
        telegram_id=user_info.get("telegram_id")
    )
    print("Creating User from Telegram", user_info.get("telegram_id"))

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def vote_representative_repo(db: AsyncSession, group_id: int, voter_user_id: int, candidate_user_id: int):
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


async def select_representative_repo(db: AsyncSession, group_id: int):
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

async def add_fractal_member_repo(db: AsyncSession, fractal_id: int, user_id: int, role: str = "member") -> FractalMember:
    member = FractalMember(fractal_id=fractal_id, user_id=user_id, role=role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member

async def get_active_fractal_members_repo(db: AsyncSession, fractal_id: int) -> List[FractalMember]:
    result = await db.execute(
        select(FractalMember).where(
            FractalMember.fractal_id == fractal_id,
            FractalMember.left_at.is_(None)
        )
    )
    return result.scalars().all()




## ROUND/FRACTAL



async def create_fractal_repo(
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

async def create_round_repo(
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
    RoundTree = models.RoundTree
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

    tree = await build_fractal_tree(db, fractal_id=closed_round.fractal_id, round_id=closed_round.id)

    # Upsert into RoundTree
    existing = await db.get(RoundTree, closed_round.id)
    if existing:
        existing.tree = tree
    else:
        db.add(RoundTree(round_id=closed_round.id, fractal_id=closed_round.fractal_id, tree=tree))
    await db.flush()

    return closed_round


# ----------------------------
# Group
# ----------------------------
async def create_group_repo(db: AsyncSession, fractal_id: int, round_id: int, level: int = 0, meta: dict = {}) -> Group:
    grp = Group(round_id=round_id, fractal_id=fractal_id, level=level, meta=meta)
    db.add(grp)
    await db.commit()
    await db.refresh(grp)
    return grp

async def add_group_member_repo(db: AsyncSession, group_id: int, user_id: int) -> GroupMember:
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
async def add_proposal_repo(db: AsyncSession, fractal_id: int, group_id: int, round_id: int,
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

async def get_proposals_for_group_repo(db: AsyncSession, group_id: int) -> List[Proposal]:
    result = await db.execute(select(Proposal).where(Proposal.group_id == group_id))
    return result.scalars().all()

async def get_top_proposals_repo(db: AsyncSession, group_id: int, top_count: int) -> List[Proposal]:
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
    def proposal_score_repo(p: Proposal):
        scores = p.score_per_level or []
        if not scores or group_level >= len(scores):
            return 0.0
        return scores[group_level]

    top_proposals = sorted(proposals, key=proposal_score_repo, reverse=True)[:top_count]
    return top_proposals


# ----------------------------
# Comment
# ----------------------------

async def add_comment_repo(db: AsyncSession, proposal_id: int, user_id: int, text: str, parent_comment_id: Optional[int] = None, group_id: Optional[int] = None) -> Comment:
    comment = Comment(proposal_id=proposal_id, user_id=user_id, text=text, parent_comment_id=parent_comment_id, group_id=group_id,
                      created_at=datetime.now(timezone.utc))
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment

async def get_comments_for_proposal_repo(db: AsyncSession, proposal_id: int) -> List[Comment]:
    """
    Fetch all comments for a proposal.
    Does NOT calculate vote totals.
    """
    result = await db.execute(
        select(Comment).where(Comment.proposal_id == proposal_id).order_by(Comment.created_at)
    )
    return result.scalars().all()

async def get_comments_tree_repo(
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
        func.sum().label("vote_total"),
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
async def vote_proposal_repo(db: AsyncSession, proposal_id: int, voter_user_id: int, score: int):
    # do I need level?
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

    # temporary debug in vote endpoint, after insert
    print("VOTE INSERTED", {
        "proposal_id": pv.proposal_id,
        "voter_user_id": pv.voter_user_id,
    })

    return pv

# ----------------------------
# Comment Vote
# ----------------------------
async def vote_comment_repo(db: AsyncSession, comment_id: int, voter_user_id: int, vote: int):
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
async def get_pending_proposals_repo(db: AsyncSession, user_id: int) -> List[Proposal]:
    # proposals where user has not voted yet
    subq = select(ProposalVote.proposal_id).where(ProposalVote.voter_user_id == user_id)
    result = await db.execute(select(Proposal).where(~Proposal.id.in_(subq)))
    return result.scalars().all()

async def get_pending_comments_repo(db: AsyncSession, user_id: int) -> List[Comment]:
    subq = select(CommentVote.comment_id).where(CommentVote.voter_user_id == user_id)
    result = await db.execute(select(Comment).where(~Comment.id.in_(subq)))
    return result.scalars().all()


async def get_group_members_repo(db: AsyncSession, group_id: int) -> List[GroupMember]:
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
async def save_proposal_score_repo(db: AsyncSession, proposal_id: int, level: int, score: float):
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

async def get_proposal_score_repo(db: AsyncSession, proposal_id: int, level: int) -> float | None:
    result = await db.execute(select(Proposal.score_per_level).where(Proposal.id == proposal_id))
    score_list = result.scalar() or []
    return score_list[level] if level < len(score_list) else None

# -----------------------------
# Comment scores with list
# -----------------------------
async def save_comment_score_repo(db: AsyncSession, comment_id: int, level: int, score: float):
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

async def get_comment_score_repo(db: AsyncSession, comment_id: int, level: int) -> float | None:
    result = await db.execute(select(Comment.score_per_level).where(Comment.id == comment_id))
    score_list = result.scalar() or []
    return score_list[level] if level < len(score_list) else None

#----------------------------
# Proposal votes
# ----------------------------
async def get_votes_for_proposal_repo(db: AsyncSession, proposal_id: int) -> List[ProposalVote]:
    """Return all ProposalVote objects for a given proposal."""
    result = await db.execute(
        select(ProposalVote).where(ProposalVote.proposal_id == proposal_id)
    )
    return result.scalars().all()


# ----------------------------
# Comment votes
# ----------------------------
async def get_votes_for_comment_repo(db: AsyncSession, comment_id: int) -> List[CommentVote]:
    """Return all CommentVote objects for a given comment."""
    result = await db.execute(
        select(CommentVote).where(CommentVote.comment_id == comment_id)
    )
    return result.scalars().all()

# ----------------------------
# Helpers
# ----------------------------

async def get_user_by_telegram_id_repo(db: AsyncSession, telegram_id: str) -> Optional[User]:
    print("id", telegram_id)
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalars().first()

async def get_user_repo(db: AsyncSession, id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == id))
    return result.scalars().first()


async def set_active_fractal_repo(db: AsyncSession, user_id: int, fractal_id: int) -> Optional[User]:

    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(
            active_fractal_id=fractal_id
        )
        .returning(User)  # RETURNING clause returns the updated row
    )
    result = await db.execute(stmt)
    await db.commit()
    user = result.scalar_one()  # get the single updated Round object
    return user

async def get_fractal_repo(
    db: AsyncSession,
    fractal_id: int
    ) -> Fractal:

    q = select(Fractal).where(Fractal.id == fractal_id)
    result = await db.execute(q)
    return result.scalars().first()

async def get_fractal_from_name_or_id_repo(
    db: AsyncSession,
    fractal_identifier: Union[str, int]
) -> Optional[Fractal]:
    
    # ----------------------------
    # 1) Try numeric ID
    # ----------------------------
    fractal_id = None
    if isinstance(fractal_identifier, int):
        fractal_id = fractal_identifier
    else:
        # ✅ FIX: Convert to str FIRST, then check isdigit()
        identifier_str = str(fractal_identifier)
        if identifier_str.isdigit():
            fractal_id = int(identifier_str)

    if fractal_id is not None:
        q = select(Fractal).where(Fractal.id == fractal_id)
        result = await db.execute(q)
        fractal = result.scalars().first()
        if fractal:
            return fractal

    # ----------------------------
    # 2) Try lookup by name - ALWAYS str
    # ----------------------------
    name_str = str(fractal_identifier)  # ✅ FIX: Always str for name
    q = select(Fractal).where(Fractal.name == name_str)
    result = await db.execute(q)
    return result.scalars().first()


async def get_last_round_repo(db: AsyncSession, fractal_id) -> Round | None:
    """
    Fetch the Round object with the highest level.
    Returns None if no rounds exist.
    """
    result = await db.execute(
        select(Round).where(Round.fractal_id==fractal_id).order_by(Round.level.desc()).limit(1)
    )
    return result.scalar_one_or_none()

async def get_round_repo(db: AsyncSession, round_id: int) -> Round | None:
    """
    Fetch a Round object by its ID.
    Returns None if not found.
    """
    result = await db.execute(
        select(Round).where(Round.id == round_id)
    )
    return result.scalar_one_or_none()

async def get_group_member_repo(db: AsyncSession, user_id: int, group_id: int) -> GroupMember | None:
    result = await db.execute(
        select(GroupMember).where(
            (GroupMember.user_id == user_id) &
            (GroupMember.group_id == group_id)
        )

    )
    return result.scalar_one_or_none()

async def get_group_repo(db: AsyncSession, group_id: int) -> Group | None:
    result = await db.execute(
        select(Group).where(Group.id == group_id)
    )
    return result.scalar_one_or_none()

async def get_user_info_by_telegram_id_repo(
    db: AsyncSession,
    telegram_id: str
) -> Optional[Dict]:

    telegram_id = str(telegram_id)

    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user: User | None = result.scalar_one_or_none()
    if not user:
        print("No user")
        return None

    user_id = int(user.id)

    fractal_id = getattr(user, "active_fractal_id", None)
    if not fractal_id:
        return None
    fractal_id = int(fractal_id)

    # 2️⃣ Get last round for this fractal
    result = await db.execute(
        select(Round)
        .where(Round.fractal_id == fractal_id)
        .order_by(desc(Round.level))
        .limit(1)
    )
    last_round: Round | None = result.scalar_one_or_none()
    if not last_round:
        return {"fractal_id": fractal_id}

    round_id = int(last_round.id)

    result = await db.execute(
        select(Group)
        .join(GroupMember, Group.id == GroupMember.group_id)
        .where(
            Group.fractal_id == fractal_id,
            GroupMember.user_id == user_id,
#            GroupMember.left_at.is_(None),  # currently in group
        )
        .order_by(Group.round_id.desc())  # pick latest active group
        .limit(1)
    )
    group: Group | None = result.scalar_one_or_none()
    group_id = group.id if group else None
    round_id = group.round_id if group else round_id if group else None


    return {
        "fractal_id": fractal_id,
        "round_id": round_id,
        "group_id": group_id,
        "user_id": user_id,
        "username": user.username,
    }


async def get_fractal_member_repo(db: AsyncSession, fractal_id: int, user_id: int):
    result = await db.execute(
        select(FractalMember).where(
            FractalMember.fractal_id == fractal_id,
            FractalMember.user_id == user_id
        )
    )
    return result.scalars().first()

async def get_fractal_members_repo(db: AsyncSession, fractal_id: int):
    result = await db.execute(
        select(FractalMember).where(
            FractalMember.fractal_id == fractal_id
        )
    )
    return result.scalars().all()


async def get_next_card_repo(
    db: AsyncSession,
    group_id: int,
    current_user_id: int
) -> Optional[Dict]:
    Proposal = models.Proposal
    Comment = models.Comment
    ProposalVote = models.ProposalVote
    CommentVote = models.CommentVote

    # --- 1) Proposals WITHOUT votes from current_user, not created by current_user

    vote_exists = (
        select(ProposalVote.id)
        .where(
            and_(
                ProposalVote.proposal_id == Proposal.id,          # correlate
                ProposalVote.voter_user_id == current_user_id,
            )
        )
        .exists()
    )

    prop_stmt = (
        select(Proposal)
        .where(
            Proposal.group_id == group_id,
            Proposal.creator_user_id != current_user_id,          # not own proposal
            ~vote_exists,                                         # NOT EXISTS
        )
        .order_by(Proposal.created_at.asc())
        .limit(1)
    )

    prop_result = await db.execute(prop_stmt)
    proposal = prop_result.scalars().first()

    if proposal:
        return await _enrich_proposal_with_comments_repo(db, proposal, current_user_id)

    # --- 2) Comments WITHOUT votes from current_user, not created by current_user

    comment_vote_exists = exists().where(
        and_(
            CommentVote.comment_id == Comment.id,
            CommentVote.voter_user_id == current_user_id,
        )
    ).correlate(Comment)

    comment_stmt = (
        select(Comment)
        .join(Proposal, Comment.proposal_id == Proposal.id)
        .where(
            Proposal.group_id == group_id,
            Comment.group_id == group_id,
            Comment.user_id != current_user_id,
            ~comment_vote_exists,  # Now boolean!
        )
        .order_by(Comment.created_at.asc())
        .limit(1)
    )
    comment_result = await db.execute(comment_stmt)
    comment = comment_result.scalars().first()

    if comment:
        return await _enrich_comment_with_proposal_repo(db, comment, current_user_id)

    return None


import asyncio
from typing import Optional, List, Dict

async def get_all_cards_repo(
    db: AsyncSession,
    group_id: int,
    current_user_id: int
) -> Optional[List[Dict[str, any]]]:
    """Load all cards in group and return as list of dicts."""
    Proposal = models.Proposal

    prop_stmt = (
        select(Proposal)
        .where(Proposal.group_id == group_id)
        .order_by(Proposal.created_at.asc())
    )

    prop_result = await db.execute(prop_stmt)
    proposals = prop_result.scalars().all()

    if not proposals:
        return None

    # ✅ Process all proposals in parallel
    proposals_data = await asyncio.gather(*[
        _enrich_proposal_with_comments_repo(db, proposal, current_user_id)
        for proposal in proposals
    ])
    
    # Filter out None values
    proposals_data = [p for p in proposals_data if p]
    
    return proposals_data if proposals_data else None


async def _enrich_proposal_with_comments_repo(
    db: AsyncSession, 
    proposal: Proposal, 
    current_user_id: int
) -> Dict:
    """Enrich proposal to match proposal_card.html template exactly."""
    User = models.User
    ProposalVote = models.ProposalVote
    CommentVote = models.CommentVote
    
    # Proposal creator info (for 'user' in template)
    creator_result = await db.execute(select(User).where(User.id == proposal.creator_user_id))
    creator = creator_result.scalars().first()    

    # take away users own vote
    if (proposal.creator_user_id == current_user_id):
        proposal_vote = -1
    else:
        # Comment vote
        vote_result = await db.execute(
            select(ProposalVote)
            .where(ProposalVote.proposal_id == proposal.id)
            .where(ProposalVote.voter_user_id == current_user_id)
        )
        vote_record = vote_result.scalars().first()
        proposal_vote = vote_record.score if vote_record else 0
        print("proposal_vote ", proposal_vote)

    # ALL comments (matching template structure)
    all_comments = await get_comments_for_proposal_repo(db, proposal.id)
    template_comments = []

    for comment in all_comments:
        # Get comment author
        author_result = await db.execute(select(User).where(User.id == comment.user_id))
        author = author_result.scalars().first()

        # Comment vote
        # take away users own vote
        if (comment.user_id == current_user_id):
            vote = -1
        else:        
            vote_result = await db.execute(
                select(CommentVote)
                .where(CommentVote.comment_id == comment.id)
                .where(CommentVote.voter_user_id == current_user_id)
            )
            vote_record = vote_result.scalars().first()
            vote = vote_record.vote if vote_record else 0
        # ADD THIS: Build and append comment structure
        comment_card = {
            "id": comment.id,
            "message": comment.text,
            "username": author.username,
            "avatar": f"/static/img/64_{(author.id) % 16 + 1}.png",
            "date": comment.created_at.strftime("%Y-%m-%d %H:%M"),
            "vote": vote,
            "text": comment.text,
            # Add other template fields
        }
        template_comments.append(comment_card)        

    
    # ✅ EXACT TEMPLATE STRUCTURE
    card = {
        "username" : creator.username,        
        "id": proposal.id,
        "title": proposal.title,
        "message": proposal.body or "",  # ✅ Template uses 'message'
        "date": proposal.created_at.strftime("%Y-%m-%d %H:%M") if proposal.created_at else "just now",
        "rating_points": 0,  # ✅ Template slider default
        "rating_percent": 0,  # 0-100%
        "tags": proposal.meta.get("tags", []),  # ✅ Template expects 'tags'
        "vote": proposal_vote,  # ✅ Template score pill
        "comments": template_comments  # ✅ Full comments array
    }
    
    return card

async def _enrich_comment_with_proposal_repo(
    db: AsyncSession, 
    comment: Comment, 
    current_user_id: int
) -> Dict:
    """Comment card - wraps proposal context to match template."""
    Proposal = models.Proposal
    User = models.User
    CommentVote = models.CommentVote
    ProposalVote = models.ProposalVote
    
    # Get parent proposal
    prop_result = await db.execute(select(Proposal).where(Proposal.id == comment.proposal_id))
    proposal = prop_result.scalars().first()
    
    # Use proposal enrichment (reuses template logic)
    proposal_card = await _enrich_proposal_with_comments_repo(db, proposal, current_user_id)
    

    return proposal_card

async def get_or_build_round_tree_repo(
    db: AsyncSession,
    fractal_id: int,
    round_id: Optional[int] = None,
) -> Dict[str, Any]:
    Round = models.Round
    RoundTree = models.RoundTree

    # 1) Determine round_id (latest if not provided)
    if round_id is None:
        res = await db.execute(
            select(Round)
            .where(Round.fractal_id == fractal_id)
            .order_by(Round.level.desc())
            .limit(1)
        )
        r = res.scalar_one_or_none()
        if not r:
            # Let caller decide how to handle "no rounds"
            return {"fractal_id": fractal_id, "rounds": []}
        round_id = r.id

    # 2) Try cache
    cached = await db.get(RoundTree, round_id)
    if cached:
        return cached.tree

    # 3) Build on demand and store
    tree = await build_fractal_tree(
        db,
        fractal_id=fractal_id,
        round_id=round_id,
    )

    existing = await db.get(RoundTree, round_id)
    if existing:
        existing.tree = tree
    else:
        db.add(RoundTree(round_id=round_id, fractal_id=fractal_id, tree=tree))
    await db.flush()

    return tree