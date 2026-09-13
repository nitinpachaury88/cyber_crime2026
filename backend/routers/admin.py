import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Team, User, Case, Answer, Question, HintUsage, Hint, ActivityLog, Submission, TeamCase
from schemas import CreateTeamRequest
from security import get_current_user, require_roles, hash_password, random_access_code, CurrentUser
from activity import log_activity

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_roles("admin"))])


@router.post("/teams", status_code=201)
async def create_team(payload: CreateTeamRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    if len(payload.leaderPassword) < 6:
        raise HTTPException(status_code=400, detail="Leader password must be at least 6 characters.")

    if db.query(User).filter(User.username == payload.leaderUsername.strip()).first():
        raise HTTPException(status_code=409, detail="That leader username is already taken.")
    if db.query(Team).filter(Team.team_name == payload.teamName.strip()).first():
        raise HTTPException(status_code=409, detail="That team name is already taken.")

    # A team can attempt any active case in any order, so nothing is
    # assigned here — just the team + its leader login.
    team = Team(
        team_name=payload.teamName.strip(),
        college=payload.college or None,
        access_code=random_access_code(),
        created_by_admin=user.id,
    )
    db.add(team)
    db.flush()  # get team.id before commit

    leader = User(
        team_id=team.id,
        full_name=payload.leaderFullName.strip(),
        username=payload.leaderUsername.strip(),
        password_hash=hash_password(payload.leaderPassword),
        role="leader",
    )
    db.add(leader)
    try:
        db.commit()
    except IntegrityError:
        # Two "Create Team" requests raced each other (e.g. a double click):
        # both passed the pre-checks above before either committed, so the
        # database's own unique constraint is what actually caught the
        # duplicate. Roll back cleanly and report it the same way the
        # pre-check does, instead of letting this surface as a 500.
        db.rollback()
        raise HTTPException(status_code=409, detail="That team name or leader username is already taken.")
    db.refresh(team)
    db.refresh(leader)

    await log_activity(team.id, user.id, "team_created", detail=f'Admin created team "{team.team_name}" with leader "{leader.username}"', db=db)

    return {
        "team": {"id": team.id, "teamName": team.team_name, "college": team.college, "accessCode": team.access_code},
        "leader": {"id": leader.id, "username": leader.username, "fullName": leader.full_name},
    }


@router.get("/teams")
def list_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).order_by(Team.total_score.desc(), Team.created_at.asc()).all()
    out = []
    for t in teams:
        member_count = db.query(User).filter(User.team_id == t.id).count()
        correct_answers = db.query(Answer).filter(Answer.team_id == t.id, Answer.is_correct == True).count()  # noqa: E712
        last_activity = (
            db.query(ActivityLog.created_at)
            .filter(ActivityLog.team_id == t.id)
            .order_by(ActivityLog.created_at.desc())
            .first()
        )
        progress = (
            db.query(TeamCase, Case)
            .join(Case, Case.id == TeamCase.case_id)
            .filter(TeamCase.team_id == t.id)
            .all()
        )
        cases_completed = sum(1 for tc, _ in progress if tc.status == "completed")
        cases_in_progress = sum(1 for tc, _ in progress if tc.status == "in_progress")
        out.append({
            "id": t.id, "team_name": t.team_name, "college": t.college,
            "access_code": t.access_code, "total_score": t.total_score, "hint_penalty": t.hint_penalty,
            "created_at": t.created_at,
            "cases_completed": cases_completed, "cases_in_progress": cases_in_progress, "cases_total": 3,
            "case_progress": [{"case_code": c.case_code, "case_title": c.title, "status": tc.status, "score": tc.score} for tc, c in progress],
            "member_count": member_count, "correct_answers": correct_answers,
            "last_activity_at": last_activity[0] if last_activity else None,
        })
    return {"teams": out}


@router.get("/teams/{team_id}")
def team_detail(team_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")

    progress = (
        db.query(TeamCase, Case)
        .join(Case, Case.id == TeamCase.case_id)
        .filter(TeamCase.team_id == team_id)
        .all()
    )

    members = db.query(User).filter(User.team_id == team_id).order_by(User.role.desc(), User.id.asc()).all()

    answers = (
        db.query(Answer, Question, User)
        .join(Question, Question.id == Answer.question_id)
        .outerjoin(User, User.id == Answer.user_id)
        .filter(Answer.team_id == team_id)
        .order_by(Answer.answered_at.asc())
        .all()
    )
    hints_used = (
        db.query(HintUsage, Hint, User)
        .join(Hint, Hint.id == HintUsage.hint_id)
        .outerjoin(User, User.id == HintUsage.user_id)
        .filter(HintUsage.team_id == team_id)
        .order_by(HintUsage.used_at.asc())
        .all()
    )
    activity = (
        db.query(ActivityLog, User)
        .outerjoin(User, User.id == ActivityLog.user_id)
        .filter(ActivityLog.team_id == team_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(100)
        .all()
    )
    submissions = (
        db.query(Submission, Case)
        .join(Case, Case.id == Submission.case_id)
        .filter(Submission.team_id == team_id)
        .all()
    )

    return {
        "team": {
            "id": team.id, "team_name": team.team_name, "college": team.college,
            "total_score": team.total_score, "hint_penalty": team.hint_penalty,
        },
        "caseProgress": [{
            "case_code": c.case_code, "case_title": c.title, "status": tc.status,
            "score": tc.score, "hint_penalty": tc.hint_penalty,
            "timer_started_at": tc.timer_started_at, "timer_ends_at": tc.timer_ends_at,
        } for tc, c in progress],
        "members": [{"id": m.id, "full_name": m.full_name, "role": m.role, "last_login_at": m.last_login_at} for m in members],
        "answers": [{
            "id": a.id, "answer_text": a.answer_text, "is_correct": a.is_correct, "marks_awarded": a.marks_awarded,
            "round_name": q.round_name, "question": q.question, "answered_by": u.full_name if u else None,
        } for a, q, u in answers],
        "hintsUsed": [{
            "round_name": h.round_name, "hint_text": h.hint_text, "penalty": h.penalty,
            "used_by": u.full_name if u else None,
        } for _, h, u in hints_used],
        "activity": [{
            "action_type": al.action_type, "round_name": al.round_name, "detail": al.detail,
            "created_at": al.created_at, "actor": u.full_name if u else None,
        } for al, u in activity],
        "submissions": [{
            "case_code": c.case_code, "case_title": c.title, "suspect": s.suspect, "attack_method": s.attack_method,
            "attack_time": s.attack_time, "final_score": s.final_score, "submitted_at": s.submitted_at,
        } for s, c in submissions],
    }


@router.delete("/teams/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    db.delete(team)
    db.commit()
    return {"ok": True}


@router.get("/activity")
def recent_activity(limit: int = 50, db: Session = Depends(get_db)):
    limit = min(limit, 200)
    rows = (
        db.query(ActivityLog, Team, User)
        .outerjoin(Team, Team.id == ActivityLog.team_id)
        .outerjoin(User, User.id == ActivityLog.user_id)
        .order_by(ActivityLog.created_at.desc())

        
        .limit(limit)
        .all()
    )
    return {"activity": [{
        "id": al.id, "action_type": al.action_type, "round_name": al.round_name, "detail": al.detail,
        "created_at": al.created_at, "team_name": t.team_name if t else None,
        "actor": u.full_name if u else None, "actor_role": u.role if u else None,
    } for al, t, u in rows]}


@router.get("/leaderboard")
def leaderboard(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    rows = sorted(teams, key=lambda t: (-(t.total_score - t.hint_penalty), -t.total_score))
    out = []
    for t in rows:
        completed = db.query(TeamCase).filter(TeamCase.team_id == t.id, TeamCase.status == "completed").count()
        out.append({
            "team_name": t.team_name, "total_score": t.total_score, "hint_penalty": t.hint_penalty,
            "cases_completed": completed, "net_score": t.total_score - t.hint_penalty,
        })
    return {"leaderboard": out}


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    rows = sorted(teams, key=lambda t: -(t.total_score - t.hint_penalty))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Team", "College", "Cases Completed", "Score", "Hint Penalty", "Net Score"])
    for t in rows:
        completed = db.query(TeamCase).filter(TeamCase.team_id == t.id, TeamCase.status == "completed").count()
        writer.writerow([t.team_name, t.college or "", f"{completed}/3", t.total_score, t.hint_penalty,
                          t.total_score - t.hint_penalty])
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )


@router.get("/cases")
def list_cases(db: Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.id.asc()).all()
    return {"cases": [{"id": c.id, "case_code": c.case_code, "title": c.title, "active": c.active} for c in cases]}
