# scripts/init_db.py
"""
Script to initialize database tables. Run from project root:
    python scripts/init_db.py
"""
from app.infrastructure.db.session import Base, engine

def init():
    Base.metadata.create_all(bind=engine)
    print("DB initialized")

if __name__ == "__main__":
    init()
