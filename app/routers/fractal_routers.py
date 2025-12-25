# app/routers/fractal_routers.py
from typing import Any, Dict, List, Optional
from datetime import datetime
from jose import jwt, JWTError
from datetime import datetime, timedelta
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional
from config.settings import settings
from mako.lookup import TemplateLookup
from infrastructure.db.session import get_async_session as get_db
from infrastructure.models import RoundTree
from datetime import datetime, timezone

from services.fractal_service_tree import build_fractal_tree

from fastapi import WebSocket, WebSocketDisconnect
import json
from typing import Dict, List


# Service imports - replace direct DB access
from services.fractal_service import (
    create_fractal,
    create_user,
    join_fractal,
    start_fractal,
    start_round,
    get_groups_for_round,
    close_round,
    promote_to_next_round,
    create_proposal,
    create_comment,
    vote_proposal,
    vote_comment,
    get_proposals_comments_tree,
    get_proposal_comments_tree,
    get_representatives_for_group_repo,
    vote_representative,
    get_group_members,
    get_fractal,
    get_user,
    get_user_info_by_telegram_id,
    get_next_card,
    get_all_cards,
    get_or_build_round_tree_repo,
    get_last_round_repo,
    calculate_rep_results
)

from telegram.bot import process_update
from telegram_init_data import validate, parse

JWT_SECRET_KEY = "a-supersecret-jwt-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1600

from states import connected_clients

router = APIRouter()

# ---------- Permissive request schemas ----------
class AnyDictModel(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

class CreateFractalRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    start_date: Optional[datetime] = None
    status: Optional[str] = "waiting"
    settings: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

class CreateUserRequest(BaseModel):
    username: Optional[str] = None
    telegram_id: Optional[str] = None
    other_id: Optional[str] = None
    prefs: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

class VoteProposalRequest(BaseModel):
    proposal_id: int
    voter_user_id: int
    score: int

    class Config:
        extra = "forbid"

class VoteCommentRequest(BaseModel):
    comment_id: int
    voter_user_id: int
    vote: int

    class Config:
        extra = "forbid"

class CreateProposalRequest(BaseModel):
    fractal_id: int
    group_id: int
    round_id: int
    title: str
    body: Optional[str] = ""
    creator_user_id: int
    type: Optional[str] = "base"
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

class CreateCommentRequest(BaseModel):
    proposal_id: int
    parent_comment_id: Optional[int] = None
    user_id: int
    group_id: int
    text: str

    class Config:
        extra = "allow"

# ---------- Utility functions ----------
def _json_safe(value: Any) -> Any:
    """Convert non-JSON-serializable values into safe primitives."""
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value) if hasattr(value, '__str__') else value

def orm_to_dict(instance) -> Dict[str, Any]:
    """Safe serializer for SQLAlchemy ORM objects."""
    if instance is None:
        return {}
    if hasattr(instance, "to_dict"):
        raw = instance.to_dict()
        return {k: _json_safe(v) for k, v in raw.items()}
    if hasattr(instance, "__dict__"):
        raw = instance.__dict__
        return {k: _json_safe(v) for k, v in raw.items() if not k.startswith("_")}
    return {}

class AuthResponse(BaseModel):
    status: str
    user_id: int  # internal user ID
    fractal_id: Optional[int] = None
    round_id: Optional[int] = None
    group_id: Optional[int] = None
    first_name: str
    username: str

class AuthRequest(BaseModel):
    init_data: str

# ---------- Telegram Webhook & Auth ----------
@router.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != settings.bot_token:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    data = await request.json()
    await process_update(data)    
    # Telegram expects EMPTY 200 response
    return Response(status_code=200)  # or PlainTextResponse("OK")

@router.post("/auth")
async def fractals_auth(request: AuthRequest, db: AsyncSession = Depends(get_db)):
    try:
        validate(request.init_data, settings.bot_token)
        data = parse(request.init_data)
        user = data["user"]
        
        user_context = await get_user_info_by_telegram_id(db, str(user["id"]))
        
        # Safe response
        return {
            "status": "ok",
            "user_id": int(user_context.get("user_id") or 0),
            "fractal_id": int(user_context.get("fractal_id") or 0),
            "round_id": int(user_context.get("round_id") or 0),
            "group_id": int(user_context.get("group_id") or 0),
            "first_name": user.get("first_name", ""),
            "username": user.get("username", "")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
# ---------- HTML Endpoints ----------
templates = TemplateLookup(
    directories=["templates"],
    input_encoding="utf-8",
    output_encoding="utf-8",
    default_filters=["decode.utf8"]
)

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    template = templates.get_template("dashboard.html")
    html = template.render(request=request, default_name="Guest", settings=settings)
    return HTMLResponse(html)

@router.get("/get_next_card")
async def get_next_card_router(
    request: Request,
    group_id: int = Query(..., description="Current group ID"),
    user_id: int = Query(..., description="Current user ID"),
    db: AsyncSession = Depends(get_db)
):
    """Load next unvoted card - EXACTLY matches proposal_card.html."""
    
    card = await get_next_card(db, group_id, user_id)
    
    if not card:
#        template = templates.get_template("no_cards.html")
#        response = HTMLResponse(template.render(request=request))
        response = HTMLResponse()
        response.headers["HX-Trigger"] = "noMoreCards"
        return response
     
    # Static user/reply for template (current user)
    avatar_id = (user_id % 16) + 1
    current_user = {
        "id": user_id,
        "username": "You",  # Or fetch real username
        "avatar": "/static/img/64_" + str(avatar_id) + ".png"
    }
    
    # ✅ Pass card as 'proposal' - template works unchanged!
    template = templates.get_template("proposal_card.html")
    
    html_content = template.render(
        request=request, 
        user=current_user, 
        proposal=card  # ✅ Perfect match!
    )
    
    return HTMLResponse(content=html_content)


@router.get("/get_all_cards")
async def get_all_cards_router(
    request: Request,
    group_id: int = Query(..., description="Current group ID"),
    user_id: int = Query(..., description="Current user ID"),
    db: AsyncSession = Depends(get_db)
):
    """Load all cards in group - renders multiple proposal_card.html templates."""
    
    cards = await get_all_cards(db, group_id, user_id)
    
    if not cards:
#        template = templates.get_template("no_cards.html")
#        html = template.render_unicode(request=request)  # ✅ render_unicode()
#        response = HTMLResponse(html)
        response = HTMLResponse()
        response.headers["HX-Trigger"] = "noCards"
        return response
    
    avatar_id = (user_id % 16) + 1
    current_user = {
        "id": user_id,
        "username": "You",
        "avatar": f"/static/img/64_{avatar_id}.png"
    }
    
    template = templates.get_template("proposal_card.html")
    
    combined_html = "".join([
        template.render_unicode(  # ✅ render_unicode() returns str
            request=request,
            user=current_user,
            proposal=card,
            number_comments = 1,
            current_group_id = group_id
        )
        for card in cards
    ])
    
    return HTMLResponse(content=combined_html)


# ---------- Service-backed API Endpoints ----------
@router.post("/create_fractal")
async def create_fractal_endpoint(
    payload: CreateFractalRequest, 
    db: AsyncSession = Depends(get_db)
):
    fractal = await create_fractal(
        db,
        payload.name,
        payload.description or "",
        payload.start_date or datetime.now(),
        payload.status,
        payload.settings  # meta optional ✅
    )
    return JSONResponse(content={"ok": True, "fractal": orm_to_dict(fractal)})  # ✅ Original

@router.get("/get_group_members/{group_id}")
async def get_group_members_endpoint(
    group_id: int, 
    db: AsyncSession = Depends(get_db)
):
    members = await get_group_members(db, group_id)
    return JSONResponse(content={"ok": True, "members": [orm_to_dict(m) for m in members]})

@router.post("/create_user")
async def create_user_endpoint(
    payload: CreateUserRequest, 
    db: AsyncSession = Depends(get_db)
):
    user_info = payload.model_dump(exclude_unset=True)
    user = await create_user(db, user_info)
    return JSONResponse(content={"ok": True, "user": orm_to_dict(user)})

@router.post("/join_fractal")
async def join_fractal_endpoint(
    payload: AnyDictModel, 
    db: AsyncSession = Depends(get_db)
):
    data = payload.data
    user_id = data.get("user_id")
    fractal_id = data.get("fractal_id")
    role = data.get("role", "member")
    
    if not user_id or not fractal_id:
        raise HTTPException(status_code=400, detail="user_id and fractal_id required")
    
    user = await join_fractal(db, {"id": user_id}, fractal_id)
    return JSONResponse(content={"ok": True, "user": orm_to_dict(user)})

@router.post("/start_fractal/{fractal_id}")
async def start_fractal_endpoint(
    fractal_id: int, 
    db: AsyncSession = Depends(get_db)
):
    round_obj = await start_fractal(db, fractal_id)
    return JSONResponse(content={"ok": True, "round": orm_to_dict(round_obj)})

@router.post("/start_round")
async def start_round_endpoint(
    payload: AnyDictModel, 
    db: AsyncSession = Depends(get_db)
):
    data = payload.data
    fractal_id = data.get("fractal_id")
    level = int(data.get("level", 0))
    members = data.get("members", [])
    
    if not fractal_id:
        raise HTTPException(status_code=400, detail="fractal_id required")
    
    round_obj = await start_round(db, fractal_id, level, members)
    return JSONResponse(content={"ok": True, "round": orm_to_dict(round_obj)})

@router.get("/get_groups_for_round/{round_id}")
async def get_groups_for_round_endpoint(
    round_id: int, 
    db: AsyncSession = Depends(get_db)
):
    groups = await get_groups_for_round(db, round_id)
    return JSONResponse(content={"ok": True, "groups": [orm_to_dict(g) for g in groups]})

@router.post("/close_round/{fractal_id}")
async def close_round_endpoint(
    fractal_id: int, 
    db: AsyncSession = Depends(get_db)
):
    result = await close_round(db, fractal_id)
    return JSONResponse(content={"ok": True, "result": orm_to_dict(result)})

@router.post("/promote_to_next_round")
async def promote_to_next_round_endpoint(
    payload: AnyDictModel, 
    db: AsyncSession = Depends(get_db)
):
    data = payload.data
    prev_round_id = data.get("prev_round_id")
    fractal_id = data.get("fractal_id")
    
    if prev_round_id is None or fractal_id is None:
        raise HTTPException(status_code=400, detail="prev_round_id and fractal_id required")
    
    new_round = await promote_to_next_round(db, prev_round_id, fractal_id)
    return JSONResponse(content={"ok": True, "new_round": orm_to_dict(new_round) if new_round else None})

@router.post("/create_proposal")
async def create_proposal_endpoint(
    payload: CreateProposalRequest, 
    db: AsyncSession = Depends(get_db)
):
    proposal = await create_proposal(
        db,
        payload.fractal_id,
        payload.group_id,
        payload.round_id,
        payload.title,
        payload.body,
        payload.creator_user_id
    )
    return JSONResponse(content={"ok": True, "proposal": orm_to_dict(proposal)})

@router.post("/create_comment")
async def create_comment_endpoint(
    payload: CreateCommentRequest, 
    db: AsyncSession = Depends(get_db)
):
    comment = await create_comment(
        db,
        payload.proposal_id,
        payload.user_id,
        payload.text,
        payload.parent_comment_id,
        payload.group_id,
    )
    return JSONResponse(content={"ok": True, "comment": orm_to_dict(comment)})

@router.post("/vote_proposal")
async def vote_proposal_endpoint(
    payload: VoteProposalRequest, 
    db: AsyncSession = Depends(get_db)
):
    
    import os
    print(f"[PID {os.getpid()}]")

    vote = await vote_proposal(
        db,
        payload.proposal_id,
        payload.voter_user_id,
        payload.score
    )
    return JSONResponse(content={"ok": True, "vote": orm_to_dict(vote)})

@router.post("/vote_comment")
async def vote_comment_endpoint(
    payload: VoteCommentRequest, 
    db: AsyncSession = Depends(get_db)
):
    vote = await vote_comment(
        db,
        payload.comment_id,
        payload.voter_user_id,
        payload.vote
    )
    return JSONResponse(content={"ok": True, "vote": orm_to_dict(vote)})

@router.get("/get_proposals_comments_tree/{group_id}")
async def get_proposals_comments_tree_endpoint(
    group_id: int, 
    db: AsyncSession = Depends(get_db)
):
    tree = await get_proposals_comments_tree(db, group_id)
    return JSONResponse(content={"ok": True, "proposals": tree})

@router.get("/get_proposal_comments_tree/{proposal_id}")
async def get_proposal_comments_tree_endpoint(
    proposal_id: int, 
    db: AsyncSession = Depends(get_db)
):
    tree = await get_proposal_comments_tree(db, proposal_id)
    return JSONResponse(content={"ok": True, "comments_tree": tree})

@router.post("/get_representatives_for_group/{group_id}")
async def select_representative_endpoint(
    group_id: int, 
    db: AsyncSession = Depends(get_db)
):
    selection = await get_representatives_for_group_repo(db, group_id)
    return JSONResponse(content={"ok": True, "selection": orm_to_dict(selection)})

#@router.post("/vote_representative")
#async def vote_representative_endpoint(
#    payload: AnyDictModel, 
#    db: AsyncSession = Depends(get_db)
#):
#    data = payload.data
#    group_id = data.get("group_id")
#    voter_user_id = data.get("voter_user_id")
#    candidate_user_id = data.get("candidate_user_id")
    
#    if not all([group_id, voter_user_id, candidate_user_id]):
#        raise HTTPException(status_code=400, detail="group_id, voter_user_id and candidate_user_id required")
    
#    vote = await vote_representative(db, group_id, voter_user_id, candidate_user_id)
#    return JSONResponse(content={"ok": True, "vote": orm_to_dict(vote)})


@router.post("/vote_representative")
async def vote_representative_endpoint(
    group_id: int = Query(...),
    round_id: int = Query(...),
    voter_id: int = Query(...),
    candidate_id: int = Query(...),
    points: int = Query(..., ge=1, le=3),
    db: AsyncSession = Depends(get_db)
):
    """Fixed: Query params + validation"""
    vote = await vote_representative(db, group_id, round_id, voter_id, candidate_id, points)
    return {"status": "ok", "vote": orm_to_dict(vote)}

@router.get("/rep_results/{group_id}/{round_id}")
async def get_rep_results(group_id: int, round_id: int, db: AsyncSession = Depends(get_db)):
    results = await calculate_rep_results(db, group_id, round_id)
    return {"results": results}

# ---------- Convenience endpoints ----------
@router.get("/fractal/{fractal_id}")
async def get_fractal_endpoint(
    fractal_id: int, 
    db: AsyncSession = Depends(get_db)
):
    fractal = await get_fractal(db, fractal_id)
    if not fractal:
        raise HTTPException(status_code=404, detail="Fractal not found")
    return JSONResponse(content={"ok": True, "fractal": orm_to_dict(fractal)})

@router.get("/user/{user_id}")
async def get_user_endpoint(
    user_id: int, 
    db: AsyncSession = Depends(get_db)
):
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return JSONResponse(content={"ok": True, "user": orm_to_dict(user)})


@router.get("/{fractal_id}/tree")
async def get_fractal_tree(
    fractal_id: int,
    round_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    tree = await get_or_build_round_tree_repo(db, fractal_id=fractal_id, round_id=round_id)
    if not tree.get("rounds"):
        raise HTTPException(status_code=404, detail="No rounds found")
    return tree

@router.get("/get-ws-token")
def get_ws_token(request: Request, user_id: str):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode({"sub": user_id, "exp": expire}, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return {"ws_token": token}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    
    try:
        await websocket.accept()
    except Exception:
        return
    
    if not token:
        await websocket.close(code=1008)
        return
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except Exception:
        await websocket.close(code=1008)
        return
    
    # ADD CLIENT ✅ (your code is correct here)
    if user_id not in connected_clients:
        connected_clients[user_id] = []
    connected_clients[user_id].append(websocket)
    
    print("=== CLIENT CONNECTED ===")
    print(f"User {user_id} added: {len(connected_clients[user_id])} connections")
    
    # Send welcome message
    event = {"type": "info", "message": "Hello from server! Connection established."}
    await websocket.send_json(event)
    
    # FIXED: Proper disconnect handling
    try:
        while True:
            data = await websocket.receive_text()  # This is correct
            print("📨 Message received:", repr(data))
            
    except WebSocketDisconnect:
        print(f"👋 User {user_id} DISCONNECTED")
    except Exception as e:
        print(f"❌ WS error {user_id}: {e}")
    finally:
        # CLEANUP (your code is correct)
        if user_id in connected_clients and websocket in connected_clients[user_id]:
            connected_clients[user_id].remove(websocket)
            print(f"✅ Removed WS for user {user_id}. Remaining: {len(connected_clients[user_id])}")
            if not connected_clients[user_id]:
                del connected_clients[user_id]
            
            


class TestUser(BaseModel):
    username: str
    telegram_id: Optional[str] = None

@router.post("/test/create_users")
async def test_create_users(num_users: int = 8, db: AsyncSession = Depends(get_db)):
    """Create N test users"""
    users = []
    for i in range(1, num_users + 1):
        user_info = {
            "username": f"TestUser{i}",
            "telegram_id": f"test_user_{i}",
            "other_id": f"test_{i}"
        }
        user = await create_user(db, user_info)  # ✅ Matches your signature
        users.append(orm_to_dict(user))
    await db.commit()
    return {"ok": True, "users": users, "count": len(users)}

@router.post("/test/create_fractal")
async def test_create_fractal(db: AsyncSession = Depends(get_db)):
    """Create test fractal with meta"""
    default_meta = {
        "group_size": 8,
        "proposals_per_user": 3
    }
    fractal = await create_fractal(
        db, 
        "Test Fractal 🧪", 
        "Auto-generated for testing",
        datetime.now(timezone.utc),
        "waiting",
        meta=default_meta  # ✅ Optional meta as you confirmed
    )
    await db.commit()
    return {"ok": True, "fractal_id": fractal.id, "fractal": orm_to_dict(fractal)}

@router.post("/test/join_fractal")
async def test_join_fractal(
    fractal_id: int, 
    num_users: int = 8, 
    db: AsyncSession = Depends(get_db)
):
    """Create + join N users to fractal"""
    users = []
    for i in range(num_users):
        # Create user
        user_info = {"username": f"User{i+1}", "telegram_id": f"test{i+1}"}
        user = await create_user(db, user_info)
        
        # Join fractal
        joined_user = await join_fractal(db, {"id": user.id}, fractal_id)
        users.append({
            "user_id": user.id,
            "group_id": joined_user.group_id
        })
    
    await db.commit()
    return {"ok": True, "fractal_id": fractal_id, "joins": users}

@router.post("/test/start_fractal/{fractal_id}")
async def test_start_fractal(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """Start fractal + first round"""
    round_obj = await start_fractal(db, fractal_id)  # ✅ Your signature
    groups = await get_groups_for_round(db, round_obj.id)
    await db.commit()
    return {
        "ok": True, 
        "round_id": round_obj.id,
        "groups": len(groups),
        "group_ids": [g.id for g in groups]
    }

@router.post("/test/generate_proposals")
async def test_generate_proposals(
    fractal_id: int, 
    proposals_per_group: int = 3, 
    db: AsyncSession = Depends(get_db)
):
    """Generate proposals across all groups"""
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    proposals = []
    for group in groups:
        members = await get_group_members(db, group.id)
        for i in range(min(proposals_per_group, len(members))):
            member = members[i]
            proposal = await create_proposal(
                db, fractal_id, group.id, round_obj.id,
                f"Proposal {i+1}", f"Test proposal content {i+1}",
                member.user_id
            )
            proposals.append(orm_to_dict(proposal))
    
    await db.commit()
    return {"ok": True, "proposals_created": len(proposals), "proposals": proposals}

@router.post("/test/generate_comments")
async def test_generate_comments(
    fractal_id: int, 
    comments_per_proposal: int = 2, 
    db: AsyncSession = Depends(get_db)
):
    """Add comments + votes to existing proposals"""
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    comments = []
    for group in groups:
        tree = await get_proposals_comments_tree(db, group.id)
        for proposal in tree[:comments_per_proposal]:
            members = await get_group_members(db, group.id)
            for i, member in enumerate(members[:comments_per_proposal]):
                comment = await create_comment(
                    db, proposal["id"], member.user_id,
                    f"Comment {i+1} on proposal {proposal['title'][:20]}...",
                    None, group.id
                )
                # Vote on comment
                await vote_comment(db, comment.id, member.user_id, 2)
                comments.append(orm_to_dict(comment))
    
    await db.commit()
    return {"ok": True, "comments_created": len(comments)}

@router.post("/test/generate_votes")
async def test_generate_votes(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """Generate proposal + rep votes"""
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    for group in groups:
        members = await get_group_members(db, group.id)
        tree = await get_proposals_comments_tree(db, group.id)
        
        # Vote proposals
        for proposal in tree:
            for member in members[:3]:
                await vote_proposal(db, proposal["id"], member.user_id, 5)
        
        # Vote representatives (3,2,1 points)
        for i, member in enumerate(members[:8]):  # 8 users max
            candidates = [m.user_id for m in members if m.user_id != member.user_id]
            for points in [3, 2, 1]:  # Gold, Silver, Bronze
                candidate = candidates[i % len(candidates)]
                await vote_representative(db, group.id, round_obj.id, 
                                        member.user_id, candidate, points)
    
    await db.commit()
    return {"ok": True, "votes_generated": True}

@router.post("/test/full_simulation")
async def test_full_simulation(num_users: int = 8, db: AsyncSession = Depends(get_db)):
    """Complete test flow"""
    print("🧪 1. Creating fractal...")
    fractal = await create_fractal(db, "Test Fractal", "Simulation", 
                                 datetime.now(timezone.utc), "waiting", {})
    
    print("🧪 2. Creating/joining users...")
    await test_join_fractal(fractal.id, num_users, db)
    
    print("🧪 3. Starting fractal...")
    await test_start_fractal(fractal.id, db)
    
    print("🧪 4. Generating proposals...")
    await test_generate_proposals(fractal.id, 3, db)
    
    print("🧪 5. Generating comments...")
    await test_generate_comments(fractal.id, 2, db)
    
    print("🧪 6. Generating votes...")
    await test_generate_votes(fractal.id, db)
    
    await db.commit()
    
    return {
        "ok": True,
        "fractal_id": fractal.id,
        "summary": "Full simulation complete! Check /test/status/{fractal_id}"
    }

@router.get("/test/status/{fractal_id}")
async def test_status(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """Fractal test status"""
    fractal = await get_fractal(db, fractal_id)
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id) if round_obj else []
    
    stats = {"groups": [], "total_proposals": 0}
    for group in groups:
        members = await get_group_members(db, group.id)
        tree = await get_proposals_comments_tree(db, group.id)
        stats["groups"].append({
            "group_id": group.id,
            "members": len(members),
            "proposals": len(tree)
        })
        stats["total_proposals"] += len(tree)
    
    return {
        "fractal": orm_to_dict(fractal),
        "round": orm_to_dict(round_obj) if round_obj else None,
        **stats
    }

