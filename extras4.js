(() => {
const app = document.getElementById("app");
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
const st = document.createElement("style");
st.textContent = `.sch-day{margin-bottom:12px}.sch-day.today{box-shadow:0 0 0 2px var(--g1),0 10px 30px rgba(0,0,0,.18)!important}
.sch-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.sch-badge{font-size:11px;font-weight:800;padding:3px 9px;border-radius:99px;background:linear-gradient(135deg,var(--g1),var(--g2));color:#fff}
.sch-les{display:flex;align-items:center;gap:11px;padding:7px 0}.sch-ico{width:38px;height:38px;display:grid;place-items:center;flex:none;border-radius:13px;font-size:20px;background:var(--glass);border:1px solid var(--glassline)}
.sch-name{font-weight:650;overflow-wrap:anywhere}.sch-time{font-size:12px;color:var(--muted)}.sch-none{color:var(--muted);font-size:14px;padding:4px 0}
.sch-edit{width:100%;margin-top:4px}`;
document.head.appendChild(st);

function build() {
  const tas = DAYS.map((_, i) => app.querySelector("#schedule-" + i));
  if (tas.some(t => !t) || app.querySelector(".sch-view")) return;
  const form = tas[0].closest("section.card"), emo = window.ppEmo || (() => "📘");
  const today = (new Date().getDay() + 6) % 7;
  const view = document.createElement("div");
  view.className = "sch-view";
  view.innerHTML = DAYS.map((d, i) => {
    const ls = tas[i].value.split("\n").map(x => x.trim()).filter(Boolean);
    return `<section class="card sch-day${i === today ? " today" : ""}"><div class="sch-head"><h2 class="card-title">${d}</h2>${i === today ? '<span class="sch-badge">сегодня</span>' : ""}</div>` +
      (ls.length ? ls.map(l => {
        const m = /^(\d{1,2}[:.]\d{2})\s+(.+)$/.exec(l), name = m ? m[2] : l;
        return `<div class="sch-les"><div class="sch-ico">${emo(name)}</div><div><div class="sch-name">${esc(name)}</div>${m ? `<div class="sch-time">${esc(m[1])}</div>` : ""}</div></div>`;
      }).join("") : '<div class="sch-none">Уроков нет</div>') + "</section>";
  }).join("") + '<button class="primary-btn sch-edit" type="button">✏️ Изменить расписание</button>';
  form.style.display = "none";
  form.before(view);
  const hint = app.querySelector(".hero-text");
  if (hint) hint.textContent = "Уроки по дням недели. Чтобы поправить, нажми кнопку внизу.";
  view.querySelector(".sch-edit").onclick = () => {
    view.style.display = "none"; form.style.display = "";
    if (hint) hint.textContent = "Каждый урок с новой строки. Время можно указать в начале: «08:30 Математика».";
    window.scrollTo(0, 0);
  };
}

document.addEventListener("click", e => {
  if (!e.target.closest("#save-schedule-button")) return;
  setTimeout(() => {
    const t = document.getElementById("toast");
    if (!(t && t.classList.contains("error")) && window.Planner) window.Planner.reload();
  }, 900);
});

new MutationObserver(build).observe(app, {childList: true});
build();
})();
