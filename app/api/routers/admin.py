# app/api/routers/admin.py
"""
Admin utilities: init database, migrations placeholder.
"""
from fastapi import APIRouter
from app.infrastructure.db.session import Base, engine

router = APIRouter()

@router.post("/init_db", summary="Create all tables in DB")
def init_db():
    """
    Re-create all tables in the database.

    WARNING:
        This does not drop existing tables.
        It only ensures missing tables are created.
    """
    try:
        Base.metadata.create_all(bind=engine)
        return {"status": "ok", "message": "Database initialized"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    

@router.post("/reset_db", summary="Drop and recreate all tables")
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return {"status": "ok", "message": "Database reset"}