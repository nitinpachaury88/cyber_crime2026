import uuid
from typing import Optional
from fastapi import WebSocket


class ConnectionManager:
    """Mirrors what Socket.IO gave the Node build, using plain FastAPI
    WebSockets: an 'admin' room, one room per team, and in-memory tracking
    of live investigation sessions (camera/mic) for WebRTC signaling relay.
    """

    def __init__(self):
        # conn_id -> (websocket, CurrentUser)
        self.connections: dict[str, tuple] = {}
        self.admin_conn_ids: set[str] = set()
        self.team_conn_ids: dict[int, set[str]] = {}

        # In-memory only — never persisted/recorded.
        # team_id -> { teamId, teamName, fullName, camera, mic, startedAt, participantConnId }
        self.active_sessions: dict[int, dict] = {}

    def new_conn_id(self) -> str:
        return str(uuid.uuid4())

    async def connect(self, conn_id: str, ws: WebSocket, user) -> None:
        await ws.accept()
        self.connections[conn_id] = (ws, user)
        if user.role == "admin":
            self.admin_conn_ids.add(conn_id)
        else:
            self.team_conn_ids.setdefault(user.team_id, set()).add(conn_id)

    def disconnect(self, conn_id: str):
        entry = self.connections.pop(conn_id, None)
        if not entry:
            return None
        _, user = entry
        self.admin_conn_ids.discard(conn_id)
        if user.team_id in self.team_conn_ids:
            self.team_conn_ids[user.team_id].discard(conn_id)
        return user

    async def send_to_conn(self, conn_id: str, type_: str, payload: dict):
        entry = self.connections.get(conn_id)
        if not entry:
            return
        ws, _ = entry
        try:
            await ws.send_json({"type": type_, "payload": payload})
        except Exception:
            pass

    async def broadcast_admin(self, type_: str, payload: dict):
        dead = []
        for conn_id in list(self.admin_conn_ids):
            entry = self.connections.get(conn_id)
            if not entry:
                continue
            ws, _ = entry
            try:
                await ws.send_json({"type": type_, "payload": payload})
            except Exception:
                dead.append(conn_id)
        for d in dead:
            self.disconnect(d)

    async def broadcast_team(self, team_id: int, type_: str, payload: dict):
        for conn_id in list(self.team_conn_ids.get(team_id, set())):
            await self.send_to_conn(conn_id, type_, payload)

    def online_participants(self):
        out = []
        for conn_id, (ws, user) in self.connections.items():
            if user.role != "admin":
                out.append({"userId": user.id, "fullName": user.full_name, "teamId": user.team_id, "role": user.role})
        return out

    def public_session(self, s: dict) -> dict:
        return {
            "teamId": s["teamId"],
            "teamName": s["teamName"],
            "fullName": s["fullName"],
            "camera": s["camera"],
            "mic": s["mic"],
            "screen": s.get("screen", False),
            "startedAt": s["startedAt"],
            "participantConnId": s["participantConnId"],
        }


manager = ConnectionManager()
