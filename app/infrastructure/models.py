# app/infrastructure/models.py
"""
SQLAlchemy ORM models for the fractal system.
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from app.infrastructure.db.session import Base

def now():
    datetime.now(timezone.utc)

from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref

Base = declarative_base()


class Fractal(Base):
    __tablename__ = "fractals"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=False)
    status = Column(String(50), default="waiting")
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=now)

    # Relationships
    members = relationship("FractalMember", back_populates="fractal")
    rounds = relationship("Round", back_populates="fractal")
    proposals = relationship("Proposal", back_populates="fractal")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(200), nullable=True)
    is_ai = Column(Boolean, default=False)
    prefs = Column(JSON, default={})
    created_at = Column(DateTime, default=now)

    telegram_id = Column(String(64), nullable=True, index=True)
    discord_id = Column(String(64), nullable=True, index=True)
    other_id = Column(String(64), nullable=True, index=True)

    # Relationships
    fractal_memberships = relationship("FractalMember", back_populates="user")
    group_memberships = relationship("GroupMember", back_populates="user")
    proposals_created = relationship("Proposal", back_populates="creator")
    proposal_votes = relationship("ProposalVote", back_populates="voter")
    comments = relationship("Comment", back_populates="user")
    comment_votes = relationship("CommentVote", back_populates="voter")
    representative_positions = relationship(
        "RepresentativeSelection", back_populates="representative"
    )


class FractalMember(Base):
    __tablename__ = "fractal_members"

    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    joined_at = Column(DateTime, default=now)
    left_at = Column(DateTime, nullable=True)
    role = Column(String(50), default="member")

    # Relationships
    fractal = relationship("Fractal", back_populates="members")
    user = relationship("User", back_populates="fractal_memberships")


class Round(Base):
    __tablename__ = "rounds"

    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    level = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="open")

    # Relationships
    fractal = relationship("Fractal", back_populates="rounds")
    groups = relationship("Group", back_populates="round")
    proposals = relationship("Proposal", back_populates="round")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), index=True)
    level = Column(Integer, default=0)
    meta = Column(JSON, default={})
    created_at = Column(DateTime, default=now)

    # Relationships
    round = relationship("Round", back_populates="groups")
    members = relationship("GroupMember", back_populates="group")
    proposals = relationship("Proposal", back_populates="group")
    representative_selections = relationship(
        "RepresentativeSelection", back_populates="group"
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    joined_at = Column(DateTime, default=now)
    left_at = Column(DateTime, nullable=True)
    replaced_by = Column(Integer, nullable=True)

    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")


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
    meta = Column(JSON, default={})
    created_at = Column(DateTime, default=now)
    score_per_level = Column(JSON, default={})

    # Relationships
    fractal = relationship("Fractal", back_populates="proposals")
    group = relationship("Group", back_populates="proposals")
    round = relationship("Round", back_populates="proposals")
    creator = relationship("User", back_populates="proposals_created")

    comments = relationship("Comment", back_populates="proposal")
    votes = relationship("ProposalVote", back_populates="proposal")

    merged_from = relationship(
        "ProposalMerge",
        foreign_keys="ProposalMerge.new_proposal_id",
        back_populates="merged_into",
    )

    merged_into = relationship(
        "ProposalMerge",
        foreign_keys="ProposalMerge.merged_from_proposal_id",
        back_populates="merged_from",
    )


class ProposalMerge(Base):
    __tablename__ = "proposal_merges"

    id = Column(Integer, primary_key=True)
    new_proposal_id = Column(Integer, ForeignKey("proposals.id"))
    merged_from_proposal_id = Column(Integer, ForeignKey("proposals.id"))

    merged_into = relationship(
        "Proposal", foreign_keys=[new_proposal_id], back_populates="merged_from"
    )
    merged_from = relationship(
        "Proposal", foreign_keys=[merged_from_proposal_id], back_populates="merged_into"
    )


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), index=True)
    parent_comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now)
    score_per_level = Column(JSON, default={})

    # Relationships
    proposal = relationship("Proposal", back_populates="comments")
    user = relationship("User", back_populates="comments")

    replies = relationship("Comment", backref=backref("parent", remote_side=[id]))
    votes = relationship("CommentVote", back_populates="comment")


class ProposalVote(Base):
    __tablename__ = "proposal_votes"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), index=True)
    voter_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    score = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=now)

    __table_args__ = (
        UniqueConstraint("proposal_id", "voter_user_id", name="uq_proposal_voter"),
    )

    # Relationships
    proposal = relationship("Proposal", back_populates="votes")
    voter = relationship("User", back_populates="proposal_votes")


class CommentVote(Base):
    __tablename__ = "comment_votes"

    id = Column(Integer, primary_key=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), index=True)
    voter_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    vote = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=now)
    votes_per_level = Column(JSON, default={})

    __table_args__ = (
        UniqueConstraint("comment_id", "voter_user_id", name="uq_comment_voter"),
    )

    # Relationships
    comment = relationship("Comment", back_populates="votes")
    voter = relationship("User", back_populates="comment_votes")


class RepresentativeSelection(Base):
    __tablename__ = "representative_selection"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    representative_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    method = Column(String(80), default="vote")
    seed = Column(Integer, nullable=True)

    # Relationships
    group = relationship("Group", back_populates="representative_selections")
    representative = relationship("User", back_populates="representative_positions")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50))
    entity_id = Column(Integer)
    action = Column(String(50))
    payload = Column(JSON, default={})
    user_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=now)
