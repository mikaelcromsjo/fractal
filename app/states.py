from typing import Dict, List
from fastapi import WebSocket

connected_clients: Dict[str, List[WebSocket]] = {}  # fractal_id -> list of websockets
