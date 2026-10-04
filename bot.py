import asyncio
import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API_URL = os.environ.get("OXALPHA_API_URL", "").strip()
API_KEY = os.environ.get("OXALPHA_API_KEY", "").strip()
MODEL = os.environ.get("OXALPHA_MODEL", "ox-alpha")
MAX_TURNS = int(os.environ.get("MAX_TURNS_PER_CHAT", "10"))

# In-memory state: process restart clears chats. Each Telegram user gets an
# isolated conversation; after MAX_TURNS, context is reset for a fresh chat.
conversations = defaultdict(lambda: {"messages": [], "turns": 0})
locks = defaultdict(asyncio.Lock)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Напиши сообщение — я передам его подключённому Ox Alpha API.\n"
        "Команды: /new — начать новый чат, /reset — удалить текущий контекст."
    )

async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversations.pop(update.effective_user.id, None)
    await update.message.reply_text("Новый чат начат.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversations.pop(update.effective_user.id, None)
    await update.message.reply_text("Контекст удалён.")

async def request_model(messages):
    if not API_URL:
        raise RuntimeError("OXALPHA_API_URL не настроен: нужен официальный API endpoint Ox Alpha.")
    payload = json.dumps({"model": MODEL, "messages": messages}).encode()
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")

    def send():
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.loads(response.read().decode())
    data = await asyncio.to_thread(send)
    # OpenAI-compatible chat completions response.
    return data["choices"][0]["message"]["content"]

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text or ""
    async with locks[user_id]:
        state = conversations[user_id]
        if state["turns"] >= MAX_TURNS:
            state = {"messages": [], "turns": 0}
            conversations[user_id] = state
            await update.message.reply_text("Достигнут лимит сообщений в этом чате. Начинаю новый чат.")
        state["messages"].append({"role": "user", "content": text})
        status = await update.message.reply_text("Думаю…")
        try:
            result = await request_model(state["messages"])
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            await status.edit_text(f"API вернул ошибку {e.code}: {detail}")
            state["messages"].pop()
            return
        except Exception as e:
            await status.edit_text(f"Не удалось получить ответ: {e}")
            state["messages"].pop()
            return
        state["messages"].append({"role": "assistant", "content": result})
        state["turns"] += 1
        # Telegram message limit; split safely into chunks.
        chunks = [result[i:i+4000] for i in range(0, len(result), 4000)] or ["(пустой ответ)"]
        await status.edit_text(chunks[0])
        for chunk in chunks[1:]:
            await update.message.reply_text(chunk)

async def main():
    if not API_URL:
        print("Warning: configure OXALPHA_API_URL with an official supported endpoint before use.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_chat))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
