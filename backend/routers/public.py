from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Team, TeamCase
from security import get_current_user, CurrentUser

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/leaderboard")
def leaderboard(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    """Available to admin, leader, and member alike — teams can check standings."""
    teams = db.query(Team).all()
    rows = sorted(teams, key=lambda t: (-(t.total_score - t.hint_penalty), -t.total_score))
    out = []
    for t in rows:
        completed = db.query(TeamCase).filter(TeamCase.team_id == t.id, TeamCase.status == "completed").count()
        out.append({
            "team_name": t.team_name, "net_score": t.total_score - t.hint_penalty, "cases_completed": completed,
        })
    return {"leaderboard": out}
