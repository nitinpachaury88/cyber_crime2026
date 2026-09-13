from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from database import db_session
from models import Team
from security import decode_token_for_ws
from ws_manager import manager
from activity import log_activity

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    user = decode_token_for_ws(token)
    if not user:
        await websocket.close(code=4401)
        return

    conn_id = manager.new_conn_id()
    await manager.connect(conn_id, websocket, user)

    if user.role != "admin":
        await manager.broadcast_team(user.team_id, "team:presence", {"userId": user.id, "fullName": user.full_name, "online": True})
    await manager.broadcast_admin("admin:presence", {"userId": user.id, "fullName": user.full_name, "teamId": user.team_id, "role": user.role, "online": True})

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            payload = msg.get("payload") or {}
            await _handle_message(conn_id, user, msg_type, payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(conn_id)
        if user.role != "admin":
            await manager.broadcast_team(user.team_id, "team:presence", {"userId": user.id, "fullName": user.full_name, "online": False})

            # If this connection owned an active investigation session, end it.
            session = manager.active_sessions.get(user.team_id)
            if session and session.get("participantConnId") == conn_id:
                del manager.active_sessions[user.team_id]
                await manager.broadcast_admin("session:stopped", {"teamId": user.team_id})
        await manager.broadcast_admin("admin:presence", {"userId": user.id, "fullName": user.full_name, "teamId": user.team_id, "role": user.role, "online": False})


async def _handle_message(conn_id: str, user, msg_type: str, payload: dict):
    # ---------------- Presence / activity ----------------
    if msg_type == "admin:request-online":
        if user.role != "admin":
            return
        await manager.send_to_conn(conn_id, "admin:online-list", manager.online_participants())
        return

    # ------------------------------------------------------------------
    # Investigation Session — explicit-consent camera/microphone sharing.
    # Only a participant can start/stop their own team's session. There is
    # deliberately no message here that lets an admin switch anything on —
    # admins may only request to *watch* a session already started.
    # Signaling is relayed blind; the media itself is encrypted end-to-end
    # by WebRTC (DTLS-SRTP). Nothing is recorded or written to disk.
    # ------------------------------------------------------------------
    if msg_type == "admin:request-sessions":
        if user.role != "admin":
            return
        await manager.send_to_conn(conn_id, "admin:sessions-list", [manager.public_session(s) for s in manager.active_sessions.values()])
        return

    if msg_type == "session:start":
        if user.role == "admin":
            return
        camera = bool(payload.get("camera"))
        mic = bool(payload.get("mic"))
        screen = bool(payload.get("screen"))
        if not camera and not mic and not screen:
            return

        with db_session() as db:  # type: Session
            team = db.query(Team).filter(Team.id == user.team_id).first()
            team_name = team.team_name if team else None

        session = {
            "teamId": user.team_id, "teamName": team_name, "fullName": user.full_name,
            "camera": camera, "mic": mic, "screen": screen, "startedAt": datetime.now(timezone.utc).isoformat(),
            "participantConnId": conn_id,
        }
        manager.active_sessions[user.team_id] = session
        await manager.broadcast_admin("session:started", manager.public_session(session))
        await log_activity(user.team_id, user.id, "session_start", detail=f"camera:{camera} mic:{mic} screen:{screen}")
        return

    if msg_type == "session:stop":
        if user.role == "admin":
            return
        session = manager.active_sessions.get(user.team_id)
        if session and session.get("participantConnId") == conn_id:
            del manager.active_sessions[user.team_id]
            await manager.broadcast_admin("session:stopped", {"teamId": user.team_id})
            await log_activity(user.team_id, user.id, "session_stop")
        return

    if msg_type == "admin:session:watch":
        if user.role != "admin":
            return
        session = manager.active_sessions.get(payload.get("teamId"))
        if not session:
            return
        await manager.send_to_conn(session["participantConnId"], "session:viewer-request", {"viewerConnId": conn_id})
        return

    if msg_type == "admin:session:unwatch":
        if user.role != "admin":
            return
        session = manager.active_sessions.get(payload.get("teamId"))
        if session:
            await manager.send_to_conn(session["participantConnId"], "session:viewer-left", {"viewerConnId": conn_id})
        return

    if msg_type == "session:signal":
        to = payload.get("to")
        data = payload.get("data")
        if not to or not data:
            return
        await manager.send_to_conn(to, "session:signal", {"from": conn_id, "data": data})
        return
