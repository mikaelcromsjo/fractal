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


class Fractal(Base):
    __tablename__ = "fractals"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=False)
    status = Column(String(50), default="waiting")  # waiting | in_progress | finished
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=now)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(200), nullable=True)
    is_ai = Column(Boolean, default=False)
    prefs = Column(JSON, default={})
    created_at = Column(DateTime, default=now)
    # Optional platform IDs
    telegram_id = Column(String(64), nullable=True, index=True)
    discord_id = Column(String(64), nullable=True, index=True)
    other_id = Column(String(64), nullable=True, index=True)
    

class FractalMember(Base):
    __tablename__ = "fractal_members"
    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    joined_at = Column(DateTime, default=now)
    left_at = Column(DateTime, nullable=True)
    role = Column(String(50), default="member")


class Round(Base):
    __tablename__ = "rounds"
    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    level = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="open")  # open | closed


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), index=True)
    level = Column(Integer, default=0)
    meta = Column(JSON, default={})
    created_at = Column(DateTime, default=now)


class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    joined_at = Column(DateTime, default=now)
    left_at = Column(DateTime, nullable=True)
    replaced_by = Column(Integer, nullable=True)


class Proposal(Base):
    __tablename__ = "proposals"
    id = Column(Integer, primary_key=True)
    fractal_id = Column(Integer, ForeignKey("fractals.id"), index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True, nullable=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), index=True, nullable=True)
    title = Column(String(300), nullable=False)
    body = Column(Text, nullable=True)
    creator_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    type = Column(String(50), default="base")  # base|propagated|merged
    meta = Column(JSON, default={})
    created_at = Column(DateTime, default=now)
    score_per_level = Column(JSON, default={})  # {level: total_score}


class ProposalMerge(Base):
    __tablename__ = "proposal_merges"
    id = Column(Integer, primary_key=True)
    new_proposal_id = Column(Integer, ForeignKey("proposals.id"))
    merged_from_proposal_id = Column(Integer, ForeignKey("proposals.id"))


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), index=True)
    parent_comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now)
    score_per_level = Column(JSON, default={})  #  {"yes": yes_count, "no": no_count}



class ProposalVote(Base):
    __tablename__ = "proposal_votes"
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), index=True)
    voter_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    score = Column(Integer, nullable=False)  # 1..10
    created_at = Column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("proposal_id", "voter_user_id", name="uq_proposal_voter"),)


class CommentVote(Base):
    __tablename__ = "comment_votes"
    id = Column(Integer, primary_key=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), index=True)
    voter_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    vote = Column(Boolean, nullable=False)  # yes/no
    created_at = Column(DateTime, default=now)
    votes_per_level = Column(JSON, default={})  # {level: {"yes": 3, "no": 2}}
    __table_args__ = (UniqueConstraint("comment_id", "voter_user_id", name="uq_comment_voter"),)


class RepresentativeSelection(Base):
    __tablename__ = "representative_selection"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)
    representative_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    method = Column(String(80), default="vote")
    seed = Column(Integer, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50))
    entity_id = Column(Integer)
    action = Column(String(50))
    payload = Column(JSON, default={})
    user_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=now)
