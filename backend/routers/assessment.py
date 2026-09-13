"""
routers/assessment.py
----------------------
The case-based, 8-option-MCQ assessment flow described in the rebuild spec:

  Case 1 -> Case 2 -> Case 3 -> Final Submission

Answers are saved (upserted) as the team navigates, with NO correctness ever
revealed, and NOTHING is scored until POST /assessment/submit-final runs —
at which point every question across all three active cases is evaluated,
each case's raw score is computed, the three are combined, and normalized to
a single 0-100 final score. A team can only submit once unless it retakes.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Team, Case, Question, QuestionAttempt, AssessmentSubmission, Answer, TeamCase, Hint, HintUsage, Evidence, Suspect
from schemas import SaveAnswerRequest, RevealHintRequest
from security import get_current_user, require_roles, CurrentUser
from activity import log_activity

router = APIRouter(prefix="/api/team/assessment", tags=["assessment"], dependencies=[Depends(require_roles("leader", "member"))])

# TESTING ONLY — bumped from 45 minutes so the timer doesn't run out while
# you're still debugging/testing the flow. Change this back to
# timedelta(minutes=45) before the real competition, or teams will get way
# more time than intended.
ASSESSMENT_DURATION = timedelta(minutes=45)


def _rating_for(percentage: int) -> str:
    if percentage >= 90:
        return "Excellent"
    if percentage >= 75:
        return "Good"
    if percentage >= 60:
        return "Satisfactory"
    if percentage >= 40:
        return "Needs Improvement"
    return "Unsatisfactory"


def _active_cases(db: Session):
    return db.query(Case).filter(Case.active == True).order_by(Case.id.asc()).all()  # noqa: E712


def _as_utc(dt):
    """SQLite doesn't persist tzinfo, so a DateTime(timezone=True) column
    comes back timezone-naive after a round trip through SQLite even though
    it was saved as UTC-aware. Comparing that naive value directly against
    datetime.now(timezone.utc) raises TypeError. Treat any naive value as
    already being UTC and attach the tzinfo back before comparing."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _finalize_assessment(db: Session, user: CurrentUser, team: Team) -> AssessmentSubmission:
    """The one place that actually scores and locks the assessment — used
    both by the team's own Final Submit click and by the server-side
    expiry check, so both paths behave identically. Any question with no
    saved QuestionAttempt is simply treated as unanswered (0 marks); it is
    NOT a reason to refuse the submission."""
    cases = _active_cases(db)
    if len(cases) != 3:
        raise HTTPException(status_code=500, detail="The assessment must have exactly 3 active cases configured.")

    case_ids = [c.id for c in cases]
    questions = db.query(Question).filter(Question.case_id.in_(case_ids)).all()
    if not questions:
        raise HTTPException(status_code=500, detail="No questions are configured for this assessment.")

    attempts = {
        a.question_id: a.selected_option
        for a in db.query(QuestionAttempt).filter(QuestionAttempt.team_id == user.team_id).all()
    }

    case_scores = []
    raw_total = 0
    raw_max = 0

    for case in cases:
        case_questions = [q for q in questions if q.case_id == case.id]
        case_score = 0
        case_max = 0
        for q in case_questions:
            case_max += q.marks
            selected = attempts.get(q.id)  # None => left unanswered, always scored as incorrect
            is_correct = selected is not None and selected == q.correct_option
            marks_awarded = q.marks if is_correct else 0
            case_score += marks_awarded

            db.add(Answer(
                team_id=user.team_id, question_id=q.id, user_id=user.id,
                answer_text=(q.options[selected] if selected is not None and 0 <= selected < len(q.options) else None),
                is_correct=is_correct, marks_awarded=marks_awarded,
            ))

        tc = db.query(TeamCase).filter(TeamCase.team_id == user.team_id, TeamCase.case_id == case.id).first()
        if not tc:
            tc = TeamCase(team_id=user.team_id, case_id=case.id)
            db.add(tc)
        tc.status = "completed"
        tc.score = case_score
        tc.completed_at = datetime.now(timezone.utc)

        case_scores.append({
            "case_id": case.id, "case_code": case.case_code, "title": case.title,
            "score": case_score, "max_score": case_max,
        })
        raw_total += case_score
        raw_max += case_max

    final_score = round((raw_total / raw_max) * 100) if raw_max else 0
    percentage = final_score
    rating = _rating_for(percentage)

    # Hint penalty is applied at the combined-assessment level: every point
    # deducted here lowers the /100 final score, but never below 0.
    hint_usages = db.query(HintUsage).filter(HintUsage.team_id == user.team_id).all()
    hint_penalty = 0
    for hu in hint_usages:
        h = db.query(Hint).filter(Hint.id == hu.hint_id).first()
        if h:
            hint_penalty += h.penalty

    if hint_penalty:
        net_total = max(0, raw_total - hint_penalty)
        final_score = round((net_total / raw_max) * 100) if raw_max else 0
        percentage = final_score
        rating = _rating_for(percentage)
        raw_total = net_total

    submission = AssessmentSubmission(
        team_id=user.team_id, case_scores=case_scores, raw_total=raw_total, raw_max=raw_max,
        hint_penalty=hint_penalty, final_score=final_score, percentage=percentage, rating=rating,
    )
    db.add(submission)

    team.total_score = raw_total
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/state")
async def get_assessment_state(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Everything the assessment UI needs: all 3 cases with their questions
    (options included, correct index withheld), this team's saved
    selections so far, this case's relevant hints (text withheld until
    revealed), and the final result if already submitted.

    Also owns the 45-minute clock: starts it on the team's first visit,
    and — because the timer must never rely on the frontend alone — checks
    on every single call whether time has run out, auto-finalizing the
    assessment (via the same scoring path as a manual Final Submit) if so."""
    team = db.query(Team).filter(Team.id == user.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")

    submission = db.query(AssessmentSubmission).filter(AssessmentSubmission.team_id == user.team_id).first()

    if not submission and not team.assessment_started_at:
        now = datetime.now(timezone.utc)
        team.assessment_started_at = now
        team.assessment_ends_at = now + ASSESSMENT_DURATION
        db.commit()
        db.refresh(team)

    auto_finalized = False
    if not submission and team.assessment_ends_at and datetime.now(timezone.utc) >= _as_utc(team.assessment_ends_at):
        submission = _finalize_assessment(db, user, team)
        auto_finalized = True

    if auto_finalized:
        await log_activity(
            user.team_id, user.id, "final_submit", round_name="assessment",
            detail=f"Assessment auto-submitted for {team.team_name} after the 45-minute timer expired — "
                   f"{submission.final_score}/100 ({submission.rating})",
            db=db,
        )

    cases = _active_cases(db)
    case_ids = [c.id for c in cases]
    questions = (
        db.query(Question).filter(Question.case_id.in_(case_ids)).order_by(Question.case_id.asc(), Question.display_order.asc(), Question.id.asc()).all()
        if case_ids else []
    )
    all_hints = db.query(Hint).filter(Hint.case_id.in_(case_ids)).all() if case_ids else []
    all_evidence = db.query(Evidence).filter(Evidence.case_id.in_(case_ids)).order_by(Evidence.display_order, Evidence.id).all() if case_ids else []
    all_suspects = db.query(Suspect).filter(Suspect.case_id.in_(case_ids)).all() if case_ids else []

    attempts = {
        a.question_id: a.selected_option
        for a in db.query(QuestionAttempt).filter(QuestionAttempt.team_id == user.team_id).all()
    }
    revealed_hint_ids = {
        h.hint_id for h in db.query(HintUsage).filter(HintUsage.team_id == user.team_id).all()
    }

    cases_out = []
    for c in cases:
        c_questions = [q for q in questions if q.case_id == c.id]
        # Only show hints for rounds that actually have a question in this
        # rebuilt MCQ case — a case's hint set may include rounds (e.g. an
        # old free-text/forensic round) that no longer has a question.
        # "evidence_board" is a deliberate exception: it's a general,
        # case-wide hint about the order to work through the evidence, not
        # tied to any single question round, so it's always kept.
        active_rounds = {q.round_name for q in c_questions}
        GENERAL_HINT_ROUNDS = {"evidence_board"}
        c_hints = [
            h for h in all_hints
            if h.case_id == c.id and (h.round_name in active_rounds or h.round_name in GENERAL_HINT_ROUNDS or not h.round_name)
        ]

        c_evidence = [e for e in all_evidence if e.case_id == c.id]
        evidence_grouped: dict = {}
        for e in c_evidence:
            evidence_grouped.setdefault(e.evidence_type, []).append({"id": e.id, "title": e.title, "content": e.content})
        c_suspects = [s for s in all_suspects if s.case_id == c.id]

        cases_out.append({
            "id": c.id, "case_code": c.case_code, "title": c.title, "description": c.description,
            "victim_name": c.victim_name, "financial_loss": c.financial_loss,
            "max_score": sum(q.marks for q in c_questions),
            "evidence": evidence_grouped,
            "suspects": [{"id": s.id, "name": s.name, "role": s.role, "description": s.description} for s in c_suspects],
            "questions": [
                {
                    "id": q.id, "round_name": q.round_name, "question": q.question,
                    "options": q.options, "marks": q.marks,
                    "selectedOption": attempts.get(q.id),
                }
                for q in c_questions
            ],
            "hints": [
                {
                    "id": h.id, "round_name": h.round_name, "penalty": h.penalty,
                    "revealed": h.id in revealed_hint_ids,
                    "hintText": h.hint_text if h.id in revealed_hint_ids else None,
                }
                for h in c_hints
            ],
        })

    total_hint_penalty = sum(h.penalty for h in all_hints if h.id in revealed_hint_ids)

    return {
        "cases": cases_out,
        "hintPenalty": total_hint_penalty,
        "locked": submission is not None,
        "result": _submission_out(submission) if submission else None,
        # Server-owned clock — the frontend only ever renders a countdown
        # from these two values (plus its own Date.now()); it never starts,
        # stores, or resets the timer itself, so refreshes, navigating
        # between questions/cases, and reopening the assessment all leave
        # the actual deadline untouched.
        "serverNow": datetime.now(timezone.utc),
        "assessmentStartedAt": team.assessment_started_at,
        "assessmentEndsAt": team.assessment_ends_at,
    }


@router.post("/hint")
async def reveal_hint(payload: RevealHintRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Reveals one hint's text — idempotent (revealing twice never charges
    the penalty twice) and blocked once the assessment is submitted."""
    if db.query(AssessmentSubmission).filter(AssessmentSubmission.team_id == user.team_id).first():
        raise HTTPException(status_code=400, detail="The assessment has already been submitted.")

    hint = db.query(Hint).filter(Hint.id == payload.hintId).first()
    if not hint:
        raise HTTPException(status_code=404, detail="Hint not found.")

    already = db.query(HintUsage).filter(HintUsage.team_id == user.team_id, HintUsage.hint_id == hint.id).first()
    if not already:
        db.add(HintUsage(team_id=user.team_id, hint_id=hint.id, user_id=user.id))
        db.commit()
        await log_activity(user.team_id, user.id, "hint_used", round_name=hint.round_name,
                            detail=f"{user.full_name} revealed a hint (−{hint.penalty} pts)", db=db)

    revealed = db.query(HintUsage).filter(HintUsage.team_id == user.team_id).all()
    total_penalty_sum = 0
    for hu in revealed:
        h2 = db.query(Hint).filter(Hint.id == hu.hint_id).first()
        if h2:
            total_penalty_sum += h2.penalty

    return {"hintId": hint.id, "hintText": hint.hint_text, "penalty": hint.penalty, "totalHintPenalty": total_penalty_sum}


@router.post("/answer")
async def save_answer(payload: SaveAnswerRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Upsert the team's radio-button selection for one question. Never
    evaluated here, never reveals correctness — just persists the choice
    so it survives navigation/refresh until Final Submission."""
    if db.query(AssessmentSubmission).filter(AssessmentSubmission.team_id == user.team_id).first():
        raise HTTPException(status_code=400, detail="The assessment has already been submitted. Retake to change answers.")

    question = db.query(Question).filter(Question.id == payload.questionId).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")
    if not (0 <= payload.selectedOption < len(question.options or [])):
        raise HTTPException(status_code=400, detail="selectedOption is out of range for this question's options.")

    existing = db.query(QuestionAttempt).filter(
        QuestionAttempt.team_id == user.team_id, QuestionAttempt.question_id == question.id
    ).first()
    if existing:
        existing.selected_option = payload.selectedOption
    else:
        db.add(QuestionAttempt(team_id=user.team_id, question_id=question.id, selected_option=payload.selectedOption))
    db.commit()

    return {"questionId": question.id, "selectedOption": payload.selectedOption, "saved": True}


@router.get("/validate")
def validate_complete(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Lists any questions (across all 3 cases) still missing an answer —
    used to block Final Submission and point the team at what's left."""
    cases = _active_cases(db)
    case_ids = [c.id for c in cases]
    questions = db.query(Question).filter(Question.case_id.in_(case_ids)).all() if case_ids else []
    answered_ids = {
        a.question_id for a in db.query(QuestionAttempt).filter(QuestionAttempt.team_id == user.team_id).all()
    }
    case_by_id = {c.id: c for c in cases}
    missing = [
        {"questionId": q.id, "caseId": q.case_id, "caseCode": case_by_id[q.case_id].case_code, "question": q.question}
        for q in questions if q.id not in answered_ids
    ]
    return {"complete": len(missing) == 0, "missing": missing, "totalQuestions": len(questions), "answeredCount": len(questions) - len(missing)}


def _submission_out(s: AssessmentSubmission) -> dict:
    return {
        "caseScores": s.case_scores,
        "rawTotal": s.raw_total,
        "rawMax": s.raw_max,
        "hintPenalty": s.hint_penalty,
        "finalScore": s.final_score,
        "percentage": s.percentage,
        "rating": s.rating,
        "submittedAt": s.submitted_at,
    }


@router.post("/submit-final")
async def submit_final(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """The ONE Final Submission action for the whole assessment. A team may
    submit from any point in the flow — answered questions are graded,
    anything left blank is simply scored as incorrect (0 marks), and the
    assessment is permanently locked against further changes or a second
    submission. Duplicate submissions (e.g. a double-click, or the 45:00
    timer expiring in the same instant as a manual click) are rejected
    safely without corrupting the original result."""
    already = db.query(AssessmentSubmission).filter(AssessmentSubmission.team_id == user.team_id).first()
    if already:
        raise HTTPException(status_code=400, detail="This assessment has already been submitted.")

    team = db.query(Team).filter(Team.id == user.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")

    try:
        submission = _finalize_assessment(db, user, team)
    except IntegrityError:
        # Another request (e.g. the expiry auto-submit) finalized it a
        # moment earlier — treat this as "already submitted", not a crash.
        db.rollback()
        existing = db.query(AssessmentSubmission).filter(AssessmentSubmission.team_id == user.team_id).first()
        if existing:
            return _submission_out(existing)
        raise HTTPException(status_code=400, detail="This assessment has already been submitted.")

    await log_activity(
        user.team_id, user.id, "final_submit", round_name="assessment",
        detail=f"{user.full_name} submitted the final assessment — {submission.final_score}/100 ({submission.rating})",
        db=db,
    )

    return _submission_out(submission)


@router.post("/retake")
async def retake_assessment(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Explicit reset: clears saved selections and the locked submission so
    the team can attempt the assessment again. The only way to submit a
    second time — this is never done automatically."""
    db.query(QuestionAttempt).filter(QuestionAttempt.team_id == user.team_id).delete()
    db.query(HintUsage).filter(HintUsage.team_id == user.team_id).delete()
    db.query(AssessmentSubmission).filter(AssessmentSubmission.team_id == user.team_id).delete()
    for tc in db.query(TeamCase).filter(TeamCase.team_id == user.team_id).all():
        tc.status = "not_started"
        tc.score = 0
        tc.completed_at = None
    db.commit()

    await log_activity(user.team_id, user.id, "assessment_retake", round_name="assessment",
                        detail=f"{user.full_name} reset the assessment for a retake.", db=db)
    return {"reset": True}