from fastapi import APIRouter, HTTPException
from fastapi import Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.services.group_service import GroupService
from app.infrastructure.db.session import get_db

router = APIRouter()
svc = GroupService()

class PostRequest(BaseModel):
    user_id: int
    text: str

@router.post("/")
def post(req: PostRequest, db: Session = Depends(get_db)):
    try:
        m = svc.add_post(db, req.user_id, req.text)
        return {"id": m.id, "group_id": m.group_id, "user_id": m.user_id, "text": m.text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
