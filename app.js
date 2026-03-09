const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
let MAX_PAST_WEEKS = null;
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
    const dot = val === true ? `<span class="status-dot done"></span>`
        : val === false ? `<span class="status-dot missed"></span>`
        : `<span class="status-dot pending"></span>`;
    if (val === null || val === undefined) return dot;
    const n = val === true ? 1 : 0;
    const cls = val === true ? "good" : "bad";
    return `<span class="has-tooltip">${dot}<span class="tooltip"><span class="tooltip-line ${cls}">${n}/1</span></span></span>`;
}

function combinedRoutineDot(a, b) {
    const done = (a === true ? 1 : 0) + (b === true ? 1 : 0);
    let dotCls, tipCls;
    if (a === true && b === true) { dotCls = "done"; tipCls = "good"; }
    else if (a === true || b === true) { dotCls = "partial"; tipCls = "warn"; }
    else if (a === false || b === false) { dotCls = "missed"; tipCls = "bad"; }
    else { dotCls = "pending"; tipCls = "na"; }
    const dot = `<span class="status-dot ${dotCls}"></span>`;
    if (dotCls === "pending") return dot;
    return `<span class="has-tooltip">${dot}<span class="tooltip"><span class="tooltip-line ${tipCls}">${done}/2</span></span></span>`;
}

function rateWork(h) {
    if (h === null || h === undefined) return "na";
    if (h < 6) return "bad";
    if (h < 8) return "warn";
    if (h <= 10) return "good";
    return "great";
}

function rateOther(h) {
    if (h === null || h === undefined) return "na";
    if (h < 3) return "great";
    if (h < 4) return "good";
    if (h <= 6) return "warn";
    return "bad";
}

function rateUnendorsed(h) {
    if (h === null || h === undefined) return "na";
    if (h === 0) return "great";
    if (h < 0.5) return "good";
    if (h < 1) return "warn";
    return "bad";
}

function rateUntracked(h) {
    if (h === null || h === undefined) return "na";
    if (h < 0.5) return "great";
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

function tooltipHtml(lines) {
    return `<span class="tooltip">${lines.map(([text, cls]) =>
        `<span class="tooltip-line ${cls}">${text}</span>`
    ).join("")}</span>`;
}

function withTooltip(valueHtml, lines) {
    return `<span class="has-tooltip">${valueHtml}${tooltipHtml(lines)}</span>`;
}

const GOALS = {
    work: [["> 10h", "great"], ["8h – 10h", "good"], ["6h – 8h", "warn"], ["< 6h", "bad"]],
    sleep: [["> 10h", "bad"], ["9h – 10h", "warn"], ["8h – 9h", "good"], ["7h – 8h", "warn"], ["< 7h", "bad"]],
    other: [["> 6h", "bad"], ["4h – 6h", "warn"], ["3h – 4h", "good"], ["< 3h", "great"]],
    unendorsed: [["> 1h", "bad"], ["30m – 1h", "warn"], ["< 30m", "good"], ["0", "great"]],
    untracked: [["> 2h", "bad"], ["1h – 2h", "warn"], ["30m – 1h", "good"], ["< 30m", "great"]],
    wakeTime: [["> 7:00", "bad"], ["6:00 – 7:00", "warn"], ["5:00 – 6:00", "good"], ["4:00 – 5:00", "warn"], ["< 4:00", "bad"]],
    bedTime: [["> 23:00", "bad"], ["22:00 – 23:00", "warn"], ["21:00 – 22:00", "good"], ["20:00 – 21:00", "warn"], ["< 20:00", "bad"]],
};

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
        ["Work", withTooltip(`<span class="${rateWork(data.work_hours)}">${formatHours(data.work_hours)}</span>`, GOALS.work)],
        ["Sleep", withTooltip(`<span class="${rateSleep(data.sleep_hours)}">${formatHours(data.sleep_hours)}</span>`, GOALS.sleep)],
        ["Other", withTooltip(`<span class="${rateOther(data.other_hours)}">${formatHours(data.other_hours)}</span>`, GOALS.other)],
        ["Unendorsed", withTooltip(`<span class="${rateUnendorsed(data.unendorsed_hours)}">${formatHours(data.unendorsed_hours)}</span>`, GOALS.unendorsed)],
        ["Untracked", withTooltip(`<span class="${rateUntracked(data.untracked_hours)}">${formatHours(data.untracked_hours)}</span>`, GOALS.untracked)],
    ], true);

    const routineSection = renderSection("Routines", [
        ["Wake time", withTooltip(`<span class="${rateWakeTime(data.wake_time)}">${formatTime(data.wake_time)}</span>`, GOALS.wakeTime)],
        ["Morning", combinedRoutineDot(todoist["Morning Hygiene"], todoist["Morning OODA"])],
        ["Night", combinedRoutineDot(todoist["Night Hygiene"], todoist["Night OODA"])],
        ["Bed time", withTooltip(`<span class="${rateBedTime(data.bedtime)}">${formatTime(data.bedtime)}</span>`, GOALS.bedTime)],
    ], true);

    const virtueSection = renderSection("Virtue", [
        ["Fortitude", statusDot(todoist["Fortitude"])],
        ["Eat Healthy", statusDot(todoist["Eat Healthy"])],
    ], true);

    const cls = isToday ? "day-card today" : "day-card";
    return `<div class="${cls}">
        ${headerHtml}
        ${timeSection}
        ${routineSection}
        ${virtueSection}
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

    if (data.max_past_weeks == null) throw new Error("max_past_weeks not found in metrics.json");
    MAX_PAST_WEEKS = data.max_past_weeks;

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
