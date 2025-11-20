# main.py
"""
Application entrypoint. Includes routers and mounts.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import fractals, users, groups, proposals, comments, votes, admin
from app.config.settings import settings

app = FastAPI(title="Fractal Governance Backend")

# Basic CORS (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# include routers
app.include_router(fractals.router, prefix="/api/v1/fractals", tags=["fractals"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(groups.router, prefix="/api/v1/groups", tags=["groups"])
app.include_router(proposals.router, prefix="/api/v1/proposals", tags=["proposals"])
app.include_router(comments.router, prefix="/api/v1/comments", tags=["comments"])
app.include_router(votes.router, prefix="/api/v1/votes", tags=["votes"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])


@app.get("/")
async def index():
    """Health / basic info endpoint."""
    return {"status": "ok", "service": "fractal-backend", "env": settings.ENV}
