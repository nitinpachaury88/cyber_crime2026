from datetime import datetime, timezone
from sqlalchemy.orm import Session

from database import db_session
from models import ActivityLog, Team, User
from ws_manager import manager


async def log_activity(team_id, user_id, action_type: str, round_name: str = None, detail: str = None, db: Session = None):
    """Writes one activity_log row AND pushes it live to the admin dashboard.
    Pass an existing `db` session when called from inside a request handler
    that already has one open; otherwise a short-lived session is opened."""
    owns_session = db is None
    if owns_session:
        db = db_session()
    try:
        row = ActivityLog(team_id=team_id, user_id=user_id, action_type=action_type, round_name=round_name, detail=detail)
        db.add(row)
        db.commit()

        team_name = None
        user_name = None
        if team_id:
            t = db.query(Team).filter(Team.id == team_id).first()
            team_name = t.team_name if t else None
        if user_id:
            u = db.query(User).filter(User.id == user_id).first()
            user_name = f"{u.full_name} ({u.role})" if u else None

        await manager.broadcast_admin("activity", {
            "teamId": team_id,
            "teamName": team_name,
            "userId": user_id,
            "userName": user_name,
            "actionType": action_type,
            "roundName": round_name,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        if owns_session:
            db.close()
