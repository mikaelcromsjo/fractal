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
import random
from services.fractal_service_tree import build_fractal_tree

from fastapi import WebSocket, WebSocketDisconnect
import json
from typing import Dict, List


# Service imports - replace direct DB access
from services.fractal_service import (
    get_last_group_repo,
    get_proposals_for_group_repo,
    vote_representative_repo,
    rep_vote_card,
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
    vote_representative_repo,
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
        # 1️⃣ Validate Telegram WebApp data
        validate(request.init_data, settings.bot_token)
        data = parse(request.init_data)
        user = data["user"]
        print(f"✅ Telegram user: {user['id']} - {user.get('first_name', '')}")

        # 2️⃣ Fetch user context
        user_context = await get_user_info_by_telegram_id(db, str(user["id"]))
        print(f"🔍 Service response: {user_context}")

        # Extract fractal details if user is linked to one
        fractal_id = user_context.get("fractal_id")
        fractal = await get_fractal(db, fractal_id) if fractal_id else None
        round_obj = await get_last_round_repo(db, fractal_id) if fractal_id else None

        # check if user is active in curren round
        group_status = "active"
        if (not user_context.get("group_id")):
            group = get_last_group_repo(db, fractal_id)
            group_status = "observer"
 


        # 3️⃣ Construct the response (with null-safety)
        response_data = {
            "status": "ok",
            "user_id": user_context.get("user_id"),
            "fractal_id": fractal_id,
            "round_id": user_context.get("round_id"),
            "group_id": user_context.get("group_id"),
            "first_name": user.get("first_name", ""),
            "username": user.get("username", ""),
            "fractal_name": fractal.name if fractal else None,
            "fractal_description": fractal.description if fractal else None,
            "fractal_start_date": (
                fractal.start_date.strftime("%Y-%m-%d %H:%M")
                if fractal and fractal.start_date
                else None
            ),
            "fractal_round_time": (fractal.meta.get("round_time") 
                if fractal and fractal.meta and "round_time" in fractal.meta 
                else None)
            ,
            "level": getattr(round_obj, "level", None),
            "fractal_status": getattr(fractal, "status", None),
            "group_status": group_status,
        }

        print(f"📤 Sending response: {response_data}")
        return JSONResponse(content=response_data)

    except Exception as e:
        print(f"❌ Auth failed: {e}")
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
    fractal_id: int = Query(-1, description="Fractal ID"),  # ✅ Optional
    db: AsyncSession = Depends(get_db)
):
    """Load all cards in group - renders multiple proposal_card.html templates."""
    
    cards = await get_all_cards(db, group_id, user_id, fractal_id)
    
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
async def vote_comment_endpoint(payload: VoteCommentRequest, db: AsyncSession = Depends(get_db)):
    # Convert boolean to int if needed
    vote_value = payload.vote
    
    vote = await vote_comment(db, payload.comment_id, payload.voter_user_id, vote_value)
    return {"ok": True, "vote": orm_to_dict(vote)}


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

class VoteRepresentativePayload(BaseModel):
    group_id: int
    round_id: int
    voter_user_id: int
    candidate_user_id: int
    points: int


def _iter_comment_nodes(comment_nodes):
    """
    Yield every comment node (including nested replies) 
    from the given list of comment nodes.
    """
    for node in comment_nodes:
        yield node
        replies = node.get("replies", [])
        if replies:
            yield from _iter_comment_nodes(replies)


@router.post("/test/vote_all_comments")
async def test_vote_comments(
    fractal_id: int,
    score: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """
    Everyone votes `score` on all comments (and all nested replies)
    for the current round in this fractal.
    """

    score  = random.randint(-10, 10) if score == -1 else score    

    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)

    votes = 0

    for group in groups:
        members = await get_group_members(db, group.id)
        tree = await get_proposals_comments_tree(db, group.id)

        # tree: list of proposal nodes
        for pnode in tree:
            comment_nodes = pnode.get("comments", [])
            for cnode in _iter_comment_nodes(comment_nodes):
                comment = cnode["comment"]
                for member in members:
                    await vote_comment(db, comment.id, member.user_id, score)
                    votes += 1

    await db.commit()
    return {"ok": True, "total_comment_votes": votes}    

@router.post("/test/generate_representative_votes")
async def test_generate_representative_votes(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """
    For every group in the latest round, every member votes on every other member:
    - Highest user_id gets 3 points from everyone
    - Two other members get 2 and 1 point each
    """
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    votes = []
    
    for g in groups:
        members = await get_group_members(db, g.id)
        member_ids = sorted([m.user_id for m in members])  # sort by user_id
        
        if len(member_ids) < 2:
            continue
            
        # lowest gets 3 from everyone
        highest_id = member_ids[0]
        
        for voter_id in member_ids:
            # voter always gives 3 to highest
            vote = await vote_representative_repo(
                db=db,
                group_id=g.id,
                round_id=round_obj.id,
                voter_user_id=voter_id,
                candidate_user_id=highest_id,
                points=3,
            )
            votes.append(vote)
            
            # skip if voter is the highest (no additional votes needed)
            if voter_id == highest_id:
                continue
                
            # pick two other candidates randomly or by index
            other_candidates = [uid for uid in member_ids if uid != voter_id and uid != highest_id]
            if len(other_candidates) >= 2:
                c1, c2 = other_candidates[:2]  # or random.sample(other_candidates, 2)
                # 2 points to first other
                vote2 = await vote_representative_repo(
                    db=db,
                    group_id=g.id,
                    round_id=round_obj.id,
                    voter_user_id=voter_id,
                    candidate_user_id=c1,
                    points=2,
                )
                votes.append(vote2)
                # 1 point to second other
                vote3 = await vote_representative_repo(
                    db=db,
                    group_id=g.id,
                    round_id=round_obj.id,
                    voter_user_id=voter_id,
                    candidate_user_id=c2,
                    points=1,
                )
                votes.append(vote3)
    
    await db.commit()
    return {"ok": True, "votes": len(votes)}

@router.post("/vote_representative")
async def vote_representative_endpoint(
    payload: VoteRepresentativePayload,
    db: AsyncSession = Depends(get_db)
):
    data = payload.dict()
    vote = await vote_representative_repo(
        db=db,
        group_id=data["group_id"],
        round_id=data["round_id"],
        voter_user_id=data["voter_user_id"],
        candidate_user_id=data["candidate_user_id"],
        points=data["points"],
    )
    return {"ok": True, "vote": orm_to_dict(vote)}


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
            
            

# ---------- 🧪 TEST PANEL - Matches Your Simulation 100% ----------
@router.post("/test/create_fractal")
async def test_create_fractal(db: AsyncSession = Depends(get_db)):
    """Exact match to your simulation"""
    fractal = await create_fractal(
        db,
        name="Test Fractal 🧪",
        description="Simulation test fractal",
        start_date=datetime.now(timezone.utc),
        status="waiting",
        settings={"group_size": 8}  # ✅ Matches your script
    )
    await db.commit()
    return {"ok": True, "fractal_id": fractal.id}

COMMUNITY_TITLES = [
    "Neighborhood Commons Hub",
    "Regenerative Cities Network",
    "Open Source Democracy Lab",
    "Local Climate Action Circle",
    "Cooperative Housing Council",
    "Digital Rights & Privacy Forum",
    "Community Resilience Coalition",
    "Urban Gardeners Alliance",
    "Conscious Entrepreneurs Guild",
    "Citizen Assembly Sandbox",
    "Grassroots Innovation Studio",
    "Participatory Budgeting Circle",
    "Community Health & Wellness Hub",
    "Circular Economy Builders",
    "Youth Civic Engagement Lab",
    "Decentralized Governance Studio",
    "Social Impact Makers Network",
    "Neighborhood Repair Café Circle",
    "Community Learning Commons",
    "Digital Commons Stewardship Circle",
]

USERNAMES = [
    "community_weaver",
    "urban_gardener",
    "policy_hacker",
    "regen_builder",
    "consensus_crafter",
    "civic_coder",
    "grassroots_maria",
    "local_linker",
    "climate_jonas",
    "openprocess_eli",
    "circle_host_anna",
    "commoner_lina",
    "facilitation_fred",
    "systems_sara",
    "impact_mika",
    "democratic_dan",
    "cohost_kim",
    "fractal_farid",
    "neighbor_nora",
    "commons_kalle",
]

@router.post("/test/quick_start")
async def test_quick_start(num_users: int = 25, db: AsyncSession = Depends(get_db)):
    """Exact replica of your simulation Steps 1-3"""
    
    # 1. Create fractal with random title
    fractal_name = random.choice(COMMUNITY_TITLES)  # [web:17][web:23]
    fractal = await create_fractal(
        db,
        fractal_name,
        "Quick simulation",
        datetime.now(timezone.utc) + timedelta(minutes=1),
        "waiting",
        {},
    )

    # 2. Join users with randomized usernames (cycled if num_users > len list)
    users = []
    for i in range(num_users):
        username = USERNAMES[i % len(USERNAMES)]
        user_dict = {
            "username": username,
            "telegram_id": str(20000 + i),
        }
        user = await join_fractal(db, user_dict, fractal.id)
        users.append(user)

    await db.commit()
    return {"ok": True, "fractal_id": fractal.id, "users_joined": len(users)}

@router.post("/test/generate_proposals")
async def test_generate_proposals(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """Generate realistic community proposals"""
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    # Real community proposal templates
    proposal_templates = [
        {
            "title": "Weekly Community Standup Meetings",
            "body": "Let's establish a weekly 30-minute video call every Tuesday at 7pm UTC to discuss progress, blockers, and upcoming initiatives. This will help us stay aligned and build stronger relationships."
        },
        {
            "title": "Community Discord Server",
            "body": "Create a dedicated Discord server for members to collaborate in real-time, share ideas, and build our community culture. We can set up channels for announcements, general chat, project discussion, and off-topic."
        },
        {
            "title": "Monthly Newsletter",
            "body": "Start a monthly newsletter highlighting community wins, member spotlights, upcoming events, and resources. This keeps everyone informed and celebrates our collective progress."
        },
        {
            "title": "Mentorship Program",
            "body": "Pair experienced members with newcomers for structured mentorship. This accelerates onboarding, builds relationships, and creates a culture of knowledge-sharing within our community."
        },
        {
            "title": "Community Contribution Guidelines",
            "body": "Document clear guidelines for how members can contribute to community projects. Include code of conduct, contribution process, and recognition for contributors."
        },
        {
            "title": "Quarterly Hackathon Events",
            "body": "Organize quarterly 48-hour hackathons where members can collaborate on projects, learn from each other, and build something cool together. This drives innovation and engagement."
        },
        {
            "title": "Community Resource Library",
            "body": "Build a centralized wiki/documentation site with tutorials, best practices, case studies, and tools curated by community members. Make knowledge easily discoverable."
        },
        {
            "title": "Local Meetup Groups",
            "body": "Establish regional meetup groups for members in the same geographic areas. Monthly in-person gatherings strengthen bonds and create local networks within our global community."
        },
        {
            "title": "Community Swag Store",
            "body": "Create a branded merchandise store (t-shirts, mugs, stickers) where members can purchase items. This builds pride and helps promote the community externally."
        },
        {
            "title": "Ambassador Program",
            "body": "Recruit passionate community members as ambassadors to represent us at conferences, run workshops, and recruit new members. Provide training, resources, and recognition."
        },
        {
            "title": "Open Source Project Initiative",
            "body": "Start an open-source project led by the community. This gives members something tangible to build together, improves their skills, and creates lasting value."
        },
        {
            "title": "Community Podcast Series",
            "body": "Launch a monthly podcast featuring community members sharing their stories, insights, and learnings. A great way to celebrate members and attract new talent."
        },
        {
            "title": "Sponsorship & Grants Program",
            "body": "Establish a fund to sponsor community projects, events, and member development. Help fund hackathons, conferences, tools, and learning resources."
        },
        {
            "title": "Code Review & Feedback Culture",
            "body": "Formalize a peer code review process where members help each other improve. Build standards and best practices together through collaborative feedback."
        },
        {
            "title": "Community Standards & Values Document",
            "body": "Collaboratively draft a living document that outlines our community's core values, mission, and principles. This guides decisions and onboarding of new members."
        }
    ]
    
    proposals = []
    proposal_idx = 0
    
    for group in groups:
        members = await get_group_members(db, group.id)
        member_ids = [m.user_id for m in members]
        
        # Distribute proposals across group members
        for i, uid in enumerate(member_ids):
            template = proposal_templates[proposal_idx % len(proposal_templates)]
            proposal = await create_proposal(
                db, 
                fractal_id, 
                group.id, 
                round_obj.id,
                template["title"],
                template["body"],
                uid  # creator_user_id
            )
            proposals.append(proposal)
            proposal_idx += 1
    
    await db.commit()
    return {
        "ok": True, 
        "proposals_created": len(proposals),
        "groups": len(groups),
        "proposals_per_group": len(proposals) // len(groups) if groups else 0
    }

@router.post("/test/vote_all_proposals")
async def test_vote_proposals(fractal_id: int, score: int = 10, db: AsyncSession = Depends(get_db)):
    """Everyone votes max score on all proposals"""

    score  = random.randint(-10, 10) if score == -1 else score    

    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    votes = 0
    for group in groups:
        members = await get_group_members(db, group.id)
        tree = await get_proposals_comments_tree(db, group.id)
        for node in tree:  # each node is a dict wrapping the proposal and metadata
            proposal = node["proposal"]
            for member in members:
                await vote_proposal(db, proposal.id, member.user_id, score)
                votes += 1    
    await db.commit()
    return {"ok": True, "total_votes": votes}

@router.post("/test/generate_representative_votes")
async def test_rep_votes(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """Updated for NEW 3-2-1 points system"""
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    for group in groups:
        members = await get_group_members(db, group.id)
        if len(members) < 2: continue
            
        candidate = members[0].user_id  # First as candidate
        for member in members[1:]:  # Everyone else votes
            await vote_representative_repo(
                db, group.id, round_obj.id, 
                member.user_id, candidate, 3  # Gold vote (3 points)
            )
    
    await db.commit()
    return {"ok": True, "rep_votes": "generated"}


@router.post("/test/generate_comments")
async def test_generate_comments(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """
    Generate realistic feedback comments on proposals from all group members.
    """
    round_obj = await get_last_round_repo(db, fractal_id)
    groups = await get_groups_for_round(db, round_obj.id)
    
    # Realistic feedback templates for community proposals
    comment_templates = [
        "Love this idea! It would really help us stay connected and aligned as a community.",
        "Great initiative. I'd suggest we start with a pilot group to test the concept before full rollout.",
        "This is important. We need clear structure and guidelines to make this sustainable long-term.",
        "I'm interested in helping lead this effort. Let me know if you need volunteers!",
        "Good proposal, but we should consider budget/resources needed. How would we fund this?",
        "This aligns perfectly with our community values. I'm excited to see this happen.",
        "Have you thought about how this would scale as we grow? We should plan ahead.",
        "I've seen similar initiatives work well in other communities. Happy to share best practices.",
        "This solves a real problem I've been experiencing. Count me in!",
        "The timing is perfect for this. We've been discussing this need for a while now.",
        "I'd like to see more details on implementation. What would the first steps be?",
        "Fantastic idea. This will definitely increase engagement and retention in our community.",
        "I have some concerns about [aspect], but the overall direction is solid.",
        "Let's make sure we include perspectives from newer members in the planning phase.",
        "This could be a great way to attract talent from outside our immediate network.",
        "I propose we create a working group to flesh out the details and timeline.",
        "Strong proposal. I'd recommend we gather more feedback from the broader community first.",
        "This is exactly what we need right now. Let's prioritize it!",
        "I'm curious about the expected ROI and how we'd measure success for this.",
        "Great thinking. I'd suggest we start small and iterate based on feedback."
    ]
    
    comments = []
    comment_idx = 0
    
    for g in groups:
        members = await get_group_members(db, g.id)
        member_ids = [m.user_id for m in members]
        
        proposals = await get_proposals_for_group_repo(db, g.id)
        
        for p in proposals:
            # Each member comments on each proposal (excluding the creator)
            for commenter_id in member_ids:
                # Skip if commenter is the proposal creator
                if commenter_id == p.creator_user_id:
                    continue
                
                template = comment_templates[comment_idx % len(comment_templates)]
                c = await create_comment(
                    db=db,
                    proposal_id=p.id,
                    user_id=commenter_id,
                    text=template,
                    parent_comment_id=None,
                    group_id=g.id,
                )
                comments.append(c)
                comment_idx += 1
    
    await db.commit()
    return {
        "ok": True,
        "comments_created": len(comments),
        "groups": len(groups)
    }

@router.post("/test/full_simulation")
async def test_full_simulation(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """Exact replica of your entire simulation"""
        
    print("🧪 3/9 Start fractal")
    round0 = await start_fractal(db, fractal_id)
    
    print("🧪 4/9 Generate proposals")
    await test_generate_proposals(fractal_id, db)

    print("🧪 4/9 Generate comments")
    await test_generate_comments(fractal_id, db)

    print("🧪 5/9 Vote proposals")
    await test_vote_proposals(fractal_id, score=-1, db=db)

    print("🧪 5/9 Vote comment")
    await test_vote_comments(fractal_id, score=-1, db=db)

    print("🧪 6/9 Representative votes")
    await test_rep_votes(fractal_id, db)
    
    print("🧪 8/9 Commit")
    await db.commit()
    
#    print("🧪 9/9 Done!")
    return {"fractal_id": fractal_id, "round_id": round0.id}

@router.get("/test/status/{fractal_id}")
async def test_status(fractal_id: int, db: AsyncSession = Depends(get_db)):
    """Quick status - matches your print_proposals_comments_tree"""
    fractal = await get_fractal(db, fractal_id)
    round_obj = await get_last_round_repo(db, fractal_id)
    
    if not round_obj:
        return {"status": "no_active_round"}
    
    groups = await get_groups_for_round(db, round_obj.id)
    stats = []
    for group in groups:
        tree = await get_proposals_comments_tree(db, group.id)
        stats.append({
            "group_id": group.id,
            "proposals": len(tree),
            "members": len(await get_group_members(db, group.id))
        })
    
    reps = {}
    for group in groups:
        reps[group.id] = await get_representatives_for_group_repo(db, group.id, round_obj.id)
    
    return {
        "fractal": fractal.id,
        "round": round_obj.id,
        "groups": stats,
        "representatives": reps
    }


@router.post("/debug/comment-votes")
async def debug_votes(group_id: int, db: AsyncSession = Depends(get_db)):
    votes = await get_votes_for_group_comments_repo(db, group_id)
    return {
        "total_votes": len(votes),
        "comment_ids_with_votes": [v.comment_id for v in votes],
        "unique_comments": len(set(v.comment_id for v in votes))
    }

import subprocess
from fastapi import APIRouter, HTTPException

    
@router.get("/rep_vote_card/{group_id}")
async def get_rep_vote_card(
    group_id: int,
    user_id: int,
    fractal_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Builds and returns the representative vote card HTML for a given group and user.
    """
    html = await rep_vote_card(db, user_id=user_id, group_id=group_id, fractal_id=fractal_id)
    return {"ok": True, "html": html}
