# ❄️ Fractal Circle

> Collective decision-making that scales like a snowflake — small circles discuss, vote, and hand their best ideas and a representative up to the next round, until one Circle holds the distilled result.

[![Live Demo](https://img.shields.io/badge/demo-fractal.ia--ai.se-5fd4e8?style=for-the-badge)](https://fractal.ia-ai.se)
[![FractalCircles.org](https://img.shields.io/badge/fractalcircles.org-learn%20more-5fd4e8?style=for-the-badge)](https://fractalcircles.org)
[![ia-ai.se](https://img.shields.io/badge/ia--ai.se-website-5fd4e8?style=for-the-badge)](https://ia-ai.se)

---

## What is this?

A structured group-decision tool, built as both a **Telegram Mini App** and a **standalone web app**. Groups of any size split into small Circles (4–8 people) to propose ideas, discuss, and vote. The top proposals and a chosen representative from each Circle advance to the next round — repeating until a single Circle holds the final, distilled result.

- 🗳️ **Private, anonymous voting** — 1–10 proposal scoring, ⭐ comment ratings
- 🥇 **Gold / Silver / Bronze** representative selection each round
- 💬 A **group chat per Circle**, alongside the structured vote
- 📜 **Full round history** once a Fractal ends
- 🌐 Works inside Telegram *or* as a plain web app at [`/app`](https://fractal.ia-ai.se/app) — no install required

## Stack

FastAPI · PostgreSQL · aiogram (Telegram bot) · vanilla JS + Mako templates

## Running it

```bash
docker compose up -d
```

Set `BOT_TOKEN` and `DATABASE_URL` in `.env` (gitignored — never commit real values). Then:

- App: `http://localhost:8030`
- API docs: `http://localhost:8030/docs`

```bash
# run tests
docker exec -it fractal python -m pytest -o anyio_backend=asyncio --tb=line -q -x

# project structure scan
docker exec -it fractal python scripts/scan_project.py
```

---

<div align="center">

[ia-ai.se](https://ia-ai.se) · [mikael.cromsjo@gmail.com](mailto:mikael.cromsjo@gmail.com)

</div>
