from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Team, User, Case, TeamCase
from schemas import AddMemberRequest
from security import get_current_user, require_roles, hash_password, CurrentUser
from activity import log_activity

router = APIRouter(prefix="/api/leader", tags=["leader"], dependencies=[Depends(require_roles("leader"))])


@router.get("/team")
def get_team(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    team = db.query(Team).filter(Team.id == user.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    progress = (
        db.query(TeamCase, Case)
        .join(Case, Case.id == TeamCase.case_id)
        .filter(TeamCase.team_id == user.team_id)
        .all()
    )
    members = db.query(User).filter(User.team_id == user.team_id).order_by(User.role.desc(), User.id.asc()).all()
    return {
        "team": {
            "id": team.id, "team_name": team.team_name, "college": team.college,
            "total_score": team.total_score, "hint_penalty": team.hint_penalty,
        },
        "caseProgress": [{"case_code": c.case_code, "case_title": c.title, "status": tc.status, "score": tc.score} for tc, c in progress],
        "members": [{"id": m.id, "full_name": m.full_name, "username": m.username, "role": m.role,
                      "is_active": m.is_active, "last_login_at": m.last_login_at} for m in members],
    }


@router.post("/members", status_code=201)
async def add_member(payload: AddMemberRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    existing_count = db.query(User).filter(User.team_id == user.team_id).count()
    if existing_count >= 6:
        raise HTTPException(status_code=400, detail="This team already has the maximum number of members (6).")

    if db.query(User).filter(User.username == payload.username.strip()).first():
        raise HTTPException(status_code=409, detail="That username is already taken.")

    member = User(
        team_id=user.team_id, full_name=payload.fullName.strip(), username=payload.username.strip(),
        password_hash=hash_password(payload.password), role="member",
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    await log_activity(user.team_id, user.id, "member_added", detail=f'Leader "{user.full_name}" added teammate "{member.full_name}"', db=db)

    return {"member": {"id": member.id, "fullName": member.full_name, "username": member.username, "role": "member"}}


@router.delete("/members/{member_id}")
async def remove_member(member_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    member = db.query(User).filter(User.id == member_id, User.team_id == user.team_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found on your team.")
    if member.role == "leader":
        raise HTTPException(status_code=400, detail="You can't remove the team leader.")

    full_name = member.full_name
    db.delete(member)
    db.commit()

    await log_activity(user.team_id, user.id, "member_removed", detail=f'Removed "{full_name}"', db=db)
    return {"ok": True}
