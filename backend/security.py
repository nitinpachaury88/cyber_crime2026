import random
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Cookie, Header
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def random_access_code(length: int = 6) -> str:
    """Fictional fallback code shown to organizers — not a real password."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session. Please log in again.")


class CurrentUser:
    """Lightweight stand-in for the decoded token payload, mirroring the
    Node build's req.user shape: { id, username, fullName, role, teamId }."""

    def __init__(self, payload: dict):
        self.id: int = int(payload["id"])
        self.username: str = payload["username"]
        self.full_name: str = payload["fullName"]
        self.role: str = payload["role"]
        self.team_id: Optional[int] = payload.get("teamId")


def _extract_token(authorization: Optional[str], token_cookie: Optional[str]) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    if token_cookie:
        return token_cookie
    return None


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Cookie(default=None),
) -> CurrentUser:
    raw = _extract_token(authorization, token)
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    payload = decode_token(raw)
    return CurrentUser(payload)


def require_roles(*roles: str):
    """Usage: Depends(require_roles('admin')) or Depends(require_roles('leader', 'member'))"""

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to do that.")
        return user

    return dependency


def decode_token_for_ws(token: Optional[str]) -> Optional[CurrentUser]:
    """Same as get_current_user but for the WebSocket handshake, where a
    token is passed as a query parameter instead of a header/cookie."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        return CurrentUser(payload)
    except HTTPException:
        return None
