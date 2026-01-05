# app/infrastructure/models.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, func, CheckConstraint, Float
from sqlalchemy.orm import relationship, backref
from datetime import datetime, timezone
from infrastructure.db.session import Base
from sqlalchemy.dialects.postgresql import JSONB


# Queue

class QueueItem(Base):
    __tablename__ = "queue_items"

    id = Column(Integer, primary_key=True)

    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 0 = proposal, 1 = comment
    item_type = Column(Integer, nullable=False)

    # proposal_id or comment_id
    item_id = Column(Integer, nullable=False)

    consumed = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")
    group = relationship("Group")

    def __repr__(self):
        return (
            f"<QueueItem id={self.id} u={self.user_id} "
            f"type={self.item_type} item={self.item_id} consumed={self.consumed}>"
        )

# ----------------------------
# User
# ----------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(200), nullable=True)
    telegram_id = Column(String(64), nullable=True, index=True)
    other_id = Column(String(64), nullable=True, index=True)
    prefs = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    active_fractal_id = Column(Integer)

    # Private relationships 
    """
    fractal_memberships = relationship("FractalMember", back_populates="_user")
    _group_memberships = relationship("GroupMember", back_populates="_user")
    _proposals_created = relationship("Proposal", back_populates="_creator")
    _proposal_votes = relationship("ProposalVote", back_populates="_voter")
    _comments = relationship("Comment", back_populates="_user")
    _comment_votes = relationship("CommentVote", back_populates="_voter")
    _representative_positions = relationship("RepresentativeSelection", back_populates="_representative")
"""

# ----------------------------
# Fractal
# ----------------------------
class Fractal(Base):
    __tablename__ = "fractals"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(50), default="waiting")
    settings = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=func.now())
    meta = Column(JSON, default=dict)

    # Private relationships
    """
    _members = relationship("FractalMember", back_populates="_fractal")
    _rounds = relationship("Round", back_populates="_fractal")
    _proposals = relationship("Proposal", back_populates="_fractal")
    _groups = relationship("Group", back_populates="_fractal")
"""


class FractalMember(Base):
    __tablename__ = "fractal_members"
    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    joined_at = Column(DateTime(timezone=True), default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)
    role = Column(String(50), default="member")

"""
    # Private relationships
    _fractal = relationship("Fractal", back_populates="_members")
    _user = relationship("User", back_populates="_fractal_memberships")
"""

# ----------------------------
# Round
# ----------------------------
class Round(Base):
    __tablename__ = "rounds"
    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    level = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="open")
"""
    _fractal = relationship("Fractal", back_populates="_rounds")
    _groups = relationship("Group", back_populates="_round")
    _proposals = relationship("Proposal", back_populates="_round")
"""

# ----------------------------
# Group
# ----------------------------
class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), index=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True, nullable=False)
    level = Column(Integer, default=0)
    meta = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=func.now())

"""
    _round = relationship("Round", back_populates="_groups")
    _members = relationship("GroupMember", back_populates="_group")
    _proposals = relationship("Proposal", back_populates="_group")
    _representative_selections = relationship("RepresentativeSelection", back_populates="_group")
    _fractal = relationship("Fractal", back_populates="_groups")
"""

class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    joined_at = Column(DateTime(timezone=True), default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by = Column(Integer, nullable=True)
"""
    _group = relationship("Group", back_populates="_members")
    _user = relationship("User", back_populates="_group_memberships")
"""

# ----------------------------
# Proposal
# ----------------------------
class Proposal(Base):
    __tablename__ = "proposals"
    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True, nullable=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), index=True, nullable=True)
    title = Column(String(300), nullable=False)
    body = Column(Text, nullable=True)
    creator_user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String(50), default="base")
    meta = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=func.now())
    score_per_level = Column(JSONB, default=list)
    total_score = Column(Float)
"""
    _fractal = relationship("Fractal", back_populates="_proposals")
    _group = relationship("Group", back_populates="_proposals")
    _round = relationship("Round", back_populates="_proposals")
    _creator = relationship("User", back_populates="_proposals_created")
    _comments = relationship("Comment", back_populates="_proposal")
    _votes = relationship("ProposalVote", back_populates="_proposal")
"""

    # ----------------------------
# Comment
# ----------------------------
class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), index=True)
    parent_comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    score_per_level = Column(JSONB, default=list)
    total_score = Column(Float)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)

"""
    _proposal = relationship("Proposal", back_populates="_comments")
    _user = relationship("User", back_populates="_comments")
    _replies = relationship("Comment", backref=backref("_parent", remote_side=[id]))
    _votes = relationship("CommentVote", back_populates="_comment")
"""

# ----------------------------
# ProposalVote
# ----------------------------
class ProposalVote(Base):
    __tablename__ = "proposal_votes"
    id = Column(Integer, primary_key=True)
#    level = Column(Integer, nullable=False)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), index=True)
    voter_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    score = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (UniqueConstraint("proposal_id", "voter_user_id", name="uq_proposal_voter"),)
"""
    _proposal = relationship("Proposal", back_populates="_votes")
    _voter = relationship("User", back_populates="_proposal_votes")
"""

# ----------------------------
# CommentVote
# ----------------------------
class CommentVote(Base):
    __tablename__ = "comment_votes"
    id = Column(Integer, primary_key=True)
#    level = Column(Integer, nullable=False)
    comment_id = Column(Integer, ForeignKey("comments.id"), index=True)
    voter_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    vote = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
#    votes_per_level = Column(JSONB, default=dict)

    __table_args__ = (UniqueConstraint("comment_id", "voter_user_id", name="uq_comment_voter"),)
"""
    _comment = relationship("Comment", back_populates="_votes")
    _voter = relationship("User", back_populates="_comment_votes")
"""

# ----------------------------
# RepresentativeVote
# ----------------------------
class RepresentativeVote(Base):
    __tablename__ = "representative_votes"
    
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), index=True)  # Add round context
    voter_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    candidate_user_id = Column(Integer, ForeignKey("users.id"), index=True)    
    created_at = Column(DateTime(timezone=True), default=func.now())
    points = Column(Integer, nullable=False)
    
    UniqueConstraint(
        "group_id", "round_id", "voter_user_id", "points", 
        name="unique_vote_per_points"
    ),

# ----------------------------
# RepresentativeSelection
# ----------------------------
class RepresentativeSelection(Base):
    __tablename__ = "representative_selection"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    representative_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=func.now())
    method = Column(String(80), default="vote")
    seed = Column(Integer, nullable=True)

"""
    _group = relationship("Group", back_populates="_representative_selections")
    _representative = relationship("User", back_populates="_representative_positions")
"""

# ----------------------------
# AuditLog
# ----------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50))
    entity_id = Column(Integer)
    action = Column(String(50))
    payload = Column(JSONB, default=dict)
    user_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=func.now())


class RoundTree(Base):
    __tablename__ = "round_trees"

    round_id = Column(Integer, ForeignKey("rounds.id"), primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    tree = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())