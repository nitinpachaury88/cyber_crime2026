from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif settings.DATABASE_URL.startswith("mysql"):
    connect_args = {"ssl": {"ca": "ca.pem"}}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — one DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def db_session():
    """Plain context-manager style session for code paths without a request
    (e.g. the WebSocket endpoint), used as: `with db_session() as db: ...`"""
    return SessionLocal()