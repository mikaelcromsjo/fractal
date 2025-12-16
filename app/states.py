from typing import Dict, List
from fastapi import WebSocket
import os
print(f"[PID {os.getpid()}]")
connected_clients: Dict[str, List[WebSocket]] = {}  # fractal_id -> list of websockets
