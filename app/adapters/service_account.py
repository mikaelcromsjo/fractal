# app/adapters/service_account.py
"""
Service Account Adapter using Telethon for managing Telegram groups.

Provides functions to:
- create_group
- add_users_to_group
- generate_invite_link
- dm_invite_link
- add_bot_to_group
- fetch_group_members
- remove_user_from_group

Configuration:
- Set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE environment variables
- Install Telethon (`pip install telethon`)
"""

import os
import logging
from typing import List
from telethon import TelegramClient
from telethon.tl.functions.messages import CreateChatRequest, AddChatUserRequest
from telethon.tl.functions.channels import InviteToChannelRequest, GetParticipantsRequest, LeaveChannelRequest
from telethon.tl.types import InputPeerUser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH"))
PHONE = os.getenv("TELEGRAM_PHONE"))

client = TelegramClient('service_account', API_ID, API_HASH)
_client_started = False

async def start_client():
    """Start the service account client (idempotent)."""
    global _client_started
    if not _client_started:
        await client.start(PHONE)
        _client_started = True
        logger.info("Service account connected")

async def create_group(title: str, user_ids: List[int]) -> int:
    """Create a private group with initial members"""
    result = await client(CreateChatRequest(users=user_ids, title=title))
    chat_id = result.chats[0].id
    logger.info(f"Created group '{title}' with id {chat_id}")
    return chat_id

async def add_users_to_group(chat_id: int, user_ids: List[int]):
    """Add multiple users to an existing group"""
    for user_id in user_ids:
        await client(AddChatUserRequest(chat_id=chat_id, user_id=user_id, fwd_limit=0))
    logger.info(f"Added {len(user_ids)} users to group {chat_id}")

async def generate_invite_link(chat_id: int) -> str:
    """Generate an invite link for a group"""
    link = await client.export_chat_invite_link(chat_id)
    logger.info(f"Generated invite link for group {chat_id}")
    return link

async def dm_invite_link(user_id: int, link: str):
    """Send invite link via DM"""
    await client.send_message(user_id, f"Join the fractal group: {link}")
