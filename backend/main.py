from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import Base, engine
from config import settings
from routers import auth, admin, leader, team, ws, public, assessment

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CyberTrace API",
    description="Digital Crime Scene — a fictional cybercrime investigation game. "
                 "All data is simulated for a college tech-fest event.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CLIENT_ORIGIN] if settings.CLIENT_ORIGIN != "http://localhost:3306" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(leader.router)
app.include_router(team.router)
app.include_router(assessment.router)
app.include_router(public.router)
app.include_router(ws.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/{page_name}.html")
    def page(page_name: str):
        candidate = FRONTEND_DIR / f"{page_name}.html"
        if candidate.exists():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}