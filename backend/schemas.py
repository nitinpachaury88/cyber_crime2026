from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ---------------- Auth ----------------
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    fullName: str
    role: str
    teamId: Optional[int] = None
    teamName: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    user: UserOut


# ---------------- Admin: teams ----------------
class CreateTeamRequest(BaseModel):
    teamName: str
    college: Optional[str] = None
    leaderFullName: str
    leaderUsername: str
    leaderPassword: str


class CreateTeamResponse(BaseModel):
    team: Dict[str, Any]
    leader: Dict[str, Any]


# ---------------- Leader ----------------
class AddMemberRequest(BaseModel):
    fullName: str
    username: str
    password: str


# ---------------- Team competition ----------------
class AnswerSubmit(BaseModel):
    questionId: int
    answer: str


class HintReveal(BaseModel):
    hintId: int


class Base64Request(BaseModel):
    text: str


class HashVerifyRequest(BaseModel):
    expectedHash: str
    evidenceHash: str


class EvidenceBoardSubmit(BaseModel):
    orderedEvidenceTypes: List[str]


class FinalSubmit(BaseModel):
    suspect: str
    attackMethod: str
    attackTime: str
    keyEvidence: Optional[str] = None
    investigationTimeline: Optional[str] = None
    conclusion: str


# ---------------- MCQ assessment (case-based, single final submission) ----------------
class SaveAnswerRequest(BaseModel):
    questionId: int
    selectedOption: int  # index 0-7


class RevealHintRequest(BaseModel):
    hintId: int
