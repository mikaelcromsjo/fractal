from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.group_service import GroupService

router = APIRouter()
svc = GroupService()

class PostRequest(BaseModel):
    user_id: int
    text: str

@router.post("/")
def post(req: PostRequest):
    try:
        m = svc.add_post(req.user_id, req.text)
        return {"id": m.id, "group_id": m.group_id, "user_id": m.user_id, "text": m.text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
