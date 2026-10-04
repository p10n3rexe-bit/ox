# Ox Alpha Telegram Bot

The bot forwards Telegram text to the public Ox Alpha chat page at `https://oxalpha.com/chat` through its visible web interface, then returns the completed answer. It does not require an Ox Alpha account or API key.

## Chat behavior

- A separate browser context keeps each Telegram user's page history isolated.
- A single global queue sends requests one at a time and applies a minimum pause between them.
- After 10 user messages in a chat, the bot clicks **New Chat** in the website UI.
- `/new` and `/reset` start a fresh website chat while keeping the same browser context.
- Session data is held in memory and is cleared when the bot process stops.
- The bot does not rotate accounts, cookies, proxies, or network identities.

## Run

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment: `python -m venv .venv`.
3. Install dependencies: `pip install -r requirements.txt`.
4. Install Chromium for Playwright: `python -m playwright install chromium`.
   On Linux systems missing browser libraries, use `python -m playwright install --with-deps chromium`.
5. Copy `.env.example` to `.env`, then set `TELEGRAM_BOT_TOKEN` from BotFather.
6. Export the variables from `.env` in your shell and run `python bot.py`.

The public chat page can change without notice. If its input, send button, or response markup changes, the selectors in `bot.py` may need an update.

## Bothost deployment

The standard Bothost Python build installs packages from `requirements.txt` but does not download Playwright browser binaries. This project includes a `Dockerfile` that installs Chromium and its Linux system dependencies during image build.

In the Bothost dashboard, edit the bot, open **Дополнительные настройки**, enable **Использовать собственный Dockerfile**, then redeploy. Add the values from `.env.example` under the bot's environment variables; keep the Telegram token private.
