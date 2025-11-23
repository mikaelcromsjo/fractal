"""
Mock Telegram CLI with 128 AI users for testing Fractal Governance.

- Supports manual and automated round simulation.
- Proper command parsing with space-separated parameters (commas allowed inside quotes).
- Prints detailed error messages and example input instructions.


/create_fractal <name> <description> <start_date>
/list_open
/join_open
/simulate_ai
/close_round
/todo
/status
/exit

"""

from datetime import datetime, timedelta, timezone
import requests
import random
import time
from faker import Faker
import shlex

# --- Globals ---
API_URL = "http://localhost:8030/api/v1"
USERS = {}
FAKE = Faker()
CURRENT_FRACTAL = None
PROPOSALS_PER_USER = 2  # Adjust as needed
PLATFORM = "ai"  # default platform for CLI AI users
DEBUG = True  # default platform for CLI AI users
NR_USERS = 10  # default platform for CLI AI users
RAND = .2 # 1 100%

# Initialize AI users
for i in range(1, NR_USERS):
    USERS[i] = {"name": FAKE.name()}

# ----------------- Helper -----------------

def list_open_fractals():
    try:
        fractals = api_get("/fractals/")  # already returns list
        open_fractals = [f for f in fractals if f.get("status", "waiting") == "waiting"]
        if not open_fractals:
            print("[INFO] No open fractals found")
            return []
        print("Open fractals:")
        for f in open_fractals:
            print(f"  ID: {f['id']}, Name: {f['name']}, Start Date: {f['start_date']}")
        return open_fractals
    except Exception as e:
        print(f"[ERROR] Failed to list open fractals: {e}")
        return []
    
def get_group_id(user_id):
    if not CURRENT_FRACTAL:
        print("[ERROR] No fractal started")
        return None

    res = api_get(f"/fractals/{CURRENT_FRACTAL}/members/{user_id}")

    if not res:
        print(f"[ERROR] No response when fetching group for user {user_id}")
        return None

    if not res.get("ok"):
        print(f"[WARN] Failed to fetch member info for user {user_id}: {res}")
        return None

    group_id = res.get("group_id")
    if group_id is None:
        print(f"[WARN] User {user_id} has no group assigned: {res}")
        return None

    return group_id


# --- Join open fractal ---
def join_open(fractal_id):
    global CURRENT_FRACTAL
    print(f"Joining fractal {fractal_id} with all AI users...")
    for uid, user in USERS.items():
        res = api_post(f"/fractals/{fractal_id}/join", {
            "username": user["name"],
            "is_ai": True,
            "other_id": f"ai_{uid}"  # unique identifier for AI users
        })
        if res.get("ok"):
            print(f"User {uid} joined fractal {fractal_id}: {res}")
        else:
            print(f"[ERROR] User {uid} failed to join fractal {fractal_id}: {res}")
    CURRENT_FRACTAL = fractal_id
    print(f"[INFO] Current fractal set to {CURRENT_FRACTAL}")
    
def select_fractal(fractal_id):
    global CURRENT_FRACTAL
    CURRENT_FRACTAL = fractal_id
    print(f"Selected fractal {fractal_id} as CURRENT_FRACTAL")

def api_get(path, params=None):
    url = f"{API_URL}{path}"
    try:
        if DEBUG: print(f"[DEBUG] GET {url} params: {params}")
        r = requests.get(url, params=params)
        r.raise_for_status()
        res_json = r.json()
        if DEBUG: print(f"[DEBUG] Response: {res_json}")
        return res_json
    except requests.RequestException as e:
        print(f"[ERROR] API GET call {url} failed: {e}")
        try:
            if DEBUG: print(f"[DEBUG] Response text: {r.text}")
        except:
            pass
        return {}

def api_post(path, payload):
    url = f"{API_URL}{path}"
    try:
        if DEBUG: print(f"[DEBUG] POST {url} payload: {payload}")  # debug print before request
        r = requests.post(url, json=payload)
        r.raise_for_status()
        res_json = r.json()
        if DEBUG: print(f"[DEBUG] Response: {res_json}")  # optional: see success response
        return res_json
    except requests.RequestException as e:
        print(f"[ERROR] API call {url} failed: {e}")
        if DEBUG: print(f"[DEBUG] Payload was: {payload}")
        try:
            # Print the response body for more info
            if DEBUG: print(f"[DEBUG] Response text: {r.text}")
        except:
            print("[DEBUG] No response text available")
        return {}
    except ValueError as ve:
        # JSON decode error
        print(f"[ERROR] Failed to decode JSON response: {ve}")
        if DEBUG: print(f"[DEBUG] Response text: {r.text}")
        return {}
    
# ----------------- Fractal Commands -----------------
def create_fractal(user_id, name, description, start_date=None):
    global CURRENT_FRACTAL
    try:        
        if start_date is None:
            start_date = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        res = api_post("/fractals/", {
            "name": name,
            "description": description,
            "start_date": start_date,
            "settings": {}
        })
        CURRENT_FRACTAL = res.get("id")
        if not CURRENT_FRACTAL:
            print("[ERROR] Failed to start fractal: no ID returned")
        else:
            print(f"Fractal created: {res}")
    except Exception as e:
        print(f"[ERROR] Failed to create fractal: {e}")
        print("Example: /create_fractal 'My Fractal' 'Description' '2025-12-01T12:00:00'")

def join_fractal(user_id):
    if not CURRENT_FRACTAL:
        print("[ERROR] No fractal created yet")
        return
    try:
        res = api_post(f"/fractals/{CURRENT_FRACTAL}/join", {"user_id": user_id})
        print(f"User {user_id} joined fractal: {res}")
    except Exception as e:
        print(f"[ERROR] Failed to join fractal: {e}")
        print("Example: join_fractal(1)")

def create_proposal(user_id, title, body=""):
    if not CURRENT_FRACTAL:
        print("[ERROR] No fractal started")
        return None
    try:
        res = api_post("/proposals/", {
            "creator_user_id": user_id,
            "title": title,
            "body": body
        })
        print("Proposal created:", res)
        return res
    except Exception as e:
        print(f"[ERROR] Failed to create proposal: {e}")
        print("Example: create_proposal(1, 'Proposal title', 'Proposal body')")
        return None

def create_comment(user_id, proposal_id, text, parent_id=None):
    try:
        res = api_post("/comments/", {
            "proposal_id": proposal_id,
            "user_id": user_id,
            "text": text,
            "parent_comment_id": parent_id
        })
        cid = res.get("id")
        if cid:
            print(f"[INFO] Comment created: {cid}")
        return res
    except Exception as e:
        print(f"[ERROR] Failed to create comment: {e}")
        return None
    
def vote_proposal(user_id, proposal_id, score):
    try:
        api_post(f"/votes/proposal", {"user_id": user_id, "proposal_id": proposal_id, "score": score})
        print(f"User {user_id} voted {score} on proposal {proposal_id}")
    except Exception as e:
        print(f"[ERROR] Failed to vote proposal: {e}")
        print("Example: vote_proposal(1, 42, 5)")

def vote_comment(user_id, comment_id, vote):
    try:
        api_post(f"/votes/comment", {"user_id": user_id, "comment_id": comment_id, "vote": vote})
        print(f"User {user_id} voted {vote} on comment {comment_id}")
    except Exception as e:
        print(f"[ERROR] Failed to vote comment: {e}")
        print("Example: vote_comment(1, 99, True)")

def show_todo(user_id):
    try:
        res = api_get(f"/users/{user_id}/todo")
        print(f"TODO for user {user_id}: {res}")
    except Exception as e:
        print(f"[ERROR] Failed to get TODO: {e}")

def show_status():
    if not CURRENT_FRACTAL:
        print("[ERROR] No fractal started yet")
        return
    try:
        res = api_get(f"/fractals/{CURRENT_FRACTAL}/status")
        print(f"Current fractal status: {res}")
    except Exception as e:
        print(f"[ERROR] Failed to get status: {e}")

def close_round():
    if not CURRENT_FRACTAL:
        print("[ERROR] No fractal started")
        return
    try:
        res = api_post(f"/fractals/{CURRENT_FRACTAL}/close_round", {})
        print(f"Round closed: {res}")
    except Exception as e:
        print(f"[ERROR] Failed to close round: {e}")


# ----------------- AI Simulation -----------------
def simulate_ai_round():
    if not CURRENT_FRACTAL:
        print("[ERROR] No fractal started")
        return

    print("=== Simulating AI users round ===")

    all_proposals = []
    # --- Step 1: Create proposals for each user in their group ---
    for user_id in USERS:
        for p in range(PROPOSALS_PER_USER):
            if random.random() < 1:
                res = create_proposal(user_id, f"AI Proposal {user_id}-{p}", "Random description")
                if res:
                    prop_id = res.get("proposal_id") or res.get("id")
                    if prop_id:
                        all_proposals.append({"id": prop_id, "owner": user_id})

    print(f"[INFO] {len(all_proposals)} proposals created by AI users")

    # --- Preload group IDs once ---
    group_cache = {uid: get_group_id(uid) for uid in USERS}

    # --- Step 2: Create comments (only within the same group as proposal owner) ---
    all_comments = []

    for proposal in all_proposals:
        prop_id = proposal["id"]
        owner_id = proposal["owner"]
        owner_group_id = group_cache[owner_id]

        for user_id in USERS:
            if group_cache[user_id] != owner_group_id:
                continue  # skip users outside the group

            if random.random() < RAND:
                res = create_comment(user_id, prop_id, f"AI comment by {user_id}")
                if res:
                    comment_id = res.get("comment_id") or res.get("id")
                    if comment_id:
                        all_comments.append({
                            "id": comment_id,
                            "proposal_id": prop_id,
                            "owner": user_id
                        })

    print(f"[INFO] {len(all_comments)} comments created by AI users")

    # --- Step 3: Vote on proposals (only within same group) ---
    for proposal in all_proposals:
        prop_id = proposal["id"]
        owner_group_id = group_cache[proposal["owner"]]

        for user_id in USERS:
            if group_cache[user_id] != owner_group_id:
                continue

            score = random.randint(1, 5)
            vote_proposal(user_id, prop_id, score)

    print("[INFO] Voting on proposals completed")

    # --- Step 4: Vote on comments (only within same group) ---
    for comment in all_comments:
        comment_id = comment["id"]
        prop_owner = comment["owner"]
        owner_group_id = group_cache[prop_owner]

        for user_id in USERS:
            if group_cache[user_id] != owner_group_id:
                continue

            vote = random.choice([True, False])
            vote_comment(user_id, comment_id, vote)

    print("[INFO] Voting on comments completed")

def start_fractal(fractal_id = CURRENT_FRACTAL):
    try:
        res = api_post(f"/fractals/{fractal_id}/start", {})
        if res.get("ok"):
            print(f"Fractal {fractal_id} started successfully (round 0 created).")       
        else:
            print(f"Fractal {fractal_id} start response: {res}")
        return res
    except Exception as e:
        print(f"[ERROR] Failed to start fractal {fractal_id}: {e}")
        return None
    
# ----------------- CLI Loop -----------------
def run_cli():
    print("Fractal Governance CLI (Mock Telegram/Discord/AI, 128 users)")
    print("Commands:")
    print("  /create_fractal <name> <description> <start_date>")
    print("  /join_open <fractal_id>")
    print("  /simulate_ai")
    print("  /close_round")
    print("  /todo")
    print("  /status")
    print("  /exit")
    print("  /start")
    print("  /list_open")

    while True:
        cmd = input(">> ").strip()
        if not cmd:
            continue
        try:
            parts = shlex.split(cmd)

                # Start a new fractal
            if parts[0] == "/create_fractal":
                if len(parts) < 3:
                    print("Usage: /create_fractal <name> <description> [start_date]")
                    continue
                _, name, description = parts[:3]
                start_date = parts[3] if len(parts) > 3 else None  # optional
                create_fractal(1, name, description, start_date)
            # CLI command handler snippet
            elif parts[0] == "/start":
                if len(parts) < 2:
                    if not CURRENT_FRACTAL:
                        print("Usage: /start <optional: fractal_id>")
                        continue
                    fractal_id = CURRENT_FRACTAL
                else:
                    _, fractal_id = parts[:2]
                    fractal_id = int(fractal_id)
                start_fractal(fractal_id)

            # Join an existing fractal (all AI users)
            elif parts[0] == "/join_open":
                if len(parts) < 2:
                    print("Usage: /join_open <fractal_id>")
                    continue
                _, fractal_id = parts[:2]
                join_open(int(fractal_id))

            elif parts[0] == "/list_open":
                list_open_fractals()                    

            # Simulate AI round for current fractal
            elif parts[0] == "/simulate_ai":
                if not CURRENT_FRACTAL:
                    print("[ERROR] No fractal selected. Use /join_open <id> first.")
                    continue
                simulate_ai_round()

            # Close current round
            elif parts[0] == "/close_round":
                if not CURRENT_FRACTAL:
                    print("[ERROR] No fractal selected. Use /join_open <id> first.")
                    continue
                close_round()

            # Show TODOs for all AI users
            elif parts[0] == "/todo":
                if not CURRENT_FRACTAL:
                    print("[ERROR] No fractal selected. Use /join_open <id> first.")
                    continue
                for uid in USERS:
                    show_todo(uid)

            # Show fractal status
            elif parts[0] == "/status":
                if not CURRENT_FRACTAL:
                    print("[ERROR] No fractal selected. Use /join_open <id> first.")
                    continue
                show_status()

            # Exit CLI
            elif parts[0] == "/exit":
                break

            else:
                print("Unknown command")

        except Exception as e:
            print(f"[ERROR] {e}")



if __name__ == "__main__":
    run_cli()
