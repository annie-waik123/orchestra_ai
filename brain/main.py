from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from brain.routers import projects, sessions, artifacts, decisions, audit, evaluations, agents

app = FastAPI(
    title="Orchestra AI: Project Brain API Server",
    description="Exposes structured session memory, artifact dependency trees, and transaction audit trails.",
    version="0.1.0"
)

# Enable CORS for frontend client interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include sub-routers
app.include_router(projects.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(artifacts.router, prefix="/api/v1")
app.include_router(decisions.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(evaluations.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")

@app.get("/health", tags=["health"])
def health_check():
    return {"status": "healthy", "service": "project-brain"}
