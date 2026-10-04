import asyncio
import logging
import os
import time
from dataclasses import dataclass

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_URL = os.environ.get("OXALPHA_CHAT_URL", "https://oxalpha.com/chat")
MAX_TURNS = max(1, int(os.environ.get("MAX_TURNS_PER_CHAT", "10")))
REPLY_TIMEOUT = max(30, int(os.environ.get("SITE_REPLY_TIMEOUT_SECONDS", "180")))
MIN_REQUEST_INTERVAL = max(0.0, float(os.environ.get("MIN_REQUEST_INTERVAL_SECONDS", "2")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("oxalpha-telegram-bot")


@dataclass
class UserSession:
    context: BrowserContext
    page: Page
    turns: int = 0


playwright = None
browser: Browser | None = None
sessions: dict[int, UserSession] = {}
session_lock = asyncio.Lock()
site_lock = asyncio.Lock()
last_site_request = 0.0


async def get_session(user_id: int) -> UserSession:
    async with session_lock:
        session = sessions.get(user_id)
        if session:
            return session
        if browser is None:
            raise RuntimeError("Browser is not initialized")
        # One isolated browser context per Telegram user prevents chat history
        # from being shared. No accounts, proxies, or identity rotation are used.
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)
        await page.locator("textarea").wait_for(state="visible", timeout=60000)
        session = UserSession(context=context, page=page)
        sessions[user_id] = session
        return session


async def start_new_chat(page: Page) -> None:
    new_chat = page.get_by_role("button", name="New Chat", exact=True)
    if await new_chat.count() == 0:
        expand = page.get_by_role("button", name="Expand", exact=True)
        if await expand.count():
            await expand.click()
    await new_chat.wait_for(state="visible", timeout=10000)
    await new_chat.click()
    await page.locator("textarea").wait_for(state="visible", timeout=10000)


async def ask_site(session: UserSession, prompt: str) -> str:
    global last_site_request
    page = session.page
    assistant_messages = page.locator(".chat-area .msg.msg-assistant .prose")
    before = await assistant_messages.count()

    field = page.locator("textarea")
    await field.fill(prompt)
    await page.get_by_role("button", name="Send", exact=True).click()

    deadline = time.monotonic() + REPLY_TIMEOUT
    previous_text = ""
    stable_polls = 0
    while time.monotonic() < deadline:
        count = await assistant_messages.count()
        if count > before:
            answer = (await assistant_messages.last.inner_text()).strip()
            sending = await page.get_by_role("button", name="Stop", exact=True).count()
            thinking = await page.get_by_role("status").count()
            if answer and sending == 0 and thinking == 0:
                if answer == previous_text:
                    stable_polls += 1
                else:
                    previous_text = answer
                    stable_polls = 0
                if stable_polls >= 1:
                    return answer
        await asyncio.sleep(0.35)

    raise TimeoutError("Ox Alpha did not finish a reply before the timeout")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Напиши сообщение — передам его в веб-чат Ox Alpha.\n"
        "Команды: /new — новый чат, /reset — очистить историю этого Telegram-чата."
    )


async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with site_lock:
        session = await get_session(user_id)
        await start_new_chat(session.page)
        session.turns = 0
    await update.message.reply_text("Начал новый чат Ox Alpha.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with site_lock:
        session = await get_session(user_id)
        await start_new_chat(session.page)
        session.turns = 0
    await update.message.reply_text("Начал новый чат; браузерная сессия сохранена.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global last_site_request
    user_id = update.effective_user.id
    prompt = update.message.text or ""
    if not prompt.strip():
        return

    status = await update.message.reply_text("Передаю запрос в Ox Alpha…")
    try:
        async with site_lock:
            session = await get_session(user_id)
            if session.turns >= MAX_TURNS:
                await start_new_chat(session.page)
                session.turns = 0
                await status.edit_text("Начал новый чат после 10 сообщений. Жду ответ…")

            delay = MIN_REQUEST_INTERVAL - (time.monotonic() - last_site_request)
            if delay > 0:
                await asyncio.sleep(delay)
            last_site_request = time.monotonic()
            response = await ask_site(session, prompt)
            session.turns += 1

        chunks = [response[i:i + 4000] for i in range(0, len(response), 4000)] or ["(пустой ответ)"]
        await status.edit_text(chunks[0])
        for chunk in chunks[1:]:
            await update.message.reply_text(chunk)
    except Exception as exc:
        log.warning("Request failed for Telegram user %s: %s", user_id, type(exc).__name__)
        await status.edit_text(
            "Не удалось получить ответ от веб-чата. Попробуй ещё раз или начни новый чат командой /new."
        )


async def post_init(application: Application) -> None:
    global playwright, browser
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    log.info("Ox Alpha browser session is ready")


async def post_shutdown(application: Application) -> None:
    global playwright, browser
    for session in list(sessions.values()):
        await session.context.close()
    sessions.clear()
    if browser:
        await browser.close()
    if playwright:
        await playwright.stop()


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_chat))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
