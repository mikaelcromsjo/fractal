# app/adapters/telegram_bot.py
"""
Telegram Bot Adapter with inline voting for proposals and comments.

- Commands: /start_fractal, /join, /proposal, /todo, /status
- Inline keyboards are used for proposal and comment voting.
- Supports nested comments voting.
- Votes sent to backend via HTTP requests.
"""

import os
import logging
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8030")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# ---------- Command Handlers ----------

async def start_fractal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a new fractal"""
    user_id = update.effective_user.id
    try:
        name = context.args[0]
        description = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        resp = requests.post(f"{BACKEND_URL}/fractals/create", json={
            "user_id": user_id,
            "name": name,
            "description": description
        })
        if resp.ok:
            await update.message.reply_text(f"Fractal '{name}' created successfully!")
        else:
            await update.message.reply_text(f"Error: {resp.text}")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Usage: /start_fractal <name> <description>")


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Join an existing fractal"""
    user_id = update.effective_user.id
    try:
        fractal_name = context.args[0]
        resp = requests.post(f"{BACKEND_URL}/fractals/join", json={
            "user_id": user_id,
            "name": fractal_name
        })
        if resp.ok:
            await update.message.reply_text(f"Joined fractal '{fractal_name}' successfully!")
        else:
            await update.message.reply_text(f"Error: {resp.text}")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Usage: /join <fractal_name>")


async def proposal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit a proposal"""
    user_id = update.effective_user.id
    try:
        title = context.args[0]
        body = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        resp = requests.post(f"{BACKEND_URL}/proposals/create", json={
            "user_id": user_id,
            "title": title,
            "description": body
        })
        if resp.ok:
            await update.message.reply_text(f"Proposal '{title}' submitted!")
        else:
            await update.message.reply_text(f"Error: {resp.text}")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Usage: /proposal <title> <description>")


# ---------- Inline Voting ----------

def build_proposal_vote_keyboard(proposal_id: int):
    """Return InlineKeyboardMarkup with buttons 1-10"""
    buttons = [
        InlineKeyboardButton(str(i), callback_data=f"proposal_vote:{proposal_id}:{i}") 
        for i in range(1, 11)
    ]
    return InlineKeyboardMarkup([buttons[:5], buttons[5:]])


def build_comment_vote_keyboard(comment_id: int):
    """Return InlineKeyboardMarkup for comment voting yes/no"""
    buttons = [
        InlineKeyboardButton("👍", callback_data=f"comment_vote:{comment_id}:yes"),
        InlineKeyboardButton("👎", callback_data=f"comment_vote:{comment_id}:no")
    ]
    return InlineKeyboardMarkup([buttons])


async def send_proposal_for_voting(chat_id: int, proposal: dict, context: ContextTypes.DEFAULT_TYPE):
    """Send a proposal with inline vote buttons"""
    text = f"Proposal #{proposal['id']}: {proposal['title']}\n{proposal.get('description', '')}"
    keyboard = build_proposal_vote_keyboard(proposal['id'])
    await context.bot.send_message(chat_id, text, reply_markup=keyboard)


async def send_comment_for_voting(chat_id: int, comment: dict, context: ContextTypes.DEFAULT_TYPE):
    """Send a comment with inline vote buttons"""
    text = f"Comment #{comment['id']} by User {comment['user_id']}:\n{comment['content']}"
    keyboard = build_comment_vote_keyboard(comment['id'])
    await context.bot.send_message(chat_id, text, reply_markup=keyboard)


# ---------- Callback Handlers ----------

async def proposal_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline proposal votes"""
    query = update.callback_query
    await query.answer()
    try:
        data = query.data.split(":")
        if len(data) != 3 or data[0] != "proposal_vote":
            return
        proposal_id = int(data[1])
        score = int(data[2])
        user_id = query.from_user.id
        resp = requests.post(f"{BACKEND_URL}/votes/proposal", json={
            "user_id": user_id,
            "proposal_id": proposal_id,
            "vote": score
        })
        if resp.ok:
            await query.edit_message_text(f"You voted {score} on proposal #{proposal_id}")
        else:
            await query.edit_message_text(f"Error voting: {resp.text}")
    except Exception as e:
        logger.error(e)
        await query.edit_message_text("Error processing your vote.")


async def comment_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline comment votes"""
    query = update.callback_query
    await query.answer()
    try:
        data = query.data.split(":")
        if len(data) != 3 or data[0] != "comment_vote":
            return
        comment_id = int(data[1])
        vote = data[2]
        user_id = query.from_user.id
        resp = requests.post(f"{BACKEND_URL}/votes/comment", json={
            "user_id": user_id,
            "comment_id": comment_id,
            "vote": vote
        })
        if resp.ok:
            await query.edit_message_text(f"You voted {vote} on comment #{comment_id}")
        else:
            await query.edit_message_text(f"Error voting: {resp.text}")
    except Exception as e:
        logger.error(e)
        await query.edit_message_text("Error processing your vote.")


# ---------- TODO & Status ----------

async def todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending actions for user including proposals and comments"""
    user_id = update.effective_user.id
    resp = requests.get(f"{BACKEND_URL}/users/{user_id}/todo")
    if resp.ok:
        items = resp.json()
        if not items:
            await update.message.reply_text("No pending items!")
        else:
            for item in items:
                if item["type"] == "proposal":
                    await send_proposal_for_voting(update.effective_chat.id, item, context)
                elif item["type"] == "comment":
                    await send_comment_for_voting(update.effective_chat.id, item, context)
                else:
                    await update.message.reply_text(f"{item['type']} #{item['id']}")
    else:
        await update.message.reply_text("Error fetching TODOs.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show voting status"""
    user_id = update.effective_user.id
    resp = requests.get(f"{BACKEND_URL}/users/{user_id}/status")
    if resp.ok:
        data = resp.json()
        msg = "Proposals:\n" + "\n".join([f"{p['title']}: {p['avg_vote']}" for p in data.get("proposals", [])])
        msg += "\n\nComments:\n" + "\n".join([f"{c['content']}: {c['vote_summary']}" for c in data.get("comments", [])])
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Error fetching status.")


# ---------- Bot Startup ----------

def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # commands
    app.add_handler(CommandHandler("start_fractal", start_fractal))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("proposal", proposal))
    app.add_handler(CommandHandler("todo", todo))
    app.add_handler(CommandHandler("status", status))
    # inline votes
    app.add_handler(CallbackQueryHandler(proposal_vote_callback, pattern="^proposal_vote:"))
    app.add_handler(CallbackQueryHandler(comment_vote_callback, pattern="^comment_vote:"))
    logger.info("Bot running...")
    app.run_polling()


# Usage Example:
# export TELEGRAM_BOT_TOKEN=<token>
# python -c "from app.adapters import telegram_bot; telegram_bot.run_bot()"
