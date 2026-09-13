from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    """Admins, team leaders, and team members all live here — same shape as
    the Node build. team_id is NULL for admin accounts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True)
    full_name = Column(String(120), nullable=False)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # admin | leader | member
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    team = relationship("Team", back_populates="members", foreign_keys=[team_id])


class Team(Base):
    """A team is no longer pinned to one case — it can attempt any active
    case, in any order (see TeamCase for per-case progress). total_score /
    hint_penalty here are the running SUM across every case, kept in sync
    incrementally whenever a case-specific score changes — this is what the
    leaderboard and admin team list sort/show."""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    team_name = Column(String(120), unique=True, nullable=False)
    college = Column(String(160), nullable=True)
    access_code = Column(String(20), nullable=False)  # fallback/manual code — fictional, not a real password

    total_score = Column(Integer, nullable=False, default=0)
    hint_penalty = Column(Integer, nullable=False, default=0)

    # The combined, 3-case assessment's 45-minute clock. Set the first time
    # the team opens the assessment (see GET /assessment/state) and never
    # reset by a refresh/navigation — the frontend only ever displays the
    # remaining time computed from assessment_ends_at, it never owns the
    # clock itself. Left NULL until the team actually starts.
    assessment_started_at = Column(DateTime(timezone=True), nullable=True)
    assessment_ends_at = Column(DateTime(timezone=True), nullable=True)

    created_by_admin = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("User", back_populates="team", foreign_keys=[User.team_id], cascade="all, delete-orphan")
    answers = relationship("Answer", back_populates="team", cascade="all, delete-orphan")
    case_progress = relationship("TeamCase", back_populates="team", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="team", cascade="all, delete-orphan")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_code = Column(String(30), unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    victim_name = Column(String(120), nullable=True)
    financial_loss = Column(Integer, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=90)
    active = Column(Boolean, default=True)

    correct_suspect = Column(String(120), nullable=True)
    correct_attack_method = Column(String(300), nullable=True)
    correct_attack_time = Column(String(50), nullable=True)
    correct_evidence_order = Column(String(300), nullable=True)  # comma-separated evidence_type chain

    evidence = relationship("Evidence", back_populates="case", cascade="all, delete-orphan")
    suspects = relationship("Suspect", back_populates="case", cascade="all, delete-orphan")
    questions = relationship("Question", back_populates="case", cascade="all, delete-orphan")
    hints = relationship("Hint", back_populates="case", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    evidence_type = Column(String(30), nullable=False)  # email|login|browser|chat|transaction|document|forensic
    title = Column(String(200), nullable=False)
    content = Column(JSON, nullable=False)
    display_order = Column(Integer, default=0)

    case = relationship("Case", back_populates="evidence")


class Suspect(Base):
    __tablename__ = "suspects"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    role = Column(String(120), nullable=True)
    description = Column(Text, nullable=True)

    case = relationship("Case", back_populates="suspects")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    round_name = Column(String(50), nullable=False)
    question = Column(Text, nullable=False)
    correct_answer = Column(String(300), nullable=False)  # never sent to the client
    options = Column(JSON, nullable=False, default=list)  # exactly 8 answer-option strings, never sent with the correct index marked
    correct_option = Column(Integer, nullable=False, default=0)  # index (0-7) into `options` — never sent to the client
    marks = Column(Integer, default=5)
    display_order = Column(Integer, default=0)

    case = relationship("Case", back_populates="questions")


class QuestionAttempt(Base):
    """The team's current radio-button selection for one question. Upserted
    every time the team picks/changes an answer, holds no correctness info,
    and is never evaluated until AssessmentSubmission is created — this is
    what lets the team freely navigate and change answers pre-submission."""
    __tablename__ = "question_attempts"
    __table_args__ = (UniqueConstraint("team_id", "question_id", name="uq_team_question_attempt"),)

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    selected_option = Column(Integer, nullable=False)  # index 0-7
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AssessmentSubmission(Base):
    """One row per team for the WHOLE assessment (all three cases combined)
    — created only on Final Submission, and its existence is what blocks a
    second submission unless the team retakes (see /assessment/retake)."""
    __tablename__ = "assessment_submissions"
    __table_args__ = (UniqueConstraint("team_id", name="uq_team_assessment_submission"),)

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    case_scores = Column(JSON, nullable=False)  # [{case_id, case_code, title, score, max_score}, ...]
    raw_total = Column(Integer, nullable=False)      # net of hint penalty
    raw_max = Column(Integer, nullable=False)
    hint_penalty = Column(Integer, nullable=False, default=0)
    final_score = Column(Integer, nullable=False)      # out of 100
    percentage = Column(Integer, nullable=False)        # 0-100
    rating = Column(String(40), nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())


class Hint(Base):
    __tablename__ = "hints"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    round_name = Column(String(50), nullable=True)
    hint_text = Column(Text, nullable=False)
    penalty = Column(Integer, default=2)

    case = relationship("Case", back_populates="hints")


class HintUsage(Base):
    __tablename__ = "hint_usage"
    __table_args__ = (UniqueConstraint("team_id", "hint_id", name="uq_team_hint"),)

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    hint_id = Column(Integer, ForeignKey("hints.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime(timezone=True), server_default=func.now())


class TeamCase(Base):
    """Per-team, per-case progress — this is what lets a team attempt all
    three cases in whatever order they like. One row is created lazily the
    first time a team opens a given case."""
    __tablename__ = "team_case"
    __table_args__ = (UniqueConstraint("team_id", "case_id", name="uq_team_case"),)

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)

    status = Column(String(20), nullable=False, default="not_started")  # not_started | in_progress | completed
    timer_started_at = Column(DateTime(timezone=True), nullable=True)
    timer_ends_at = Column(DateTime(timezone=True), nullable=True)

    score = Column(Integer, nullable=False, default=0)         # this case's raw score
    hint_penalty = Column(Integer, nullable=False, default=0)  # this case's hint penalty
    completed_at = Column(DateTime(timezone=True), nullable=True)

    team = relationship("Team", back_populates="case_progress")
    case = relationship("Case")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("team_id", "question_id", name="uq_team_question"),)

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    answer_text = Column(String(300), nullable=True)
    is_correct = Column(Boolean, default=False)
    marks_awarded = Column(Integer, default=0)
    answered_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="answers")


class Submission(Base):
    """One final report per team PER CASE (a team files up to three — one
    for each case it completes)."""
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("team_id", "case_id", name="uq_team_case_submission"),)

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)

    suspect = Column(String(120), nullable=True)
    attack_method = Column(String(300), nullable=True)
    attack_time = Column(String(50), nullable=True)
    key_evidence = Column(Text, nullable=True)
    investigation_timeline = Column(Text, nullable=True)
    conclusion = Column(Text, nullable=True)
    evidence_board_order = Column(String(300), nullable=True)

    final_score = Column(Integer, default=0)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="submissions")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(40), nullable=False)
    round_name = Column(String(50), nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
