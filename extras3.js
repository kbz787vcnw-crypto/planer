(() => {
const tg = window.Telegram && window.Telegram.WebApp, app = document.getElementById("app");
const hdr = () => ({"Content-Type": "application/json", "X-Init-Data": tg ? tg.initData : ""});
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const call = (p, m = "GET", b) => fetch("/api/" + p, {method: m, headers: hdr(), body: b ? JSON.stringify(b) : undefined}).then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || "Ошибка"); }));
const reload = () => { if (window.Planner && window.Planner.reload) window.Planner.reload(); };
const left = n => n === 0 ? "сегодня" : n === 1 ? "завтра" : `через ${n} дн.`;
const st = document.createElement("style");
st.textContent = `.x-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--glassline)}.x-row:last-of-type{border-bottom:0}
.x-main{flex:1;min-width:0;overflow-wrap:anywhere}.x-badge{font-size:12px;font-weight:800;padding:4px 9px;border-radius:99px;background:linear-gradient(135deg,var(--g1),var(--g2));color:#fff;white-space:nowrap}
.x-btn{padding:6px 10px;border-radius:10px;font-size:13px;font-weight:700}.x-add{display:flex;gap:8px;margin-top:10px}.x-add input{flex:1;min-width:0}
.x-del{width:30px;height:30px;padding:0;background:transparent;color:var(--muted);font-size:18px}`;
document.head.appendChild(st);

async function fill() {
  const exBox = app.querySelector("#x-ex"), sdBox = app.querySelector("#x-sd");
  if (!exBox || !sdBox) return;
  try {
    const [ex, sd] = await Promise.all([call("exams"), call("someday")]);
    exBox.innerHTML = ex.length ? ex.map(e => `<div class="x-row"><div class="x-main">📝 ${esc(e.subject)}<div class="card-caption">${e.day.split("-").reverse().slice(0, 2).join(".")}</div></div>
      <span class="x-badge">${left(e.left)}</span><button class="x-del" data-xe="${e.id}" aria-label="Удалить">×</button></div>`).join("") : `<div class="empty">Контрольных нет</div>`;
    sdBox.innerHTML = sd.length ? sd.map(s => `<div class="x-row"><div class="x-main">💭 ${esc(s.title)}</div>
      <button class="x-btn secondary-btn" data-sm="${s.id}">→ сегодня</button><button class="x-del" data-sx="${s.id}" aria-label="Удалить">×</button></div>`).join("") : `<div class="empty">Пока пусто</div>`;
  } catch (e) { exBox.innerHTML = sdBox.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

function enhance() {
  if (!app.querySelector(".hero-title") || app.querySelector(".x-cards")) return;
  app.insertAdjacentHTML("beforeend", `<div class="x-cards">
    <section class="card"><div class="card-title-row"><h2 class="card-title">Контрольные</h2></div><div id="x-ex"></div>
      <div class="x-add"><input id="x-subj" type="text" placeholder="Предмет"><input id="x-date" type="date" style="max-width:150px"></div>
      <button class="primary-btn add-submit" id="x-ex-add" type="button">Добавить контрольную</button></section>
    <section class="card"><div class="card-title-row"><h2 class="card-title">Когда-нибудь</h2></div><div id="x-sd"></div>
      <div class="x-add"><input id="x-title" type="text" placeholder="Дело без даты"><button class="primary-btn" id="x-sd-add" type="button" style="min-height:0;padding:0 18px">+</button></div></section></div>`);
  fill();
}

app.addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    if (b.id === "x-ex-add") {
      const s = app.querySelector("#x-subj").value.trim(), d = app.querySelector("#x-date").value;
      if (!s || !d) return;
      await call("exams", "POST", {subject: s, day: d}); app.querySelector(".x-cards").remove(); enhance();
    } else if (b.id === "x-sd-add") {
      const t = app.querySelector("#x-title").value.trim();
      if (!t) return;
      await call("someday", "POST", {title: t}); app.querySelector(".x-cards").remove(); enhance();
    } else if (b.dataset.xe) { await call("exams/" + b.dataset.xe, "DELETE"); fill(); }
    else if (b.dataset.sx) { await call("someday/" + b.dataset.sx, "DELETE"); fill(); }
    else if (b.dataset.sm) { await call(`someday/${b.dataset.sm}/move`, "POST"); reload(); }
  } catch (err) { if (tg && tg.showAlert) tg.showAlert(err.message); }
});

new MutationObserver(enhance).observe(app, {childList: true});
enhance();
})();
