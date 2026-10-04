# Telegram bot for Ox Alpha (official API adapter)

This starter bot forwards Telegram messages to an **official, authorized, OpenAI-compatible Ox Alpha API endpoint** and returns the answer. It does not automate the oxalpha.com website, extract browser session tokens, create accounts, rotate identities, or evade service limits.

## Current integration status

Ox Alpha's public pages describe a no-login web chat. No public API documentation or supported bot endpoint was found, so the API URL is intentionally left unset. The bot will not connect to `oxalpha.com/chat` until the service provides an official API endpoint or explicitly authorizes an integration. Do not substitute private frontend endpoints or browser cookies.

## Run

1. Install Python 3.10+.
2. `python -m venv .venv` and activate it.
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`, fill in the Telegram token and documented API settings.
5. Export the variables from `.env` in your shell, then run `python bot.py`.

Each Telegram user has an isolated in-memory chat. `/new` starts a chat; `/reset` removes its context. At `MAX_TURNS_PER_CHAT` user turns, the bot starts a clean chat to honor the stated ten-message limit. Restarting the process clears conversation history. Add a persistent database only if desired and disclose the retention policy to users.
