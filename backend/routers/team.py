import base64
import binascii
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Team, Case, Evidence, Suspect, Question, Hint, HintUsage, Answer, Submission, TeamCase
from schemas import AnswerSubmit, HintReveal, Base64Request, HashVerifyRequest, EvidenceBoardSubmit, FinalSubmit
from security import get_current_user, require_roles, CurrentUser
from activity import log_activity

router = APIRouter(prefix="/api/team", tags=["team"], dependencies=[Depends(require_roles("leader", "member"))])


def _as_utc(dt):
    """SQLite doesn't persist tzinfo, so a DateTime(timezone=True) column
    comes back naive after a round trip through SQLite even though it was
    saved as UTC-aware. Treat a naive value as already UTC before comparing
    it against an aware datetime.now(timezone.utc)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _get_team(db: Session, team_id: int) -> Team:
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    return team


def _get_case_or_404(db: Session, case_id: int) -> Case:
    case = db.query(Case).filter(Case.id == case_id, Case.active == True).first()  # noqa: E712
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case


def _get_or_create_progress(db: Session, team_id: int, case_id: int) -> TeamCase:
    """A TeamCase row is created lazily the first time a team opens a case —
    this is what lets teams attempt the three cases in any order they like."""
    tc = db.query(TeamCase).filter(TeamCase.team_id == team_id, TeamCase.case_id == case_id).first()
    if not tc:
        tc = TeamCase(team_id=team_id, case_id=case_id, status="not_started")
        db.add(tc)
        db.commit()
        db.refresh(tc)
    return tc


# ---------------- Case selection ----------------

@router.get("/cases")
def list_cases_with_progress(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Powers the case-selection screen: every active case plus this team's
    own progress on it (not_started / in_progress / completed + score)."""
    cases = db.query(Case).filter(Case.active == True).order_by(Case.id.asc()).all()  # noqa: E712
    progress_rows = {tc.case_id: tc for tc in db.query(TeamCase).filter(TeamCase.team_id == user.team_id).all()}

    out = []
    for c in cases:
        tc = progress_rows.get(c.id)
        out.append({
            "id": c.id, "case_code": c.case_code, "title": c.title, "description": c.description,
            "victim_name": c.victim_name, "financial_loss": c.financial_loss, "duration_minutes": c.duration_minutes,
            "status": tc.status if tc else "not_started",
            "score": tc.score if tc else 0,
            "hintPenalty": tc.hint_penalty if tc else 0,
            "timerStartedAt": tc.timer_started_at if tc else None,
            "timerEndsAt": tc.timer_ends_at if tc else None,
        })
    return {"cases": out}


@router.get("/case/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Everything the investigation console needs for ONE case: case info,
    evidence (grouped by type), suspects, questions (answers stripped),
    which questions this team already solved, hints already revealed,
    this case's timer/score, and this case's final report if filed."""
    case = _get_case_or_404(db, case_id)
    tc = _get_or_create_progress(db, user.team_id, case_id)

    evidence = db.query(Evidence).filter(Evidence.case_id == case_id).order_by(Evidence.display_order, Evidence.id).all()
    suspects = db.query(Suspect).filter(Suspect.case_id == case_id).all()
    questions = db.query(Question).filter(Question.case_id == case_id).order_by(Question.display_order, Question.id).all()
    hints = db.query(Hint).filter(Hint.case_id == case_id).all()

    question_ids = [q.id for q in questions]
    solved = db.query(Answer).filter(Answer.team_id == user.team_id, Answer.question_id.in_(question_ids)).all() if question_ids else []

    hint_ids = [h.id for h in hints]
    revealed = (
        db.query(HintUsage, Hint)
        .join(Hint, Hint.id == HintUsage.hint_id)
        .filter(HintUsage.team_id == user.team_id, HintUsage.hint_id.in_(hint_ids))
        .all()
    ) if hint_ids else []

    submission = db.query(Submission).filter(Submission.team_id == user.team_id, Submission.case_id == case_id).first()

    evidence_grouped: dict[str, list] = {}
    for e in evidence:
        evidence_grouped.setdefault(e.evidence_type, []).append({"id": e.id, "title": e.title, "content": e.content})

    return {
        "team": {
            "id": user.team_id,
            "caseStatus": tc.status, "score": tc.score, "hintPenalty": tc.hint_penalty,
            "timerStartedAt": tc.timer_started_at, "timerEndsAt": tc.timer_ends_at,
        },
        "case": {
            "id": case.id, "case_code": case.case_code, "title": case.title, "description": case.description,
            "victim_name": case.victim_name, "financial_loss": case.financial_loss, "duration_minutes": case.duration_minutes,
        },
        "evidence": evidence_grouped,
        "suspects": [{"id": s.id, "name": s.name, "role": s.role, "description": s.description} for s in suspects],
        "questions": [{"id": q.id, "round_name": q.round_name, "question": q.question, "marks": q.marks} for q in questions],
        "hints": [{"id": h.id, "round_name": h.round_name, "penalty": h.penalty} for h in hints],
        "solved": [{"question_id": a.question_id, "is_correct": a.is_correct, "marks_awarded": a.marks_awarded, "answer_text": a.answer_text} for a in solved],
        "revealedHints": [{"id": h.id, "hint_text": h.hint_text} for _, h in revealed],
        "submission": ({"final_score": submission.final_score} if submission else None),
    }


@router.post("/case/{case_id}/timer/start")
async def start_timer(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    case = _get_case_or_404(db, case_id)
    tc = _get_or_create_progress(db, user.team_id, case_id)
    if tc.timer_started_at:
        return {"timerStartedAt": tc.timer_started_at, "timerEndsAt": tc.timer_ends_at}

    now = datetime.now(timezone.utc)
    tc.timer_started_at = now
    tc.timer_ends_at = now + timedelta(minutes=case.duration_minutes)
    tc.status = "in_progress"
    db.commit()

    await log_activity(user.team_id, user.id, "timer_start", round_name=case.case_code,
                        detail=f"Investigation clock started by {user.full_name} on {case.case_code}", db=db)
    return {"timerStartedAt": tc.timer_started_at, "timerEndsAt": tc.timer_ends_at}


@router.post("/case/{case_id}/view")
async def view_evidence(case_id: int, payload: dict, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    await log_activity(user.team_id, user.id, "view_evidence", round_name=payload.get("roundName"), detail=payload.get("detail"), db=db)
    return {"ok": True}


@router.post("/case/{case_id}/answer")
async def submit_answer(case_id: int, payload: AnswerSubmit, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    answer_text = payload.answer.strip()
    if not answer_text:
        raise HTTPException(status_code=400, detail="A non-empty answer is required.")

    question = db.query(Question).filter(Question.id == payload.questionId, Question.case_id == case_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")

    already = db.query(Answer).filter(Answer.team_id == user.team_id, Answer.question_id == payload.questionId).first()
    if already:
        raise HTTPException(status_code=400, detail="Your team already answered this question.")

    is_correct = answer_text.lower() == question.correct_answer.strip().lower()
    marks_awarded = question.marks if is_correct else 0

    db.add(Answer(team_id=user.team_id, question_id=question.id, user_id=user.id,
                   answer_text=answer_text, is_correct=is_correct, marks_awarded=marks_awarded))

    team = _get_team(db, user.team_id)
    tc = _get_or_create_progress(db, user.team_id, case_id)
    if is_correct:
        team.total_score += marks_awarded
        tc.score += marks_awarded
    db.commit()

    short_q = question.question[:60] + ("…" if len(question.question) > 60 else "")
    await log_activity(
        user.team_id, user.id, "answer_submit", round_name=question.round_name,
        detail=f'{user.full_name} answered "{short_q}" — {"correct (+%d)" % marks_awarded if is_correct else "incorrect"}',
        db=db,
    )

    return {"questionId": question.id, "isCorrect": is_correct, "marksAwarded": marks_awarded,
            "caseScore": tc.score, "totalScore": team.total_score, "netScore": team.total_score - team.hint_penalty}


@router.post("/case/{case_id}/hint")
async def reveal_hint(case_id: int, payload: HintReveal, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    hint = db.query(Hint).filter(Hint.id == payload.hintId, Hint.case_id == case_id).first()
    if not hint:
        raise HTTPException(status_code=404, detail="Hint not found.")

    already = db.query(HintUsage).filter(HintUsage.team_id == user.team_id, HintUsage.hint_id == payload.hintId).first()
    team = _get_team(db, user.team_id)
    tc = _get_or_create_progress(db, user.team_id, case_id)
    if not already:
        db.add(HintUsage(team_id=user.team_id, hint_id=payload.hintId, user_id=user.id))
        team.hint_penalty += hint.penalty
        tc.hint_penalty += hint.penalty
        db.commit()
        await log_activity(user.team_id, user.id, "hint_used", round_name=hint.round_name,
                            detail=f"{user.full_name} revealed a hint (−{hint.penalty} pts)", db=db)

    return {"hintId": hint.id, "hintText": hint.hint_text, "penalty": hint.penalty,
            "caseHintPenalty": tc.hint_penalty, "totalScore": team.total_score, "hintPenalty": team.hint_penalty}


@router.post("/forensic/decode")
def forensic_decode(payload: Base64Request):
    try:
        decoded = base64.b64decode(payload.text or "", validate=False).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 input.")
    return {"decoded": decoded}


@router.post("/forensic/hash-verify")
def forensic_hash_verify(payload: HashVerifyRequest):
    match = payload.expectedHash.strip().lower() == payload.evidenceHash.strip().lower()
    return {"match": match}


@router.post("/case/{case_id}/evidence-board")
async def submit_evidence_board(case_id: int, payload: EvidenceBoardSubmit, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    if not payload.orderedEvidenceTypes:
        raise HTTPException(status_code=400, detail="orderedEvidenceTypes must be a non-empty list.")

    case = _get_case_or_404(db, case_id)
    if not case.correct_evidence_order:
        raise HTTPException(status_code=404, detail="Evidence order is not configured for this case.")

    question = db.query(Question).filter(Question.case_id == case_id, Question.round_name == "evidence_board").first()
    if question:
        already = db.query(Answer).filter(Answer.team_id == user.team_id, Answer.question_id == question.id).first()
        if already:
            raise HTTPException(status_code=400, detail="Your team already submitted the evidence board.")

    correct_order = [x.strip().lower() for x in case.correct_evidence_order.split(",")]
    submitted_order = [str(x).strip().lower() for x in payload.orderedEvidenceTypes]
    is_correct = correct_order == submitted_order
    marks_awarded = (question.marks if question else 10) if is_correct else 0

    if question:
        db.add(Answer(team_id=user.team_id, question_id=question.id, user_id=user.id,
                       answer_text=",".join(submitted_order), is_correct=is_correct, marks_awarded=marks_awarded))

    team = _get_team(db, user.team_id)
    tc = _get_or_create_progress(db, user.team_id, case_id)
    if is_correct:
        team.total_score += marks_awarded
        tc.score += marks_awarded
    db.commit()

    await log_activity(user.team_id, user.id, "answer_submit", round_name="evidence_board",
                        detail=f'{user.full_name} arranged the evidence board — {"correct (+%d)" % marks_awarded if is_correct else "incorrect"}',
                        db=db)

    return {"isCorrect": is_correct, "marksAwarded": marks_awarded, "caseScore": tc.score, "totalScore": team.total_score}


@router.post("/case/{case_id}/final")
async def submit_final(case_id: int, payload: FinalSubmit, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    already = db.query(Submission).filter(Submission.team_id == user.team_id, Submission.case_id == case_id).first()
    if already:
        raise HTTPException(status_code=400, detail="Your team has already filed the final report for this case.")

    case = _get_case_or_404(db, case_id)
    team = _get_team(db, user.team_id)
    tc = _get_or_create_progress(db, user.team_id, case_id)

    conclusion_marks = 0
    if case.correct_suspect and payload.suspect.strip().lower() == case.correct_suspect.strip().lower():
        conclusion_marks += 6
    if case.correct_attack_method and case.correct_attack_method.strip().lower() in payload.attackMethod.strip().lower():
        conclusion_marks += 5
    if case.correct_attack_time and payload.attackTime.strip().lower() == case.correct_attack_time.strip().lower():
        conclusion_marks += 4

    team.total_score += conclusion_marks
    tc.score += conclusion_marks
    final_score = tc.score

    db.add(Submission(
        team_id=user.team_id, case_id=case_id, suspect=payload.suspect, attack_method=payload.attackMethod,
        attack_time=payload.attackTime, key_evidence=payload.keyEvidence, investigation_timeline=payload.investigationTimeline,
        conclusion=payload.conclusion, final_score=final_score,
    ))
    tc.status = "completed"
    now = datetime.now(timezone.utc)
    if not tc.timer_ends_at or _as_utc(tc.timer_ends_at) > now:
        tc.timer_ends_at = now
    tc.completed_at = now
    db.commit()

    await log_activity(user.team_id, user.id, "final_submit", round_name=case.case_code,
                        detail=f"{user.full_name} filed the final report for {case.case_code} — case score {final_score}", db=db)

    return {"finalScore": final_score, "conclusionMarksAwarded": conclusion_marks, "totalScore": team.total_score}