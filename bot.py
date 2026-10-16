import os
import sqlite3
from datetime import time
from zoneinfo import ZoneInfo

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

# Адрес вашего Mini App / API.
# Пример: https://your-domain.trycloudflare.com
API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")

TIMEZONE = ZoneInfo("Europe/Moscow")
DAILY_HOUR = 8
DAILY_MINUTE = 0

DB_FILE = "channels.db"

def get_db():
    return sqlite3.connect(DB_FILE)

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                notifications_enabled INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()

def save_subscriber(chat_id: int, user_id: int):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO subscribers (chat_id, user_id, notifications_enabled)
            VALUES (?, ?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET
                user_id = excluded.user_id,
                notifications_enabled = 1
        """, (chat_id, user_id))
        conn.commit()

def set_notifications(chat_id: int, enabled: bool):
    with get_db() as conn:
        conn.execute("""
            UPDATE subscribers
            SET notifications_enabled = ?
            WHERE chat_id = ?
        """, (1 if enabled else 0, chat_id))
        conn.commit()

def get_subscribers():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT chat_id
            FROM subscribers
            WHERE notifications_enabled = 1
        """).fetchall()
    return [row[0] for row in rows]

async def api_get(path: str):
    if not API_BASE_URL:
        raise RuntimeError("Не задан API_BASE_URL")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{API_BASE_URL}{path}")
        response.raise_for_status()
        return response.json()

def format_schedule(schedule_data) -> list[str]:
    if isinstance(schedule_data, dict):
        items = (
            schedule_data.get("schedule")
            or schedule_data.get("items")
            or schedule_data.get("lessons")
            or []
        )
    else:
        items = schedule_data or []

    lines = []

    for item in items:
        if isinstance(item, str):
            lines.append(f"• {item}")
            continue

        if not isinstance(item, dict):
            continue

        title = (
            item.get("title")
            or item.get("name")
            or item.get("subject")
            or "Без названия"
        )
        lesson_time = (
            item.get("time")
            or item.get("startTime")
            or item.get("start_time")
            or ""
        )

        lines.append(f"• {lesson_time} — {title}" if lesson_time else f"• {title}")

    return lines

def format_tasks(day_data) -> list[str]:
    if isinstance(day_data, dict):
        tasks = day_data.get("tasks") or day_data.get("items") or []
    else:
        tasks = day_data or []

    lines = []

    for task in tasks:
        if isinstance(task, str):
            lines.append(f"• {task}")
            continue

        if not isinstance(task, dict):
            continue

        if task.get("completed") or task.get("done"):
            continue

        title = task.get("title") or task.get("text") or task.get("name") or "Без названия"
        task_time = task.get("time") or task.get("deadline") or ""

        lines.append(f"• {task_time} — {title}" if task_time else f"• {title}")

    return lines

async def build_daily_plan() -> str:
    try:
        day_data = await api_get("/api/day")
        schedule_data = await api_get("/api/schedule")

        schedule_lines = format_schedule(schedule_data)
        task_lines = format_tasks(day_data)

        date_text = time_now().strftime("%d.%m.%Y")

        schedule_text = "\n".join(schedule_lines) if schedule_lines else "• Занятий нет"
        tasks_text = "\n".join(task_lines) if task_lines else "• Дел нет"

        return (
            f"📅 План на сегодня — {date_text}\n\n"
            f"🕘 Расписание\n{schedule_text}\n\n"
            f"✅ Дела\n{tasks_text}"
        )

    except Exception as error:
        print(f"Ошибка получения плана из API: {error}")
        return (
            "📅 План на сегодня\n\n"
            "Не удалось загрузить расписание и дела. "
            "Проверьте, что Mini App и API запущены."
        )

def time_now():
    from datetime import datetime
    return datetime.now(TIMEZONE)

async def send_daily_plan(context: ContextTypes.DEFAULT_TYPE):
    text = await build_daily_plan()

    for chat_id in get_subscribers():
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as error:
            print(f"Не удалось отправить уведомление в {chat_id}: {error}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return

    save_subscriber(update.effective_chat.id, update.effective_user.id)

    await update.message.reply_text(
        "Уведомления включены.\n\n"
        "Каждый день в 08:00 я буду присылать расписание и дела на сегодня.\n\n"
        "Команды:\n"
        "/plan — получить план сейчас\n"
        "/off — отключить уведомления\n"
        "/on — включить уведомления"
    )

async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Загружаю план...")
    await update.message.reply_text(await build_daily_plan())

async def off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    set_notifications(update.effective_chat.id, False)
    await update.message.reply_text("Уведомления отключены. Включить обратно: /on")

async def on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return

    save_subscriber(update.effective_chat.id, update.effective_user.id)
    await update.message.reply_text("Уведомления включены. План будет приходить в 08:00.")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задана переменная BOT_TOKEN")

    if not API_BASE_URL:
        raise RuntimeError(
            "Не задана переменная API_BASE_URL. "
            "Укажите публичный адрес Mini App, например https://xxxx.trycloudflare.com"
        )

    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("plan", plan))
    application.add_handler(CommandHandler("off", off))
    application.add_handler(CommandHandler("on", on))

    application.job_queue.run_daily(
        send_daily_plan,
        time=time(hour=DAILY_HOUR, minute=DAILY_MINUTE, tzinfo=TIMEZONE),
        name="daily_plan_for_all_users",
    )

    print("Бот запущен. Ежедневный план: 08:00, Europe/Moscow.")
    application.run_polling()

if __name__ == "__main__":
    main()
