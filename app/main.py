from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.projects import router as projects_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for frontend and testing interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 sub-routers
app.include_router(projects_router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["health"])
def health_check():
    """Service health state checks."""
    return {
        "status": "healthy",
        "version": settings.PROJECT_VERSION
    }
