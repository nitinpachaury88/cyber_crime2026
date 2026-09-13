from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from database import get_db
from models import User, Team
from schemas import LoginRequest, LoginResponse, UserOut
from security import verify_password, create_access_token, get_current_user, CurrentUser
from activity import log_activity

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Works for admin, team-leader, and team-member accounts alike — the
    role (and, for leader/member, the team) comes straight from the users table."""
    username = payload.username.strip()
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    team_name = None
    if user.team_id:
        team = db.query(Team).filter(Team.id == user.team_id).first()
        if team:
            team_name = team.team_name

    token = create_access_token({
        "id": user.id, "username": user.username, "fullName": user.full_name,
        "role": user.role, "teamId": user.team_id,
    })

    await log_activity(user.team_id, user.id, "login", detail=f'{user.role} "{user.full_name}" logged in', db=db)

    response.set_cookie("token", token, httponly=True, samesite="lax", max_age=12 * 60 * 60)

    return LoginResponse(
        token=token,
        user=UserOut(id=user.id, username=user.username, fullName=user.full_name, role=user.role,
                     teamId=user.team_id, teamName=team_name),
    )


@router.post("/logout")
async def logout(response: Response, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    await log_activity(user.team_id, user.id, "logout", detail=f'{user.role} "{user.full_name}" logged out', db=db)
    response.delete_cookie("token")
    return {"ok": True}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {"user": {"id": user.id, "username": user.username, "fullName": user.full_name, "role": user.role, "teamId": user.team_id}}
