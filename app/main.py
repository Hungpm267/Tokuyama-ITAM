from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import engine, Base, SessionLocal
import app.models  # Ensure all models are registered in Base.metadata
from app.services.seed import seed_all_data
from app.api.router import api_router
from app.web.router import web_router
from app.admin import setup_admin

BASE_DIR = Path(__file__).resolve().parent.parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create database tables if they do not exist
    Base.metadata.create_all(bind=engine)
    # 2. Seed initial roles, users, and base categories
    db = SessionLocal()
    try:
        seed_all_data(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. Starlette Session Middleware (Required by SQLAdmin & Session Auth)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=1800  # 30 minutes
)

# 2. Mount Static Files
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 3. Mount Routers
app.include_router(web_router)
app.include_router(api_router)

# 4. Mount SQLAdmin
setup_admin(app)
