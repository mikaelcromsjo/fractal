from typing import Dict, List
from fastapi import WebSocket
import os
connected_clients: Dict[str, List[WebSocket]] = {}  # fractal_id -> list of websockets
