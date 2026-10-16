import asyncio, hashlib, hmac, json, os, sqlite3, urllib.parse
from contextlib import closing
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]  # публичный https-адрес сервера
PORT = int(os.getenv("PORT", "8000"))
DB = os.getenv("DB_PATH", "schedule.db")
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- база ----------
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def rows(sql, args=()):
    with closing(db()) as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def ex(sql, args=()):
    with closing(db()) as c:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def mark(uid, key):
    """True, если это сообщение сегодня ещё не отправлялось."""
    with closing(db()) as c:
        cur = c.execute("INSERT OR IGNORE INTO sent VALUES(?,?)", (uid, key))
        c.commit()
        return cur.rowcount == 1


def init():
    with closing(db()) as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY, tz TEXT DEFAULT 'Europe/Moscow',
                morning TEXT DEFAULT '06:00', first TEXT DEFAULT '13:00',
                every INTEGER DEFAULT 2, last TEXT DEFAULT '23:00', city TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS schedule(
                user_id INTEGER, wd INTEGER, text TEXT DEFAULT '',
                PRIMARY KEY(user_id, wd));
            CREATE TABLE IF NOT EXISTS tasks(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                day TEXT, title TEXT, at TEXT DEFAULT '', done INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sent(
                user_id INTEGER, key TEXT, PRIMARY KEY(user_id, key));
            """
        )
        try:
            c.execute("ALTER TABLE users ADD COLUMN city TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        c.commit()


def user(uid):
    return rows("SELECT * FROM users WHERE id=?", (uid,))[0]


def lessons(uid, wd):
    r = rows("SELECT text FROM schedule WHERE user_id=? AND wd=?", (uid, wd))
    return [l.strip() for l in (r[0]["text"] if r else "").splitlines() if l.strip()]


def hhmm(s):
    try:
        datetime.strptime(s, "%H:%M")
        return s
    except Exception:
        raise HTTPException(400, "Время нужно в формате ЧЧ:ММ")


# ---------- авторизация через Telegram ----------
def me(x_init_data: str = Header("")):
    try:
        d = dict(urllib.parse.parse_qsl(x_init_data, strict_parsing=True))
        h = d.pop("hash")
        s = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
        key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(hmac.new(key, s.encode(), hashlib.sha256).hexdigest(), h):
            raise ValueError
        uid = json.loads(d["user"])["id"]
    except Exception:
        raise HTTPException(401, "Открой приложение из Telegram")
    ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
    return uid


# ---------- API ----------
app = FastAPI()


class TaskIn(BaseModel):
    day: str
    title: str
    at: str = ""


class DoneIn(BaseModel):
    done: bool


class ScheduleIn(BaseModel):
    days: list[str]


class SettingsIn(BaseModel):
    tz: str
    morning: str
    first: str
    every: int
    last: str
    city: str = ""


@app.get("/")
def index():
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html.replace("</body>", '<script src="/extras.js"></script></body>'))


@app.get("/extras.js")
def extras():
    return FileResponse(os.path.join(HERE, "extras.js"), media_type="application/javascript")


@app.get("/api/day")
def get_day(d: str = "", uid: int = Depends(me)):
    u = user(uid)
    t = datetime.now(ZoneInfo(u["tz"])).date().isoformat()
    d = d or t
    wd = date.fromisoformat(d).weekday()
    return {
        "date": d,
        "today": t,
        "lessons": lessons(uid, wd),
        "tasks": rows(
            "SELECT id,title,at,done FROM tasks WHERE user_id=? AND day=? ORDER BY at='', at, id",
            (uid, d),
        ),
        "overdue": rows(
            "SELECT id,title,day,at FROM tasks WHERE user_id=? AND day<? AND done=0 ORDER BY day, at",
            (uid, t),
        ),
    }


@app.post("/api/tasks")
def add_task(t: TaskIn, uid: int = Depends(me)):
    title = t.title.strip()
    if not title:
        raise HTTPException(400, "Название пустое")
    date.fromisoformat(t.day)
    at = hhmm(t.at) if t.at else ""
    return {"id": ex("INSERT INTO tasks(user_id,day,title,at) VALUES(?,?,?,?)", (uid, t.day, title, at))}


@app.patch("/api/tasks/{tid}")
def set_done(tid: int, b: DoneIn, uid: int = Depends(me)):
    ex("UPDATE tasks SET done=? WHERE id=? AND user_id=?", (int(b.done), tid, uid))
    return {"ok": True}


@app.delete("/api/tasks/{tid}")
def del_task(tid: int, uid: int = Depends(me)):
    ex("DELETE FROM tasks WHERE id=? AND user_id=?", (tid, uid))
    return {"ok": True}


@app.post("/api/tasks/{tid}/postpone")
def postpone(tid: int, uid: int = Depends(me)):
    u = user(uid)
    t = datetime.now(ZoneInfo(u["tz"])).date()
    r = rows("SELECT day FROM tasks WHERE id=? AND user_id=?", (tid, uid))
    if not r:
        raise HTTPException(404, "Дело не найдено")
    d = max(date.fromisoformat(r[0]["day"]), t) + timedelta(days=1)
    ex("UPDATE tasks SET day=? WHERE id=?", (d.isoformat(), tid))
    return {"day": d.isoformat()}


@app.get("/api/schedule")
def get_schedule(uid: int = Depends(me)):
    days = [""] * 7
    for r in rows("SELECT wd,text FROM schedule WHERE user_id=?", (uid,)):
        days[r["wd"]] = r["text"]
    return {"days": days}


@app.put("/api/schedule")
def put_schedule(b: ScheduleIn, uid: int = Depends(me)):
    for wd, text in enumerate(b.days[:7]):
        ex("INSERT OR REPLACE INTO schedule VALUES(?,?,?)", (uid, wd, text))
    return {"ok": True}


@app.get("/api/settings")
def get_settings(uid: int = Depends(me)):
    return user(uid)


@app.put("/api/settings")
def put_settings(b: SettingsIn, uid: int = Depends(me)):
    try:
        ZoneInfo(b.tz)
    except Exception:
        raise HTTPException(400, "Неизвестный часовой пояс, пример: Europe/Moscow")
    if b.every < 1:
        raise HTTPException(400, "Интервал должен быть от 1 часа")
    ex(
        "UPDATE users SET tz=?,morning=?,first=?,every=?,last=?,city=? WHERE id=?",
        (b.tz, hhmm(b.morning), hhmm(b.first), b.every, hhmm(b.last), b.city.strip()[:80], uid),
    )
    return {"ok": True}


# ---------- рассылка ----------
def kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )


def due(now, t):
    h, m = map(int, t.split(":"))
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return start <= now < start + timedelta(minutes=10)


def reminder_times(u):
    h, m = map(int, u["first"].split(":"))
    lh, lm = map(int, u["last"].split(":"))
    t, end, out = h * 60 + m, lh * 60 + lm, []
    while t <= end:
        out.append(f"{t // 60:02d}:{t % 60:02d}")
        t += u["every"] * 60
    return out


QUOTES = [
    "Маленький шаг сегодня лучше большого плана на потом.",
    "Не нужно делать всё сразу, нужно начать.",
    "Ты уже справлялся с трудным, справишься и с этим.",
    "Порядок в делах начинается с одного списка.",
    "Лучше сделать неидеально, чем не сделать совсем.",
    "Отдых тоже часть плана.",
    "Сложное делается по частям, одна часть за раз.",
    "Каждая выполненная галочка делает день легче.",
]


async def weather(city):
    if not city:
        return ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": city, "count": 1, "language": "ru"}) as r:
                p = (await r.json())["results"][0]
            async with s.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto", "forecast_days": 1,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max"}) as r:
                d = (await r.json())["daily"]
        hi, lo = round(d["temperature_2m_max"][0]), round(d["temperature_2m_min"][0])
        rain = d["precipitation_probability_max"][0] or 0
        return f"🌤 {p['name']}: от {lo}° до {hi}°" + (f", осадки {rain}%, возьми зонт" if rain >= 50 else "")
    except Exception as e:
        print("weather error", e)
        return ""


async def tick(bot, u):
    uid = u["id"]
    now = datetime.now(ZoneInfo(u["tz"]))
    d = now.date().isoformat()

    if due(now, u["morning"]) and mark(uid, f"{d}:morning"):
        ls = lessons(uid, now.weekday())
        text = (
            "Уроки на сегодня:\n" + "\n".join(f"{i}. {l}" for i, l in enumerate(ls, 1))
            if ls
            else "Сегодня уроков нет."
        )
        w = await weather(u.get("city", ""))
        text = (w + "\n\n" if w else "") + text + "\n\n💬 " + QUOTES[now.toordinal() % len(QUOTES)]
        await bot.send_message(uid, text, reply_markup=kb())

    for t in reminder_times(u):
        if not due(now, t):
            continue
        pend = rows(
            "SELECT title,at,day FROM tasks WHERE user_id=? AND day<=? AND done=0 ORDER BY day, at",
            (uid, d),
        )
        if pend and mark(uid, f"{d}:{t}"):
            lines = [
                ("↩️ " if p["day"] < d else "▫️ ") + (p["at"] + " " if p["at"] else "") + p["title"]
                for p in pend
            ]
            await bot.send_message(
                uid, "Не сделано:\n" + "\n".join(lines) + "\n\n↩️ — со вчера или раньше", reply_markup=kb()
            )


async def scheduler(bot):
    while True:
        for u in rows("SELECT * FROM users"):
            try:
                await tick(bot, u)
            except Exception as e:
                print("tick error", u["id"], e)
        await asyncio.sleep(30)


async def main():
    init()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(m: Message):
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (m.from_user.id,))
        await m.answer(
            "Привет! Открой приложение, впиши школьное расписание и добавляй свои дела.",
            reply_markup=kb(),
        )

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning"))
    await asyncio.gather(dp.start_polling(bot, handle_signals=False), server.serve(), scheduler(bot))


if __name__ == "__main__":
    asyncio.run(main())
