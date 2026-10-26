import asyncio, hashlib, hmac, json, os, sqlite3, urllib.parse
from contextlib import closing
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram import F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]  # публичный https-адрес сервера
PORT = int(os.getenv("PORT", "8000"))
DB = os.getenv("DB_PATH", "schedule.db")
HERE = os.path.dirname(os.path.abspath(__file__))


EXTRAS_JS = r'''/* Дополнения к интерфейсу: карточка «Сейчас», «Отложить на завтра», город, цвет приложения.
   Подключается сервером автоматически, index.html менять не нужно. */
(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  const app = document.getElementById("app");
  const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const hdr = () => ({"Content-Type": "application/json", "X-Init-Data": tg ? tg.initData : ""});
  const THEMES = {blue: ["#2F90FF", 0], purple: ["#9B6CFF", 70], green: ["#2FD98A", -75], red: ["#FF5C6C", 150]};
  const saved = () => { try { return localStorage.getItem("planner_theme") || "blue"; } catch (e) { return "blue"; } };
  const applyTheme = n => document.documentElement.style.setProperty("--hue", (THEMES[n] || THEMES.blue)[1] + "deg");

  const st = document.createElement("style");
  st.textContent = `html{filter:hue-rotate(var(--hue,0deg))}img{filter:hue-rotate(calc(var(--hue,0deg)*-1))}
.now-main{font-size:20px;font-weight:800;letter-spacing:-.3px;margin-top:2px}
.pp-btn{width:32px;height:32px;display:grid;place-items:center;flex:none;padding:0;border-radius:10px;color:#9DB8D9;background:transparent;font-size:18px}
.pp-btn:active{color:#48D7FF;background:rgba(72,215,255,.16)}
.themes{display:flex;gap:14px}
.theme-dot{width:44px;height:44px;border-radius:50%;border:3px solid transparent;padding:0;filter:hue-rotate(calc(var(--hue,0deg)*-1))}
.theme-dot.on{border-color:#fff}`;
  document.head.appendChild(st);
  applyTheme(saved());

  // город уходит на сервер вместе с остальными настройками
  const origFetch = window.fetch;
  window.fetch = (url, o = {}) => {
    const c = document.getElementById("setting-city");
    if (String(url).endsWith("/api/settings") && o.method === "PUT" && c)
      o = {...o, body: JSON.stringify({...JSON.parse(o.body), city: c.value.trim()})};
    return origFetch(url, o);
  };

  function nowCard() {
    const items = [...app.querySelectorAll(".lesson-text")].map(e => {
      const m = /^(\d{1,2})[:.](\d{2})\s+(.+)$/.exec(e.textContent.trim());
      return m ? {at: +m[1] * 60 + +m[2], t: m[3], hm: m[1].padStart(2, "0") + ":" + m[2]} : null;
    }).filter(Boolean);
    if (!items.length) return "";
    const d = new Date(), now = d.getHours() * 60 + d.getMinutes();
    const cur = [...items].reverse().find(i => i.at <= now && now < i.at + 45);
    const next = items.find(i => i.at > now);
    let label = "Сейчас", main, sub = "";
    if (cur) { main = cur.t; sub = next ? `Дальше: ${next.t} в ${next.hm}` : "Это последний урок"; }
    else if (next) { label = "Дальше"; main = next.t; sub = `Начало в ${next.hm}, через ${next.at - now} мин`; }
    else main = "Уроки на сегодня закончились";
    return `<section class="card progress-card now-card"><div class="progress-label">${label}</div><div class="now-main">${esc(main)}</div>${sub ? `<p class="hero-text">${esc(sub)}</p>` : ""}</section>`;
  }

  function enhance() {
    const lessonsTitle = [...app.querySelectorAll(".card-title")].find(e => e.textContent === "Уроки сегодня");
    if (lessonsTitle) {
      if (!app.querySelector(".now-card") && !app.querySelector(".today-link")) {
        const html = nowCard();
        if (html) lessonsTitle.closest("section").insertAdjacentHTML("beforebegin", html);
      }
      app.querySelectorAll(".task").forEach(row => {
        const del = row.querySelector(".delete-btn");
        const m = del && /deleteTask\((\d+)\)/.exec(del.getAttribute("onclick") || "");
        if (!m || row.querySelector(".pp-btn")) return;
        const b = document.createElement("button");
        b.type = "button"; b.className = "pp-btn"; b.textContent = "→";
        b.setAttribute("aria-label", "Отложить на завтра"); b.title = "Отложить на завтра";
        b.dataset.id = m[1];
        del.before(b);
      });
    }
    if (app.querySelector("#setting-tz") && !app.querySelector("#setting-city")) {
      app.querySelector("#save-settings-button").insertAdjacentHTML("beforebegin",
        `<label class="field-label" for="setting-city">Город (для погоды в утреннем сообщении)</label>
         <input id="setting-city" type="text" placeholder="Например, Москва">`);
      fetch("/api/settings", {headers: hdr()}).then(r => r.json()).then(s => {
        const c = document.getElementById("setting-city"); if (c && !c.value) c.value = s.city || "";
      }).catch(() => {});
      app.insertAdjacentHTML("beforeend", `<section class="card"><div class="card-title-row"><h2 class="card-title">Цвет приложения</h2></div>
        <div class="themes">${Object.entries(THEMES).map(([n, t]) =>
          `<button class="theme-dot ${n === saved() ? "on" : ""}" data-theme="${n}" style="background:${t[0]}" aria-label="${n}"></button>`).join("")}</div></section>`);
    }
  }

  app.addEventListener("click", async e => {
    const dot = e.target.closest(".theme-dot");
    if (dot) {
      try { localStorage.setItem("planner_theme", dot.dataset.theme); } catch (_) {}
      applyTheme(dot.dataset.theme);
      app.querySelectorAll(".theme-dot").forEach(x => x.classList.toggle("on", x === dot));
      return;
    }
    const pp = e.target.closest(".pp-btn");
    if (pp) {
      pp.disabled = true;
      try { await fetch(`/api/tasks/${pp.dataset.id}/postpone`, {method: "POST", headers: hdr()}); } catch (_) {}
      if (window.Planner) window.Planner.reload();
    }
  });

  new MutationObserver(enhance).observe(app, {childList: true});
  enhance();
})();
'''


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
            CREATE TABLE IF NOT EXISTS exams(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, subject TEXT, day TEXT);
            CREATE TABLE IF NOT EXISTS someday(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT);
            """
        )
        try:
            c.execute("ALTER TABLE users ADD COLUMN city TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN name TEXT DEFAULT ''")
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
    return HTMLResponse(html.replace("</body>", '<script src="/extras.js?v=3"></script><script src="/extras2.js?v=1"></script><script src="/extras3.js?v=1"></script><script src="/extras4.js?v=1"></script></body>'),
                        headers={"Cache-Control": "no-store"})


@app.get("/extras.js")
def extras():
    return Response(EXTRAS_JS, media_type="application/javascript; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


@app.get("/extras2.js")
def extras2():
    with open(os.path.join(HERE, "extras2.js"), encoding="utf-8") as f:
        return Response(f.read(), media_type="application/javascript; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


@app.get("/extras3.js")
def extras3():
    with open(os.path.join(HERE, "extras3.js"), encoding="utf-8") as f:
        return Response(f.read(), media_type="application/javascript; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


@app.get("/extras4.js")
def extras4():
    with open(os.path.join(HERE, "extras4.js"), encoding="utf-8") as f:
        return Response(f.read(), media_type="application/javascript; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


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


# ---------- погода (Open-Meteo, без ключа) ----------
WX = {0: ("Ясно", "☀️", "clear"), 1: ("Малооблачно", "🌤", "clear"), 2: ("Облачно с прояснениями", "⛅", "cloud"),
      3: ("Пасмурно", "☁️", "cloud"), 45: ("Туман", "🌫", "fog"), 48: ("Туман", "🌫", "fog")}
for _c in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
    WX[_c] = ("Дождь", "🌧", "rain")
for _c in (71, 73, 75, 77, 85, 86):
    WX[_c] = ("Снег", "❄️", "snow")
for _c in (95, 96, 99):
    WX[_c] = ("Гроза", "⛈", "storm")


YX_KEY = os.getenv("YANDEX_WEATHER_KEY", "")
YX = {"clear": ("Ясно", "☀️", "clear"), "partly-cloudy": ("Облачно с прояснениями", "⛅", "cloud"),
      "cloudy": ("Облачно", "☁️", "cloud"), "overcast": ("Пасмурно", "☁️", "cloud"), "hail": ("Град", "🌨", "rain")}
for _c in ("drizzle", "light-rain", "rain", "moderate-rain", "heavy-rain", "continuous-heavy-rain", "showers"):
    YX[_c] = ("Дождь", "🌧", "rain")
for _c in ("wet-snow", "light-snow", "snow", "snow-showers"):
    YX[_c] = ("Снег", "❄️", "snow")
for _c in ("thunderstorm", "thunderstorm-with-rain", "thunderstorm-with-hail"):
    YX[_c] = ("Гроза", "⛈", "storm")


async def get_wx(city):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1, "language": "ru"}) as r:
            p = (await r.json())["results"][0]
        if YX_KEY:  # Яндекс Погода, при ошибке падаем на Open-Meteo
            try:
                async with s.get("https://api.weather.yandex.ru/v2/forecast", headers={"X-Yandex-Weather-Key": YX_KEY},
                                 params={"lat": p["latitude"], "lon": p["longitude"], "lang": "ru_RU", "limit": 1}) as r:
                    if r.status == 200:
                        f = (await r.json())["fact"]
                        text, emoji, kind = YX.get(f.get("condition"), ("Облачно", "☁️", "cloud"))
                        return {"city": p["name"], "temp": round(f["temp"]), "feels": round(f["feels_like"]),
                                "humidity": round(f["humidity"]), "wind": round(f["wind_speed"]),
                                "pressure": round(f["pressure_mm"]), "text": text, "emoji": emoji, "kind": kind,
                                "night": f.get("daytime") == "n"}
                    print("yandex weather status", r.status)
            except Exception as e:
                print("yandex weather error", e)
        async with s.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto", "wind_speed_unit": "ms",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,pressure_msl,wind_speed_10m,weather_code,is_day"}) as r:
            c = (await r.json())["current"]
    text, emoji, kind = WX.get(c["weather_code"], ("Облачно", "☁️", "cloud"))
    return {"city": p["name"], "temp": round(c["temperature_2m"]), "feels": round(c["apparent_temperature"]),
            "humidity": round(c["relative_humidity_2m"]), "wind": round(c["wind_speed_10m"]),
            "pressure": round(c["pressure_msl"] * 0.75006), "text": text, "emoji": emoji, "kind": kind,
            "night": not c["is_day"]}


@app.get("/api/weather")
async def api_weather(uid: int = Depends(me)):
    city = user(uid)["city"]
    if not city:
        raise HTTPException(400, "Город не указан")
    try:
        return await get_wx(city)
    except Exception as e:
        print("weather error", e)
        raise HTTPException(502, "Не удалось получить погоду")


class ProfileIn(BaseModel):
    name: str = ""


@app.put("/api/profile")
def put_profile(b: ProfileIn, uid: int = Depends(me)):
    ex("UPDATE users SET name=? WHERE id=?", (b.name.strip()[:40], uid))
    return {"ok": True}


# ---------- контрольные и «когда-нибудь» ----------
def exam_list(uid):
    t = now_of(uid).date()
    out = rows("SELECT id,subject,day FROM exams WHERE user_id=? AND day>=? ORDER BY day", (uid, t.isoformat()))
    for e in out:
        e["left"] = (date.fromisoformat(e["day"]) - t).days
    return out


class ExamIn(BaseModel):
    subject: str
    day: str


class TitleIn(BaseModel):
    title: str


@app.get("/api/exams")
def get_exams(uid: int = Depends(me)):
    return exam_list(uid)


@app.post("/api/exams")
def add_exam(b: ExamIn, uid: int = Depends(me)):
    if not b.subject.strip():
        raise HTTPException(400, "Укажи предмет")
    date.fromisoformat(b.day)
    return {"id": ex("INSERT INTO exams(user_id,subject,day) VALUES(?,?,?)", (uid, b.subject.strip()[:80], b.day))}


@app.delete("/api/exams/{eid}")
def del_exam(eid: int, uid: int = Depends(me)):
    ex("DELETE FROM exams WHERE id=? AND user_id=?", (eid, uid))
    return {"ok": True}


@app.get("/api/someday")
def get_someday(uid: int = Depends(me)):
    return rows("SELECT id,title FROM someday WHERE user_id=? ORDER BY id", (uid,))


@app.post("/api/someday")
def add_someday(b: TitleIn, uid: int = Depends(me)):
    if not b.title.strip():
        raise HTTPException(400, "Название пустое")
    return {"id": ex("INSERT INTO someday(user_id,title) VALUES(?,?)", (uid, b.title.strip()[:120]))}


@app.delete("/api/someday/{sid}")
def del_someday(sid: int, uid: int = Depends(me)):
    ex("DELETE FROM someday WHERE id=? AND user_id=?", (sid, uid))
    return {"ok": True}


@app.post("/api/someday/{sid}/move")
def move_someday(sid: int, day: str = "", uid: int = Depends(me)):
    r = rows("SELECT title FROM someday WHERE id=? AND user_id=?", (sid, uid))
    if not r:
        raise HTTPException(404, "Не найдено")
    d = day or now_of(uid).date().isoformat()
    date.fromisoformat(d)
    ex("INSERT INTO tasks(user_id,day,title) VALUES(?,?,?)", (uid, d, r[0]["title"]))
    ex("DELETE FROM someday WHERE id=?", (sid,))
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
        w = await get_wx(city)
        return f"{w['emoji']} {w['city']}: {w['temp']}°, {w['text']}, ветер {w['wind']} м/с"
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
        hi = "Доброе утро" + (", " + u["name"] if u.get("name") else "") + "!\n\n"
        text = hi + (w + "\n\n" if w else "") + text + "\n\n💬 " + QUOTES[now.toordinal() % len(QUOTES)]
        await bot.send_message(uid, text, reply_markup=kb())

    if due(now, u["morning"]):
        for e in exam_list(uid):
            if e["left"] in (3, 1, 0) and mark(uid, f"{d}:exam{e['id']}"):
                when = {3: "через 3 дня", 1: "завтра", 0: "сегодня"}[e["left"]]
                await bot.send_message(uid, f"📝 Контрольная {when}: {e['subject']}", reply_markup=kb())

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


# ---------- команды в чате ----------
def menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="📅 План"), KeyboardButton(text="📝 Дела")],
        [KeyboardButton(text="🌤 Погода"), KeyboardButton(text="➕ Добавить")]])


def now_of(uid):
    return datetime.now(ZoneInfo(user(uid)["tz"]))


def plan_text(uid):
    n = now_of(uid)
    d = n.date().isoformat()
    ls = lessons(uid, n.weekday())
    ts = rows("SELECT title,at,done FROM tasks WHERE user_id=? AND day=? ORDER BY at='',at,id", (uid, d))
    a = "📚 Уроки:\n" + "\n".join(f"{i}. {l}" for i, l in enumerate(ls, 1)) if ls else "📚 Уроков нет"
    b = ("📝 Дела:\n" + "\n".join(("✅ " if t["done"] else "▫️ ") + (t["at"] + " " if t["at"] else "") + t["title"]
                                  for t in ts)) if ts else "📝 Дел на сегодня нет"
    return f"{n.strftime('%d.%m.%Y')}\n\n{a}\n\n{b}"


def tasks_kb(uid):
    d = now_of(uid).date().isoformat()
    ts = rows("SELECT id,title FROM tasks WHERE user_id=? AND day<=? AND done=0 ORDER BY day,at", (uid, d))
    return ts, InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ " + t["title"][:28], callback_data=f"done:{t['id']}"),
        InlineKeyboardButton(text="→ завтра", callback_data=f"pp:{t['id']}")] for t in ts])


def register(dp):
    @dp.message(Command("plan"))
    @dp.message(F.text == "📅 План")
    async def _plan(m: Message):
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (m.from_user.id,))
        await m.answer(plan_text(m.from_user.id), reply_markup=kb())

    @dp.message(Command("tasks"))
    @dp.message(F.text == "📝 Дела")
    async def _tasks(m: Message):
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (m.from_user.id,))
        ts, k = tasks_kb(m.from_user.id)
        await m.answer("Невыполненные дела:" if ts else "Невыполненных дел нет 🎉", reply_markup=k if ts else None)

    @dp.message(Command("add"))
    @dp.message(F.text == "➕ Добавить")
    async def _add(m: Message):
        uid = m.from_user.id
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
        t = (m.text or "").replace("/add", "", 1).strip()
        if not t or t.startswith("➕"):
            return await m.answer("Напиши так: /add Купить хлеб 18:30 (время можно не указывать)")
        at, p = "", t.rsplit(" ", 1)
        if len(p) == 2 and ":" in p[1]:
            try:
                datetime.strptime(p[1], "%H:%M")
                at, t = p[1], p[0]
            except ValueError:
                pass
        ex("INSERT INTO tasks(user_id,day,title,at) VALUES(?,?,?,?)", (uid, now_of(uid).date().isoformat(), t, at))
        await m.answer("Добавлено: " + t)

    @dp.message(Command("weather"))
    @dp.message(F.text == "🌤 Погода")
    async def _weather(m: Message):
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (m.from_user.id,))
        city = user(m.from_user.id)["city"]
        if not city:
            return await m.answer("Укажи город: /city Москва")
        try:
            w = await get_wx(city)
            await m.answer(f"{w['emoji']} {w['city']}: {w['temp']}°, {w['text']}\n"
                           f"Ощущается {w['feels']}°, влажность {w['humidity']}%, ветер {w['wind']} м/с")
        except Exception:
            await m.answer("Не удалось получить погоду")

    @dp.message(Command("city"))
    async def _city(m: Message):
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (m.from_user.id,))
        c = (m.text or "").replace("/city", "", 1).strip()[:80]
        if not c:
            return await m.answer("Напиши: /city Москва")
        ex("UPDATE users SET city=? WHERE id=?", (c, m.from_user.id))
        await m.answer("Город сохранён: " + c)

    @dp.message(Command("name"))
    async def _name(m: Message):
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (m.from_user.id,))
        n = (m.text or "").replace("/name", "", 1).strip()[:40]
        if not n:
            return await m.answer("Напиши: /name Аня")
        ex("UPDATE users SET name=? WHERE id=?", (n, m.from_user.id))
        await m.answer(f"Буду называть тебя {n}")

    @dp.message(Command("help"))
    async def _help(m: Message):
        await m.answer("/plan — план на сегодня\n/tasks — невыполненные дела (кнопки ✅ и → завтра)\n"
                       "/add текст [ЧЧ:ММ] — добавить дело\n/weather — погода\n/city Город — город для погоды\n"
                       "/name Имя — как к тебе обращаться\n/exam Предмет 25.11 — контрольная, /exams — список\n/later текст — отложить «на когда-нибудь», /later — список", reply_markup=menu())

    @dp.message(Command("exam"))
    async def _exam(m: Message):
        uid = m.from_user.id
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
        t = (m.text or "").replace("/exam", "", 1).strip()
        p = t.rsplit(" ", 1)
        try:
            if len(p) != 2:
                raise ValueError
            d = datetime.strptime(p[1], "%d.%m.%Y" if p[1].count(".") == 2 else "%d.%m")
            if p[1].count(".") == 1:
                d = d.replace(year=now_of(uid).year)
            ex("INSERT INTO exams(user_id,subject,day) VALUES(?,?,?)", (uid, p[0][:80], d.date().isoformat()))
            await m.answer(f"Контрольная добавлена: {p[0]}, {d.strftime('%d.%m.%Y')}. Напомню за 3 дня и за день.")
        except ValueError:
            await m.answer("Напиши так: /exam Математика 25.11")

    @dp.message(Command("exams"))
    async def _exams(m: Message):
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (m.from_user.id,))
        es = exam_list(m.from_user.id)
        await m.answer("\n".join(f"📝 {e['subject']} — {date.fromisoformat(e['day']).strftime('%d.%m')} (осталось дней: {e['left']})"
                                  for e in es) if es else "Контрольных нет. Добавить: /exam Математика 25.11")

    @dp.message(Command("later"))
    async def _later(m: Message):
        uid = m.from_user.id
        ex("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
        t = (m.text or "").replace("/later", "", 1).strip()
        if t:
            ex("INSERT INTO someday(user_id,title) VALUES(?,?)", (uid, t[:120]))
            return await m.answer("Добавлено в «когда-нибудь»: " + t)
        rs = rows("SELECT id,title FROM someday WHERE user_id=? ORDER BY id", (uid,))
        if not rs:
            return await m.answer("Список пуст. Добавить: /later Выучить гитару")
        await m.answer("Когда-нибудь (нажми, чтобы перенести на сегодня):", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="→ " + r["title"][:40], callback_data=f"sd:{r['id']}")] for r in rs]))

    @dp.callback_query(F.data.startswith("sd:"))
    async def _sd(c: CallbackQuery):
        uid = c.from_user.id
        r = rows("SELECT title FROM someday WHERE id=? AND user_id=?", (int(c.data[3:]), uid))
        if r:
            ex("INSERT INTO tasks(user_id,day,title) VALUES(?,?,?)", (uid, now_of(uid).date().isoformat(), r[0]["title"]))
            ex("DELETE FROM someday WHERE id=?", (int(c.data[3:]),))
        await c.message.edit_text("Перенесено на сегодня ✅" if r else "Уже перенесено")
        await c.answer()

    async def refresh(c: CallbackQuery):
        ts, k = tasks_kb(c.from_user.id)
        await c.message.edit_text("Невыполненные дела:" if ts else "Все дела выполнены 🎉", reply_markup=k if ts else None)
        await c.answer()

    @dp.callback_query(F.data.startswith("done:"))
    async def _done(c: CallbackQuery):
        ex("UPDATE tasks SET done=1 WHERE id=? AND user_id=?", (int(c.data[5:]), c.from_user.id))
        await refresh(c)

    @dp.callback_query(F.data.startswith("pp:"))
    async def _pp(c: CallbackQuery):
        uid, tid = c.from_user.id, int(c.data[3:])
        r = rows("SELECT day FROM tasks WHERE id=? AND user_id=?", (tid, uid))
        if r:
            d = max(date.fromisoformat(r[0]["day"]), now_of(uid).date()) + timedelta(days=1)
            ex("UPDATE tasks SET day=? WHERE id=?", (d.isoformat(), tid))
        await refresh(c)


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
        await m.answer("Кнопки меню внизу, все команды: /help", reply_markup=menu())

    register(dp)
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in [
        ("plan", "План на сегодня"), ("tasks", "Невыполненные дела"), ("add", "Добавить дело"),
        ("exams", "Контрольные"), ("later", "Когда-нибудь"), ("weather", "Погода"), ("city", "Город для погоды"), ("name", "Как к тебе обращаться"), ("help", "Помощь")]])

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning"))
    await asyncio.gather(dp.start_polling(bot, handle_signals=False), server.serve(), scheduler(bot))


if __name__ == "__main__":
    asyncio.run(main())
