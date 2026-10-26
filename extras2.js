(() => {
const tg = window.Telegram && window.Telegram.WebApp, app = document.getElementById("app");
const hdr = () => ({"Content-Type": "application/json", "X-Init-Data": tg ? tg.initData : ""});
const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) {} return null; };
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const G = {neon: ["Неон", "#e300df", "#3900f6"], candy: ["Сирень", "#c22de0", "#5dfae0"], ocean: ["Океан", "#36D1DC", "#5B86E5"],
  flame: ["Пламя", "#DC2626", "#DB2777"], aqua: ["Аква", "#0F766E", "#22D3EE"], berry: ["Ягода", "#9333EA", "#FB7185"], cotton: ["Вата", "#7AA8FF", "#FF9AEF"]};
const F = {sys: ["Системный", '-apple-system,"Segoe UI",sans-serif'], nunito: ["Скруглённый", "Nunito,sans-serif"], comf: ["Мягкий", "Comfortaa,sans-serif"],
  serif: ["Строгий", '"Playfair Display",serif'], hand: ["Рукописный", "Caveat,cursive"]};
const QUOTES = ["Маленький шаг сегодня лучше большого плана на потом.", "Не нужно делать всё сразу, нужно начать.", "Ты справлялся с трудным, справишься и с этим.",
  "Лучше сделать неидеально, чем не сделать совсем.", "Отдых тоже часть плана.", "Каждая галочка делает день легче.", "Сложное делается по частям."];
const EMO = [[/матем|алгебр|геометр/i, "📐"], [/физкульт|физ-ра|физра/i, "⚽"], [/русск|родн/i, "📖"], [/литер/i, "📚"], [/англ|иностр|немец|франц/i, "🌍"],
  [/истори/i, "🏛"], [/общество|обществ/i, "⚖️"], [/географ/i, "🗺"], [/биолог/i, "🧬"], [/хими/i, "🧪"], [/физик/i, "🔬"], [/информат/i, "💻"],
  [/музык/i, "🎵"], [/изо|рисов/i, "🎨"], [/технолог|труд/i, "🛠"], [/обж|безопас/i, "🦺"], [/класс.*час|разговор/i, "💬"]];
const emo = t => (EMO.find(e => e[0].test(t)) || [0, "📘"])[1];
window.ppEmo = emo;

const fl = document.createElement("link");
fl.rel = "stylesheet";
fl.href = "https://fonts.googleapis.com/css2?family=Nunito:wght@400;700&family=Comfortaa:wght@400;700&family=Playfair+Display:wght@400;700&family=Caveat:wght@400;700&display=swap&subset=cyrillic";
document.head.appendChild(fl);

const st = document.createElement("style");
st.textContent = `html{filter:none!important}
:root{--glass:rgba(255,255,255,.1);--glassline:rgba(255,255,255,.22);--text:#fff;--muted:rgba(255,255,255,.68)}
html[data-mode=light]{--glass:rgba(255,255,255,.55);--glassline:rgba(255,255,255,.8);--text:#14142b;--muted:#55587a}
body{color:var(--text)!important;font-family:var(--font,inherit)!important;background:linear-gradient(160deg,color-mix(in srgb,var(--g1) 34%,#07070f),color-mix(in srgb,var(--g2) 34%,#07070f)) fixed!important}
html[data-mode=light] body{background:linear-gradient(160deg,color-mix(in srgb,var(--g1) 30%,#fff),color-mix(in srgb,var(--g2) 30%,#fff)) fixed!important}
button,input,textarea{font-family:inherit}
.card,.stat,.nav{background:var(--glass)!important;border:1px solid var(--glassline)!important;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:0 10px 30px rgba(0,0,0,.18)!important}
input[type=text],input[type=time],input[type=number],textarea{background:var(--glass)!important;border-color:var(--glassline)!important;color:var(--text)!important}
.primary-btn{background:linear-gradient(135deg,var(--g1),var(--g2))!important;color:#fff!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.4),0 8px 24px color-mix(in srgb,var(--g1) 45%,transparent)!important}
.secondary-btn,.icon-btn,.pp-chip{background:var(--glass)!important;color:var(--text)!important;border:1px solid var(--glassline)!important;backdrop-filter:blur(14px);box-shadow:inset 0 1px 0 rgba(255,255,255,.3)}
.brand-mark,.progress-fill{background:linear-gradient(135deg,var(--g1),var(--g2))!important}
.hero-text,.progress-label,.stat-label,.card-caption,.kicker,.brand-subtitle,.settings-note,.empty,.profile-user{color:var(--muted)!important}
.field-label,.schedule-day-name,.lesson-text,.task-title,.date-name,.card-title{color:var(--text)!important}
.lesson-index{background:var(--glass)!important;color:var(--text)!important;font-size:16px!important}
.nav{grid-template-columns:repeat(5,1fr)!important}.nav-btn{color:var(--muted)!important}
.nav-btn.active{color:var(--text)!important;background:var(--glass)!important;box-shadow:inset 0 0 0 1px var(--glassline)!important}
.task-checkbox:checked{background:linear-gradient(135deg,var(--g1),var(--g2))!important;border-color:transparent!important}
.dots{display:flex;flex-wrap:wrap;gap:12px}.gd{width:40px;height:40px;border-radius:50%;border:3px solid transparent;padding:0}.gd.on,.pp-chip.on{border-color:var(--text)!important}
.pp-chip{padding:9px 14px;border-radius:14px;margin:0 8px 8px 0}
#wx-bg{position:fixed;inset:0;z-index:-1;overflow:hidden}#wx-bg::before,#wx-bg::after{content:"";position:absolute;inset:-30% 0 0}
.wx-rain,.wx-storm{background:linear-gradient(#0b1623,#22364d)}
.wx-rain::before,.wx-storm::before{background:linear-gradient(105deg,transparent 48%,rgba(190,215,255,.6) 49% 51%,transparent 52%);background-size:34px 70px;animation:fall .45s linear infinite}
.wx-storm::after{background:#fff;opacity:0;animation:flash 6s infinite}
.wx-snow{background:linear-gradient(#26364d,#5b7391)}
.wx-snow::before{background:radial-gradient(circle,#fff 0 2.5px,transparent 3.5px) 0 0/55px 55px,radial-gradient(circle,#fff 0 1.5px,transparent 2.5px) 20px 30px/37px 37px;animation:snow 7s linear infinite}
.wx-clear{background:linear-gradient(#2f8bff,#a5e4ff)}.wx-clear.night{background:linear-gradient(#050b1f,#1a2550)}
.wx-clear::before{inset:auto;top:6%;right:8%;width:130px;height:130px;border-radius:50%;background:radial-gradient(circle,#fff6b0,#ffd44d 45%,transparent 70%);animation:pulse 4s ease-in-out infinite}
.wx-clear.night::before{background:radial-gradient(circle,#f4f1d8 0 30%,transparent 32%);width:70px;height:70px}
.wx-clear.night::after{background:radial-gradient(circle,#fff 0 1px,transparent 2px) 0 0/70px 70px,radial-gradient(circle,#fff 0 1px,transparent 2px) 30px 40px/90px 90px;animation:pulse 3s infinite}
.wx-cloud{background:linear-gradient(#52627a,#93a3b8)}.wx-fog{background:linear-gradient(#aab4bf,#d8dde2)}
.wx-cloud::before,.wx-fog::before{inset:20% -40% auto;height:160px;border-radius:80px;background:rgba(255,255,255,.35);filter:blur(24px);animation:drift 14s ease-in-out infinite alternate}
.wx-cloud::after,.wx-fog::after{inset:55% -40% auto;height:140px;border-radius:80px;background:rgba(255,255,255,.28);filter:blur(28px);animation:drift 18s ease-in-out infinite alternate-reverse}
@keyframes fall{to{background-position:-17px 70px}}@keyframes snow{to{transform:translateY(55px)}}@keyframes flash{0%,92%,100%{opacity:0}94%{opacity:.8}96%{opacity:0}97%{opacity:.5}}
@keyframes pulse{50%{transform:scale(1.08);opacity:.85}}@keyframes drift{to{transform:translateX(18%)}}
.wx-t{font-size:64px;font-weight:800;line-height:1}.wx-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.wx-grid div{padding:10px;border-radius:14px;background:var(--glass);border:1px solid var(--glassline)}
.wx-grid b{display:block;font-size:12px;color:var(--muted);font-weight:600}`;
document.head.appendChild(st);

function apply() {
  const g = G[ls("pp_g")] || G.ocean, f = F[ls("pp_f")] || F.sys, r = document.documentElement;
  r.style.setProperty("--g1", g[1]); r.style.setProperty("--g2", g[2]); r.style.setProperty("--accent", g[1]);
  r.style.setProperty("--font", f[1]); r.dataset.mode = ls("pp_m") === "light" ? "light" : "dark";
}
apply();

function hello() {
  const h = new Date().getHours();
  return h < 5 ? "Доброй ночи" : h < 12 ? "Доброе утро" : h < 18 ? "Добрый день" : "Добрый вечер";
}
function name() {
  const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  return ls("pp_n") || (u && u.first_name) || "друг";
}

function enhance() {
  const ht = app.querySelector(".hero-title");
  if (ht) {
    ht.textContent = `${hello()}, ${name()}!`;
    const t = app.querySelector(".hero-text");
    if (t) t.textContent = QUOTES[Math.floor(Date.now() / 864e5) % QUOTES.length];
  }
  app.querySelectorAll(".lesson").forEach(l => {
    const t = l.querySelector(".lesson-text"), i = l.querySelector(".lesson-index");
    if (t && i && !i.dataset.e) { i.dataset.e = 1; i.textContent = emo(t.textContent); }
  });
  app.querySelectorAll(".themes").forEach(x => x.closest("section") && x.closest("section").remove());
  if (app.querySelector("#setting-tz") && !app.querySelector(".pp-set")) {
    const on = (a, b) => a === b ? " on" : "";
    app.insertAdjacentHTML("beforeend", `<section class="card pp-set"><div class="card-title-row"><h2 class="card-title">Оформление</h2></div>
      <label class="field-label" for="pp-name">Как к тебе обращаться</label><input id="pp-name" type="text" value="${esc(ls("pp_n") || "")}" placeholder="Твоё имя">
      <label class="field-label">Тема</label><button class="pp-chip${on(ls("pp_m") || "dark", "dark")}" data-m="dark">Тёмная</button><button class="pp-chip${on(ls("pp_m"), "light")}" data-m="light">Светлая</button>
      <label class="field-label">Градиент</label><div class="dots">${Object.entries(G).map(([k, v]) =>
        `<button class="gd${on(ls("pp_g") || "ocean", k)}" data-g="${k}" aria-label="${v[0]}" style="background:linear-gradient(135deg,${v[1]},${v[2]})"></button>`).join("")}</div>
      <label class="field-label">Шрифт</label>${Object.entries(F).map(([k, v]) =>
        `<button class="pp-chip${on(ls("pp_f") || "sys", k)}" data-f="${k}" style="font-family:${v[1]}">${v[0]}</button>`).join("")}</section>`);
  }
}

const nav = document.querySelector(".nav");
const wxBtn = document.createElement("button");
wxBtn.type = "button"; wxBtn.className = "nav-btn";
wxBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18a4 4 0 0 1-.5-8A5.5 5.5 0 0 1 17 8.5a4.8 4.8 0 0 1 0 9.5z"></path></svg><span>Погода</span>`;
nav.appendChild(wxBtn);
const bg = () => { const b = document.getElementById("wx-bg"); if (b) b.remove(); };

async function showWx() {
  nav.querySelectorAll(".nav-btn").forEach(b => b.classList.toggle("active", b === wxBtn));
  bg();
  app.innerHTML = `<div class="loading"><span class="spinner"></span><span>Загрузка…</span></div>`;
  try {
    const r = await fetch("/api/weather", {headers: hdr()}), w = await r.json();
    if (!r.ok) throw new Error(w.detail || "Ошибка");
    const d = document.createElement("div");
    d.id = "wx-bg"; d.className = `wx-${w.kind}${w.night ? " night" : ""}`;
    document.body.appendChild(d);
    app.innerHTML = `<section class="card" style="color:#fff"><div class="kicker" style="color:#fff!important">${esc(w.city)}</div>
      <div class="wx-t">${w.temp}°</div><div style="font-size:19px;margin-top:6px">${w.emoji} ${esc(w.text)}</div>
      <div class="wx-grid"><div><b>Ощущается</b>${w.feels}°</div><div><b>Влажность</b>${w.humidity}%</div>
      <div><b>Ветер</b>${w.wind} м/с</div><div><b>Давление</b>${w.pressure} мм</div></div></section>`;
  } catch (e) {
    app.innerHTML = `<section class="card"><h2 class="card-title">Погода</h2><p class="empty">${esc(e.message)}. Город указывается в настройках.</p></section>`;
  }
}

document.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b === wxBtn) return showWx();
  if (b.closest(".nav") || b.dataset.view) { bg(); wxBtn.classList.remove("active"); }
  const set = (k, v) => { ls(k, v); apply(); app.querySelectorAll(`[data-${{pp_g: "g", pp_f: "f", pp_m: "m"}[k]}]`).forEach(x => x.classList.toggle("on", x === b)); };
  if (b.dataset.g) set("pp_g", b.dataset.g);
  if (b.dataset.f) set("pp_f", b.dataset.f);
  if (b.dataset.m) set("pp_m", b.dataset.m);
}, true);

document.addEventListener("change", e => {
  if (e.target.id !== "pp-name") return;
  ls("pp_n", e.target.value.trim());
  fetch("/api/profile", {method: "PUT", headers: hdr(), body: JSON.stringify({name: e.target.value.trim()})}).catch(() => {});
});

new MutationObserver(enhance).observe(app, {childList: true});
enhance();
})();
