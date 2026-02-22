const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
let MAX_PAST_WEEKS = 4;
let allData = {};
let weekOffset = 0;

function formatHours(h) {
    if (h === null || h === undefined) return "—";
    const hrs = Math.floor(h);
    const mins = Math.round((h - hrs) * 60);
    if (hrs === 0) return `${mins}m`;
    if (mins === 0) return `${hrs}h`;
    return `${hrs}h ${mins}m`;
}

function formatTime(t) {
    if (!t) return "—";
    return t;
}

function getMonday(d) {
    const date = new Date(d);
    const day = date.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    date.setDate(date.getDate() + diff);
    return date;
}

function dateStr(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}

function addDays(d, n) {
    const r = new Date(d);
    r.setDate(r.getDate() + n);
    return r;
}

function todayStr() {
    return dateStr(new Date());
}

function getWeekStart() {
    const monday = getMonday(new Date());
    return addDays(monday, weekOffset * 7);
}

function formatWeekLabel(monday) {
    const sunday = addDays(monday, 6);
    const mStr = `${MONTH_NAMES[monday.getMonth()]} ${monday.getDate()}`;
    const sStr = `${MONTH_NAMES[sunday.getMonth()]} ${sunday.getDate()}, ${sunday.getFullYear()}`;
    return `${mStr} — ${sStr}`;
}

function statusDot(val) {
    if (val === true) return `<span class="status-dot done"></span>`;
    if (val === false) return `<span class="status-dot missed"></span>`;
    return `<span class="status-dot pending"></span>`;
}

function combinedRoutineDot(a, b) {
    if (a === true && b === true) return `<span class="status-dot done"></span>`;
    if (a === true || b === true) return `<span class="status-dot partial"></span>`;
    if (a === false || b === false) return `<span class="status-dot missed"></span>`;
    return `<span class="status-dot pending"></span>`;
}

function rateWork(h) {
    if (h === null || h === undefined) return "na";
    if (h < 4) return "bad";
    if (h < 8) return "warn";
    return "good";
}

function rateUnendorsed(h) {
    if (h === null || h === undefined) return "na";
    if (h < 0.5) return "good";
    if (h < 1) return "warn";
    return "bad";
}

function rateUntracked(h) {
    if (h === null || h === undefined) return "na";
    if (h < 1) return "good";
    if (h < 2) return "warn";
    return "bad";
}

function rateSleep(h) {
    if (h === null || h === undefined) return "na";
    if (h < 7) return "bad";
    if (h < 8) return "warn";
    if (h <= 9) return "good";
    if (h <= 10) return "warn";
    return "bad";
}

function timeToMinutes(t) {
    if (!t) return null;
    const [h, m] = t.split(":").map(Number);
    return h * 60 + m;
}

function rateWakeTime(t) {
    const mins = timeToMinutes(t);
    if (mins === null) return "na";
    if (mins < 240) return "bad";
    if (mins < 300) return "warn";
    if (mins < 360) return "good";
    if (mins < 420) return "warn";
    return "bad";
}

function rateBedTime(t) {
    const mins = timeToMinutes(t);
    if (mins === null) return "na";
    const adj = mins < 720 ? mins + 1440 : mins;
    if (adj < 1200) return "bad";
    if (adj < 1260) return "warn";
    if (adj < 1320) return "good";
    if (adj < 1380) return "warn";
    return "bad";
}

function renderSection(title, rows, startExpanded) {
    const collapsed = startExpanded ? "" : " collapsed";
    const rowsHtml = rows.map(([label, valueHtml]) =>
        `<div class="metric-row">
            <span class="metric-label">${label}</span>
            <span class="metric-value">${valueHtml}</span>
        </div>`
    ).join("");

    return `<div class="section${collapsed}">
        <div class="section-header" onclick="this.parentElement.classList.toggle('collapsed')">
            <span class="section-title">${title}</span>
            <span class="section-chevron">&#9660;</span>
        </div>
        <div class="section-body">${rowsHtml}</div>
    </div>`;
}

function renderDayCard(date, data, isToday, isFuture) {
    const d = new Date(date + "T12:00:00");
    const dayName = DAY_NAMES[((d.getDay() + 6) % 7)];
    const dayNum = d.getDate();

    const headerHtml = `<div class="day-header">
        <span class="day-name">${dayName}</span>
        <span class="day-date">${dayNum}</span>
    </div>`;

    if (!data || isToday || isFuture) {
        const cls = isToday ? "day-card empty today" : "day-card empty";
        return `<div class="${cls}">${headerHtml}<div class="empty-label">No data</div></div>`;
    }

    const todoist = data.todoist || {};

    const timeSection = renderSection("Time", [
        ["Work", `<span class="${rateWork(data.work_hours)}">${formatHours(data.work_hours)}</span>`],
        ["Sleep", `<span class="${rateSleep(data.sleep_hours)}">${formatHours(data.sleep_hours)}</span>`],
        ["Unendorsed", `<span class="${rateUnendorsed(data.unendorsed_hours)}">${formatHours(data.unendorsed_hours)}</span>`],
        ["Untracked", `<span class="${rateUntracked(data.untracked_hours)}">${formatHours(data.untracked_hours)}</span>`],
    ], true);

    const routineSection = renderSection("Routines", [
        ["Wake time", `<span class="${rateWakeTime(data.wake_time)}">${formatTime(data.wake_time)}</span>`],
        ["Morning", combinedRoutineDot(todoist["Morning Hygiene"], todoist["Morning OODA"])],
        ["Night", combinedRoutineDot(todoist["Night Hygiene"], todoist["Night OODA"])],
        ["Bed time", `<span class="${rateBedTime(data.bedtime)}">${formatTime(data.bedtime)}</span>`],
    ], true);

    const cls = isToday ? "day-card today" : "day-card";
    return `<div class="${cls}">
        ${headerHtml}
        ${timeSection}
        ${routineSection}
    </div>`;
}

function updateNavButtons() {
    document.getElementById("prev-week").disabled = weekOffset <= -MAX_PAST_WEEKS;
    document.getElementById("next-week").disabled = weekOffset >= 0;
}

function renderWeek() {
    const monday = getWeekStart();
    const today = todayStr();
    const grid = document.getElementById("week-grid");
    const label = document.getElementById("week-label");

    label.textContent = formatWeekLabel(monday);

    let html = "";
    for (let i = 0; i < 7; i++) {
        const d = addDays(monday, i);
        const ds = dateStr(d);
        const isToday = ds === today;
        const isFuture = ds > today;
        const data = allData[ds] || null;
        html += renderDayCard(ds, data, isToday, isFuture);
    }
    grid.innerHTML = html;
    updateNavButtons();
}

async function main() {
    const resp = await fetch("data/metrics.json");
    if (!resp.ok) return;
    const data = await resp.json();

    if (data.max_past_weeks != null) MAX_PAST_WEEKS = data.max_past_weeks;

    for (const day of (data.days || [])) {
        allData[day.date] = day;
    }

    renderWeek();

    document.getElementById("prev-week").addEventListener("click", () => {
        if (weekOffset > -MAX_PAST_WEEKS) {
            weekOffset--;
            renderWeek();
        }
    });
    document.getElementById("next-week").addEventListener("click", () => {
        if (weekOffset < 0) {
            weekOffset++;
            renderWeek();
        }
    });
}

main();
