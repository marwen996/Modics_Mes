(function () {
  // Tableau de bord MODICS. Les données viennent de /api/summary, /api/stops, /api/daily.
  // Tout texte issu des données est inséré via textContent (aucun HTML interprété).
  const M = window.MODICS;
  const $ = (id) => document.getElementById(id);

  // ---------- Traductions (textes fixes : data-i18n dans index.html) ----------
  const I18N = {
    fr: {
      locale: "fr-FR", title: "Tableau de bord", subtitle: "Atelier moulage · suivi des presses",
      connecting: "Connexion…", online: (t) => `À jour · ${t}`, db_down: (t) => `Base injoignable — données du ${t}`,
      offline: "Hors ligne — nouvelle tentative…",
      all_f: "Toutes", all_shifts: "Toutes les équipes", p_today: "Dernier jour", p_7: "7 jours", p_30: "30 jours", p_all: "Tout",
      k_oee: "TRS moyen (OEE)", k_av: "Disponibilité", k_pf: "Performance", k_ql: "Qualité", k_good: "Pièces bonnes",
      k_rej: "Rebuts", k_run: "Temps de marche", k_down: "Temps d'arrêt", k_stops: "Arrêts enregistrés",
      stops_val: (n, m) => `${n} · ${m} min`, vs_prev: "par rapport à la période précédente de même durée",
      grid_title: "TRS par jour et par équipe", lg_good: "≥ 85 %", lg_warn: "60 – 85 %", lg_bad: "< 60 %", lg_idle: "Pas de production",
      no_data: "Aucune donnée pour ces filtres.", idle: "arrêt", pcs: "pcs", shift_short: (s) => s.replace("Shift ", "Éq. "),
      cell_title: (a, p, q) => `Dispo ${a} · Perf ${p} · Qual ${q}`,
      c_trend: "Évolution du TRS par équipe", c_codes: "Causes d'arrêt (minutes)", c_machine: "Marche / arrêt par machine (min)", c_day: "Arrêts par jour",
      ds_minutes: "Minutes", ds_run: "Marche", ds_stop: "Arrêt", ds_stop_min: "Minutes d'arrêt", ds_count: "Nombre d'arrêts",
      n_stops: (n) => `${n} arrêt(s)`, n_rows: (n) => `${n} ligne(s)`,
      t_stops: "Journal des arrêts", t_daily: "Production par équipe",
      th_machine: "Machine", th_start: "Début", th_end: "Fin", th_dur: "Durée (min)", th_code: "Code", th_shift: "Équipe", th_part: "Réf. pièce",
      th_setter: "Régleur", th_day: "Jour prod.", th_date: "Horodatage", th_run: "Marche", th_down: "Arrêt", th_good: "Bonnes", th_rej: "Rebuts",
      th_cycle: "Cycle (s)", th_av: "Dispo", th_pf: "Perf", th_ql: "Qual", th_oee: "TRS",
      no_stops: "Aucun arrêt sur cette période.", none: "Aucune donnée.",
      bad_ts: "Horodatage incohérent (fin avant début ou > 24 h) : exclu des totaux",
      ai_title: "Analyse IA · Claude", ai_run: "Analyser la période", ai_rerun: "Relancer l'analyse", ai_running: "Analyse en cours…",
      ai_hint: "Cliquez sur « Analyser la période » pour obtenir un résumé, des alertes, des prévisions et des actions sur les données filtrées.",
      ai_ph: "Posez une question sur les données… ex. : pourquoi le TRS de l'équipe C est-il plus bas ?", ai_ask: "Demander",
      ai_thinking: "Claude réfléchit…", ai_alerts: "Alertes", ai_pred: "Prévisions", ai_actions: "Actions", ai_none: "Rien à signaler.",
      ai_trend: (d, c) => `Tendance TRS : ${d} — ${c}`, ai_sev: (s) => `Gravité : ${s}`, ai_prio: (s) => `Priorité : ${s}`,
      ai_conf: (c, j) => `Confiance ${c} — ${j}`, ai_meta: (cached, t, m) => `${cached ? "Analyse en cache" : "Généré"} le ${t} · ${m}`,
      sev: { haute: "Haute", moyenne: "Moyenne", basse: "Basse" }, srv_err: (s) => `Erreur serveur (${s})`,
      i50: "Industrie 5.0", scrap: "de rebut",
      th_btn: "Seuils", th_good: "Vert dès", th_warn: "Orange dès", th_reset: "Réinitialiser", th_err: "Le seuil orange doit être inférieur au seuil vert.",
      fp_attention: "À traiter en priorité", fp_cause: "Cause d'arrêt dominante", fp_shifts: "Équipes · TRS pondéré",
      fp_day: (d) => `Dernier jour : ${d}`, fp_ok: (n) => `Aucune équipe sous ${n} % le dernier jour. Bon travail.`, fp_weak: (n) => `Point faible : ${n}`,
      fp_share: (p, n) => `${p} % du temps d'arrêt · ${n} arrêt(s)`, fp_ref: "Référence", fp_support: "À soutenir", fp_no_stop: "Aucun arrêt sur la période.",
    },
    en: {
      locale: "en-GB", title: "Dashboard", subtitle: "Moulding shop · press monitoring",
      connecting: "Connecting…", online: (t) => `Up to date · ${t}`, db_down: (t) => `Database unreachable — data as of ${t}`,
      offline: "Offline — retrying…",
      all_f: "All", all_shifts: "All shifts", p_today: "Last day", p_7: "7 days", p_30: "30 days", p_all: "All",
      k_oee: "Average OEE", k_av: "Availability", k_pf: "Performance", k_ql: "Quality", k_good: "Good parts",
      k_rej: "Rejects", k_run: "Run time", k_down: "Downtime", k_stops: "Recorded stops",
      stops_val: (n, m) => `${n} · ${m} min`, vs_prev: "vs the previous period of the same length",
      grid_title: "OEE by day and shift", lg_good: "≥ 85 %", lg_warn: "60 – 85 %", lg_bad: "< 60 %", lg_idle: "No production",
      no_data: "No data for these filters.", idle: "stopped", pcs: "pcs", shift_short: (s) => s.replace("Shift ", "Sh. "),
      cell_title: (a, p, q) => `Avail ${a} · Perf ${p} · Qual ${q}`,
      c_trend: "OEE trend by shift", c_codes: "Stop causes (minutes)", c_machine: "Run / stop by machine (min)", c_day: "Stops per day",
      ds_minutes: "Minutes", ds_run: "Running", ds_stop: "Stopped", ds_stop_min: "Downtime minutes", ds_count: "Number of stops",
      n_stops: (n) => `${n} stop(s)`, n_rows: (n) => `${n} row(s)`,
      t_stops: "Stop log", t_daily: "Production by shift",
      th_machine: "Machine", th_start: "Start", th_end: "End", th_dur: "Duration (min)", th_code: "Code", th_shift: "Shift", th_part: "Part no.",
      th_setter: "Setter", th_day: "Prod. day", th_date: "Timestamp", th_run: "Run", th_down: "Down", th_good: "Good", th_rej: "Rejects",
      th_cycle: "Cycle (s)", th_av: "Avail", th_pf: "Perf", th_ql: "Qual", th_oee: "OEE",
      no_stops: "No stop in this period.", none: "No data.",
      bad_ts: "Inconsistent timestamps (end before start or > 24 h): excluded from totals",
      ai_title: "AI analysis · Claude", ai_run: "Analyse this period", ai_rerun: "Run again", ai_running: "Analysing…",
      ai_hint: "Click “Analyse this period” to get a summary, alerts, forecasts and actions for the filtered data.",
      ai_ph: "Ask a question about the data… e.g. why is shift C's OEE lower?", ai_ask: "Ask",
      ai_thinking: "Claude is thinking…", ai_alerts: "Alerts", ai_pred: "Forecasts", ai_actions: "Actions", ai_none: "Nothing to report.",
      ai_trend: (d, c) => `OEE trend: ${d} — ${c}`, ai_sev: (s) => `Severity: ${s}`, ai_prio: (s) => `Priority: ${s}`,
      ai_conf: (c, j) => `Confidence ${c} — ${j}`, ai_meta: (cached, t, m) => `${cached ? "Cached analysis" : "Generated"} at ${t} · ${m}`,
      sev: { haute: "High", moyenne: "Medium", basse: "Low" }, srv_err: (s) => `Server error (${s})`,
      i50: "Industry 5.0", scrap: "scrap rate",
      th_btn: "Thresholds", th_good: "Green from", th_warn: "Orange from", th_reset: "Reset", th_err: "The orange threshold must be below the green one.",
      fp_attention: "Needs attention", fp_cause: "Top stop cause", fp_shifts: "Shifts · weighted OEE",
      fp_day: (d) => `Last day: ${d}`, fp_ok: (n) => `No shift below ${n} % on the last day. Well done.`, fp_weak: (n) => `Weakest factor: ${n}`,
      fp_share: (p, n) => `${p} % of downtime · ${n} stop(s)`, fp_ref: "Benchmark", fp_support: "Needs support", fp_no_stop: "No stop in this period.",
    },
  };
  let T = I18N[M.lang], fmt = new Intl.NumberFormat(T.locale);
  const num = (v) => (v == null ? "—" : fmt.format(v));
  const pct = (v) => (v == null ? "—" : fmt.format(Math.round(v * 10) / 10) + " %");
  const fmtDate = (s) => new Date(s.replace(" ", "T")).toLocaleDateString(T.locale, { weekday: "short", day: "2-digit", month: "2-digit" });
  const fmtTime = (s) => s.slice(11, 19);
  const fmtStamp = (s) => (s ? s.slice(11, 19) + (T === I18N.fr ? " le " : " on ") + s.slice(8, 10) + "/" + s.slice(5, 7) : "—");
  const SHIFTS = ["Shift A", "Shift B", "Shift C"];
  const SHIFT_COLOR = () => ({ "Shift A": M.css("--shift-a"), "Shift B": M.css("--shift-b"), "Shift C": M.css("--shift-c") });
  const shiftTag = (s) => { const e = document.createElement("span"); e.className = `tag shift-${(s || "").slice(-1).toLowerCase()}`; e.textContent = s || ""; return e; };
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  // Seuils d'alerte du TRS (en %), propres à ce navigateur
  const TH_DEFAULT = { good: 85, warn: 60 };
  const thValid = (t) => t && Number.isFinite(t.good) && Number.isFinite(t.warn) && t.warn >= 0 && t.good > t.warn && t.good <= 200;
  function loadTh() {
    try { const t = JSON.parse(localStorage.getItem("modics_thresholds")); if (thValid(t)) return { good: t.good, warn: t.warn }; } catch (e) { /* stockage indisponible */ }
    return { ...TH_DEFAULT };
  }

  const charts = {};
  const state = { th: loadTh(), machine: document.querySelector(".machine.active")?.dataset.machine || "", preset: localStorage.getItem("modics_preset") || "7",
    data: null, stops: null, daily: null, sort: { stops: { key: "start", dir: -1 }, daily: { key: "date", dir: -1 } } };

  function setChartDefaults() {
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    Chart.defaults.color = M.css("--ink-2");
    Chart.defaults.borderColor = M.css("--line");
    Chart.defaults.plugins.tooltip.backgroundColor = M.css("--panel-2");
    Chart.defaults.plugins.tooltip.titleColor = M.css("--ink");
    Chart.defaults.plugins.tooltip.bodyColor = M.css("--ink");
    Chart.defaults.plugins.tooltip.borderColor = M.css("--line-2");
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.legend.labels.boxWidth = 10;
    Chart.defaults.plugins.legend.labels.boxHeight = 10;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.maintainAspectRatio = false;
  }
  function chart(id, config) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart($(id), config);
  }

  // ---------- Filtres & période ----------
  const startEl = document.querySelector("[name=start]"), endEl = document.querySelector("[name=end]");
  const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

  function applyPreset(p) {
    state.preset = p; localStorage.setItem("modics_preset", p);
    document.querySelectorAll("#presets button").forEach((b) => b.classList.toggle("active", b.dataset.preset === p));
    if (p === "custom") return;
    const min = startEl.min, max = endEl.max;
    const start = p === "all" ? min : p === "today" ? max : addDays(max, -(Number(p) - 1));
    startEl.value = start < min ? min : start;
    endEl.value = max;
  }
  function params() {
    const f = new FormData($("filters"));
    const p = new URLSearchParams();
    if (state.machine) p.set("machine", state.machine);
    for (const k of ["shift", "start", "end"]) if (f.get(k)) p.set(k, f.get(k));
    return p.toString();
  }

  let loading = false;
  async function load() {
    if (loading) return;
    loading = true;
    let again = false;
    try {
      const q = params();
      const [summary, stops, daily] = await Promise.all([
        fetch("/api/summary?" + q).then((r) => r.json()),
        fetch("/api/stops?" + q).then((r) => r.json()),
        fetch("/api/daily?" + q).then((r) => r.json()),
      ]);
      state.data = summary; state.stops = stops; state.daily = daily;
      render();
      document.body.classList.remove("is-loading");
      again = applyMeta(summary.meta);  // nouveau jour en base : on recharge avec la période mise à jour
    } catch (e) {
      setLive(false, T.offline);
    } finally {
      loading = false;
    }
    if (again) load();
  }

  // Met à jour les bornes et la liste des machines ; renvoie true si la période a bougé
  function applyMeta(m) {
    setLive(!m.error, m.error ? T.db_down(fmtStamp(m.updated_at)) : T.online(fmtStamp(m.updated_at)));
    const before = startEl.value + endEl.value;
    for (const e of [startEl, endEl]) { e.min = m.min_date; e.max = m.max_date; }
    applyPreset(state.preset);
    const box = document.querySelector(".machines");
    const known = new Set([...box.querySelectorAll(".machine")].map((b) => b.dataset.machine));
    m.machines.filter((x) => !known.has(x)).forEach((x) => {
      const b = el("button", "machine", x); b.type = "button"; b.dataset.machine = x; box.appendChild(b);
    });
    return startEl.value + endEl.value !== before;
  }

  function setLive(ok, text) {
    $("live").classList.toggle("off", !ok);
    $("live-text").textContent = text;
  }

  // ---------- Rendu ----------
  function render() {
    if (!state.data) return;
    const s = state.data;
    renderKpis(s);
    renderLegend();
    renderGrid(s.trend);
    renderFocus(s);
    renderTrend(s.trend);
    renderCodes(s.by_code);
    renderMachines(s.by_machine);
    renderDays(s.stops_per_day);
    renderStops();
    renderDaily();
    Chart.defaults.animation = false;  // pas d'animation lors des rafraîchissements suivants
  }

  function renderLegend() {
    const { good, warn } = state.th;
    $("lg-good").textContent = `≥ ${good} %`; $("lg-warn").textContent = `${warn} – ${good} %`; $("lg-bad").textContent = `< ${warn} %`;
  }

  // Formulaire des seuils : appliqué dès qu'une valeur valide est saisie
  const thForm = $("th-form"), thBtn = $("th-btn");
  const fillTh = () => { thForm.good.value = state.th.good; thForm.warn.value = state.th.warn; $("th-err").textContent = ""; };
  thBtn.addEventListener("click", () => {
    thForm.hidden = !thForm.hidden; thBtn.setAttribute("aria-expanded", String(!thForm.hidden));
    if (!thForm.hidden) fillTh();
  });
  thForm.addEventListener("input", () => {
    const t = { good: thForm.good.valueAsNumber, warn: thForm.warn.valueAsNumber };
    if (!thValid(t)) { $("th-err").textContent = T.th_err; return; }
    $("th-err").textContent = ""; state.th = t;
    try { localStorage.setItem("modics_thresholds", JSON.stringify(t)); } catch (e) { /* stockage indisponible */ }
    render();
  });
  $("th-reset").addEventListener("click", () => {
    state.th = { ...TH_DEFAULT };
    try { localStorage.removeItem("modics_thresholds"); } catch (e) { /* stockage indisponible */ }
    fillTh(); render();
  });

  // Sparkline SVG : série journalière, remplissage dégradé
  function spark(id, vals, color) {
    const svg = $(id), v = vals.filter((x) => x != null);
    svg.replaceChildren();
    if (v.length < 2) return;
    const W = 100, H = 30, lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const pts = vals.map((x, i) => (x == null ? null : [(i / (vals.length - 1)) * W, H - 2 - ((x - lo) / span) * (H - 4)])).filter(Boolean);
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("preserveAspectRatio", "none");
    const ns = "http://www.w3.org/2000/svg";
    const fill = document.createElementNS(ns, "path");
    fill.setAttribute("d", `${d} L${pts[pts.length - 1][0].toFixed(1)} ${H} L${pts[0][0].toFixed(1)} ${H} Z`);
    fill.setAttribute("fill", color); fill.setAttribute("opacity", ".14");
    const line = document.createElementNS(ns, "path");
    line.setAttribute("d", d); line.setAttribute("fill", "none"); line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "1.6"); line.setAttribute("vector-effect", "non-scaling-stroke"); line.setAttribute("stroke-linejoin", "round");
    svg.append(fill, line);
  }

  // Variation vs période précédente : en points pour les taux, en % pour les quantités
  function delta(id, cur, prev, { pts = false, invert = false } = {}) {
    const e = $(id);
    if (prev == null || (!pts && !prev)) { e.textContent = ""; e.className = "delta"; return; }
    const d = pts ? cur - prev : ((cur - prev) / prev) * 100;
    const flat = Math.abs(d) < (pts ? 0.05 : 0.5);
    const good = invert ? d < 0 : d > 0;
    e.className = "delta " + (flat ? "flat" : (d > 0 ? "pos " : "neg ") + (good ? "good" : "bad"));
    e.textContent = (d > 0 ? "+" : "") + fmt.format(Math.round(d * 10) / 10) + (pts ? " pts" : " %");
    e.title = T.vs_prev;
  }

  function renderKpis(s) {
    const k = s.kpis, c = s.compare || {}, pd = s.per_day || [];
    const set = (id, v) => ($(id).textContent = v);
    set("k-oee", pct(k.oee)); set("k-av", pct(k.availability)); set("k-pf", pct(k.performance)); set("k-ql", pct(k.quality));
    $("b-av").style.width = k.availability + "%"; $("b-pf").style.width = Math.min(100, k.performance) + "%"; $("b-ql").style.width = k.quality + "%";
    set("k-good", num(k.good_qty)); set("k-rej", num(k.reject_qty));
    const made = k.good_qty + k.reject_qty, sc = $("k-scrap");  // durabilité : part de la production partie au rebut
    sc.replaceChildren(); if (made) sc.append(el("b", null, pct((k.reject_qty / made) * 100)), " " + T.scrap);
    set("k-run", num(Math.round(k.run_min)) + " min"); set("k-down", num(Math.round(k.down_min)) + " min");
    set("k-stops", T.stops_val(k.stops_count, num(Math.round(k.stops_min))));
    delta("d-oee", k.oee, c.oee, { pts: true }); delta("d-good", k.good_qty, c.good_qty); delta("d-rej", k.reject_qty, c.reject_qty, { invert: true });
    delta("d-run", k.run_min, c.run_min); delta("d-down", k.down_min, c.down_min, { invert: true }); delta("d-stops", k.stops_count, c.stops_count, { invert: true });
    const col = (v) => M.css(v);
    spark("sp-oee", pd.map((r) => r.oee), col("--blue")); spark("sp-good", pd.map((r) => r.good_qty), col("--good"));
    spark("sp-rej", pd.map((r) => r.reject_qty), col("--bad")); spark("sp-run", pd.map((r) => r.run_min), col("--good"));
    spark("sp-down", pd.map((r) => r.down_min), col("--warn")); spark("sp-stops", pd.map((r) => r.stops_count), col("--ink-2"));
  }

  // Une équipe peut avoir plusieurs enregistrements le même jour (changements d'OF, relevés intermédiaires) :
  // on les fusionne en un seul par jour × machine × équipe. Quantités et durées sont additionnées ; les taux
  // sont recalculés sur le total (disponibilité = marche / (marche + arrêt), qualité = bonnes / (bonnes + rebuts),
  // performance moyenne pondérée par le temps de marche, TRS = D × P × Q comme dans les enregistrements).
  function mergeShifts(trend) {
    const groups = new Map();
    trend.forEach((r) => {
      const k = `${r.day.slice(0, 10)}|${r.machine}|${r.shift}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(r);
    });
    return [...groups.values()].map((rows) => {
      if (rows.length === 1) return rows[0];
      const sum = (f) => rows.reduce((a, r) => a + (r[f] || 0), 0);
      const run = sum("run_min"), down = sum("down_min"), good = sum("good_qty"), rej = sum("reject_qty");
      const availability = run + down ? run / (run + down) : 0;
      const quality = good + rej ? good / (good + rej) : 0;
      const performance = run ? rows.reduce((a, r) => a + (r.performance || 0) * (r.run_min || 0), 0) / run : 0;
      return { ...rows[rows.length - 1], run_min: run, down_min: down, good_qty: good, reject_qty: rej,
        availability, quality, performance, oee: run ? availability * performance * quality : 0 };
    });
  }

  // Grille : lignes = jours, colonnes = machine × équipe
  function renderGrid(rawTrend) {
    const trend = mergeShifts(rawTrend);
    const g = $("grid");
    g.replaceChildren();
    if (!trend.length) { g.style.gridTemplateColumns = "1fr"; g.appendChild(el("div", "empty", T.no_data)); return; }
    const machines = [...new Set(trend.map((r) => r.machine))].sort();
    const days = [...new Set(trend.map((r) => r.day.slice(0, 10)))].sort();
    const idx = {};
    trend.forEach((r) => (idx[`${r.day.slice(0, 10)}|${r.machine}|${r.shift}`] = r));
    const cols = machines.flatMap((m) => SHIFTS.map((s) => ({ m, s }))), SC = SHIFT_COLOR();
    g.style.gridTemplateColumns = `110px repeat(${cols.length}, minmax(84px, 1fr))`;
    // Ligne 1 : une en-tête par machine couvrant ses équipes ; ligne 2 : les équipes
    g.appendChild(el("div", "head"));
    machines.forEach((m) => { const h = el("div", "head mach", m); h.style.gridColumn = `span ${SHIFTS.length}`; g.appendChild(h); });
    g.appendChild(el("div", "head"));
    cols.forEach((c) => { const h = el("div", "head sh", T.shift_short(c.s)); h.style.color = SC[c.s]; g.appendChild(h); });
    days.forEach((d) => {
      const lab = el("div", "rowlab" + (d === days[days.length - 1] ? " latest" : ""), fmtDate(d)); lab.appendChild(el("small", null, `${d.slice(8, 10)}/${d.slice(5, 7)}`)); g.appendChild(lab);
      cols.forEach((c) => {
        const r = idx[`${d}|${c.m}|${c.s}`];
        if (!r) { g.appendChild(el("div", "cell none")); return; }
        if (!r.run_min) { const x = el("div", "cell idle"); x.append(el("small", null, T.idle), el("small", null, `${Math.round(r.down_min)} min`)); g.appendChild(x); return; }
        const o = r.oee * 100, cell = el("div", "cell " + (o >= state.th.good ? "good" : o >= state.th.warn ? "warn" : "bad"));
        cell.title = T.cell_title(pct(r.availability * 100), pct(r.performance * 100), pct(r.quality * 100));
        const gauge = el("i"); gauge.style.width = Math.min(100, o) + "%";
        cell.append(el("b", null, `${Math.round(o)} %`), el("small", null, `${num(r.good_qty)} ${T.pcs}`), gauge);
        g.appendChild(cell);
      });
    });
  }

  // Priorités du poste : écarts du dernier jour, cause d'arrêt dominante, comparaison des équipes.
  // Le but est d'orienter l'attention (et le soutien) des équipes, pas de les classer.
  function renderFocus(s) {
    const trend = mergeShifts(s.trend), list = $("fp-list"), cause = $("fp-cause"), sh = $("fp-shifts");
    [list, cause, sh].forEach((n) => n.replaceChildren());
    $("fp-day").textContent = "";
    if (!trend.length) { list.appendChild(el("li", "empty", T.no_data)); return; }

    const last = trend.map((r) => r.day.slice(0, 10)).sort().pop();
    $("fp-day").textContent = T.fp_day(fmtDate(last));
    const multi = new Set(trend.map((r) => r.machine)).size > 1;
    const low = trend.filter((r) => r.day.startsWith(last) && r.run_min && r.oee * 100 < state.th.good).sort((a, b) => a.oee - b.oee).slice(0, 5);
    if (!low.length) list.appendChild(el("li", "fp-ok", T.fp_ok(state.th.good)));
    low.forEach((r) => {
      const factors = [[T.k_av, r.availability], [T.k_pf, r.performance], [T.k_ql, r.quality]].sort((a, b) => a[1] - b[1]);
      const li = el("li", "fp-item" + (r.oee * 100 < state.th.warn ? "" : " warn")), mid = el("div");
      mid.append(el("b", "name", (multi ? r.machine + " · " : "") + T.shift_short(r.shift)),
        el("small", null, `${T.fp_weak(factors[0][0])} (${pct(factors[0][1] * 100)})`));
      li.append(shiftTag(r.shift), mid, el("span", "val", pct(r.oee * 100)));
      list.appendChild(li);
    });

    const codes = s.by_code || [], total = codes.reduce((a, r) => a + r.minutes, 0), top = [...codes].sort((a, b) => b.minutes - a.minutes)[0];
    if (!top || !total) cause.appendChild(el("div", "empty", T.fp_no_stop));
    else {
      const share = Math.round((top.minutes / total) * 100), bar = el("span", "bar"), u = el("u"); u.style.width = share + "%"; bar.appendChild(u);
      const big = el("div", "fp-big", num(Math.round(top.minutes))); big.appendChild(el("small", null, "min"));
      cause.append(el("div", "fp-code", top.code || "—"), big, bar, el("div", "fp-meta", T.fp_share(share, top.count)));
    }

    // TRS pondéré par le temps de marche, par équipe (toutes machines confondues)
    const agg = SHIFTS.map((x) => {
      const rows = trend.filter((r) => r.shift === x && r.run_min), run = rows.reduce((a, r) => a + r.run_min, 0);
      return { shift: x, oee: run ? rows.reduce((a, r) => a + r.oee * r.run_min, 0) / run : null };
    }).filter((x) => x.oee != null), SC = SHIFT_COLOR();
    const best = Math.max(...agg.map((x) => x.oee)), worst = Math.min(...agg.map((x) => x.oee));
    agg.forEach((x) => {
      const row = el("div", "fp-shift"), bar = el("span", "bar"), u = el("u"); u.style.width = Math.min(100, x.oee * 100) + "%"; u.style.background = SC[x.shift]; bar.appendChild(u);
      row.append(shiftTag(x.shift), bar, el("span", "v", pct(x.oee * 100)));
      sh.appendChild(row);
    });
    if (agg.length > 1 && best - worst >= 0.03) {
      const w = agg.find((x) => x.oee === worst), b = agg.find((x) => x.oee === best);
      sh.appendChild(el("div", "fp-note", `${T.fp_ref} : ${T.shift_short(b.shift)} · ${T.fp_support} : ${T.shift_short(w.shift)}`));
    }
  }

  const DASHES = [[], [6, 4], [2, 3], [10, 3, 2, 3]];  // un motif de trait par machine

  function renderTrend(rawTrend) {
    const trend = mergeShifts(rawTrend);
    const days = [...new Set(trend.map((r) => r.day.slice(0, 10)))].sort();
    const machines = [...new Set(trend.map((r) => r.machine))].sort(), SC = SHIFT_COLOR();
    const datasets = [];
    machines.forEach((m) => SHIFTS.forEach((s) => {
      const data = days.map((d) => { const r = trend.find((x) => x.machine === m && x.shift === s && x.day.startsWith(d)); return r && r.run_min ? +(r.oee * 100).toFixed(1) : null; });
      if (data.some((v) => v != null)) datasets.push({ label: (machines.length > 1 ? m + " · " : "") + T.shift_short(s), data, borderColor: SC[s],
        backgroundColor: SC[s], borderDash: DASHES[machines.indexOf(m) % DASHES.length], tension: .35, spanGaps: true, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2 });
    }));
    chart("c-trend", { type: "line", data: { labels: days.map(fmtDate), datasets },
      options: { plugins: { legend: { position: "bottom" } }, scales: { y: { min: 0, max: 110, ticks: { callback: (v) => v + " %" } }, x: { grid: { display: false } } } } });
  }

  function renderCodes(rows) {
    chart("c-code", { type: "bar", data: { labels: rows.map((r) => r.code || "—"),
      datasets: [{ label: T.ds_minutes, data: rows.map((r) => r.minutes), backgroundColor: M.css("--warn"), borderRadius: 4, borderSkipped: false }] },
      options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: (c) => T.n_stops(rows[c.dataIndex].count) } } },
        scales: { y: { grid: { display: false } } } } });
  }

  function renderMachines(rows) {
    chart("c-machine", { type: "bar", data: { labels: rows.map((r) => r.machine), datasets: [
      { label: T.ds_run, data: rows.map((r) => r.run_min), backgroundColor: M.css("--good"), borderRadius: 4 },
      { label: T.ds_stop, data: rows.map((r) => r.down_min), backgroundColor: M.css("--warn"), borderRadius: 4 } ] },
      options: { plugins: { legend: { position: "bottom" } }, scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true } } } });
  }

  function renderDays(rows) {
    chart("c-day", { type: "bar", data: { labels: rows.map((r) => fmtDate(r.day)), datasets: [
      { label: T.ds_stop_min, data: rows.map((r) => r.minutes), backgroundColor: M.css("--bad"), yAxisID: "y", borderRadius: 4 },
      { label: T.ds_count, data: rows.map((r) => r.count), type: "line", borderColor: M.css("--blue"), backgroundColor: M.css("--blue"), yAxisID: "y2", tension: .35, borderWidth: 2 } ] },
      options: { plugins: { legend: { position: "bottom" } },
        scales: { x: { grid: { display: false } }, y: { position: "left", beginAtZero: true }, y2: { position: "right", beginAtZero: true, grid: { drawOnChartArea: false }, ticks: { precision: 0 } } } } });
  }

  // ---------- Tableaux triables ----------
  function sorted(rows, { key, dir }) {
    return [...rows].sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "number" ? x - y : String(x).localeCompare(String(y), T.locale)) * dir;
    });
  }
  function markSort(tableId, s) {
    document.querySelectorAll(`#${tableId} th`).forEach((th) => {
      th.classList.toggle("asc", th.dataset.key === s.key && s.dir === 1);
      th.classList.toggle("desc", th.dataset.key === s.key && s.dir === -1);
    });
  }
  document.querySelectorAll("table.sortable th[data-key]").forEach((th) => th.addEventListener("click", () => {
    const which = th.closest("table").id === "t-stops" ? "stops" : "daily", s = state.sort[which];
    if (s.key === th.dataset.key) s.dir = -s.dir; else { s.key = th.dataset.key; s.dir = th.classList.contains("num") ? -1 : 1; }
    which === "stops" ? renderStops() : renderDaily();
  }));
  function td(v, cls) { const e = el("td", cls); if (v instanceof Node) e.appendChild(v); else e.textContent = v ?? ""; return e; }
  function emptyRow(cols, text) { const tr = el("tr"); const c = td(text, "empty"); c.colSpan = cols; tr.appendChild(c); return tr; }

  function renderStops() {
    const rows = sorted(state.stops || [], state.sort.stops);
    markSort("t-stops", state.sort.stops);
    $("stops-count").textContent = T.n_stops(rows.length);
    document.querySelector("#t-stops tbody").replaceChildren(...(rows.length ? rows.map((r) => {
      const tr = el("tr");
      const d = r.duration_min == null ? el("span", "muted", "—") : null; if (d) d.title = T.bad_ts;
      tr.append(td(r.machine), td(`${fmtDate(r.start)} ${fmtTime(r.start)}`), td(r.end ? fmtTime(r.end) : ""), td(d || num(r.duration_min), "num"),
        td(r.code), td(shiftTag(r.shift)), td(r.part_no || ""), td(r.regleur || ""));
      return tr;
    }) : [emptyRow(8, T.no_stops)]));
  }

  function renderDaily() {
    const rows = sorted(state.daily || [], state.sort.daily);
    markSort("t-daily", state.sort.daily);
    $("daily-count").textContent = T.n_rows(rows.length);
    document.querySelector("#t-daily tbody").replaceChildren(...(rows.length ? rows.map((r) => {
      const tr = el("tr"), b = el("b", null, pct(r.oee * 100));
      tr.append(td(r.machine), td(fmtDate(r.day)), td(`${fmtDate(r.date)} ${fmtTime(r.date)}`), td(shiftTag(r.shift)), td(r.part_no || ""),
        td(num(r.run_min), "num"), td(num(r.down_min), "num"), td(num(r.good_qty), "num"), td(num(r.reject_qty), "num"), td(num(r.cycle_time), "num"),
        td(pct(r.availability * 100), "num"), td(pct(r.performance * 100), "num"), td(pct(r.quality * 100), "num"), td(b, "num"));
      return tr;
    }) : [emptyRow(14, T.none)]));
  }

  // ---------- Analyse IA (Claude) ----------
  const aiRun = $("ai-run");
  if (aiRun) initAI();
  function initAI() {
    const aiFilters = () => ({ ...Object.fromEntries(new URLSearchParams(params())), lang: M.lang });
    async function postAI(url, body) {
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await r.json().catch(() => ({ error: T.srv_err(r.status) }));
      if (!r.ok) throw new Error(data.error || T.srv_err(r.status));
      return data;
    }
    function aiColumn(title, items, render) {
      const col = el("div", "ai-col"); col.appendChild(el("h3", null, title));
      if (!items.length) col.appendChild(el("div", "count", T.ai_none));
      items.forEach((it) => col.appendChild(render(it)));
      return col;
    }
    function aiItem(cls, title, detail, foot) {
      const d = el("div", "ai-item " + cls); d.append(el("b", null, title), el("span", null, detail)); if (foot) d.appendChild(el("small", null, foot));
      return d;
    }
    let lastAI = null;
    function renderAI(res) {
      lastAI = res;
      const a = res.analysis, out = $("ai-out"), sev = (s) => T.sev[s] || s;
      out.replaceChildren();
      const sum = el("div", "ai-summary"); sum.append(el("p", null, a.resume), el("p", "trend", T.ai_trend(a.tendance_trs.direction, a.tendance_trs.commentaire)));
      out.append(sum,
        aiColumn(T.ai_alerts, a.alertes, (x) => aiItem(x.gravite, x.titre, x.detail, T.ai_sev(sev(x.gravite)))),
        aiColumn(T.ai_pred, a.predictions, (x) => aiItem("info", `${x.sujet} · ${x.horizon}`, x.prevision, T.ai_conf(x.confiance, x.justification))),
        aiColumn(T.ai_actions, a.actions, (x) => aiItem(x.priorite, x.action, x.impact_attendu, T.ai_prio(sev(x.priorite)))));
      $("ai-meta").textContent = T.ai_meta(res.cached, fmtStamp(res.generated_at), res.model);
    }
    const resetBtn = () => { aiRun.dataset.force = ""; aiRun.textContent = T.ai_run; };
    aiRun.addEventListener("click", async () => {
      aiRun.disabled = true; aiRun.textContent = T.ai_running;
      try {
        renderAI(await postAI("/api/ai/insights", { ...aiFilters(), force: aiRun.dataset.force === "1" }));  // 2e clic : force une nouvelle analyse
        aiRun.dataset.force = "1";
      } catch (e) {
        $("ai-out").replaceChildren(el("div", "empty ai-error", e.message));
      } finally {
        aiRun.disabled = false; aiRun.textContent = aiRun.dataset.force === "1" ? T.ai_rerun : T.ai_run;
      }
    });
    $("filters").addEventListener("change", resetBtn);
    document.querySelector(".machines").addEventListener("click", resetBtn);
    $("ai-ask").addEventListener("submit", async (ev) => {
      const form = ev.currentTarget, q = form.q.value.trim(), btn = form.querySelector("button"), box = $("ai-answer");
      if (!q) return;
      btn.disabled = true; box.hidden = false; box.classList.remove("ai-error"); box.textContent = T.ai_thinking;
      try { box.textContent = (await postAI("/api/ai/ask", { ...aiFilters(), question: q })).answer; }
      catch (e) { box.classList.add("ai-error"); box.textContent = e.message; }
      finally { btn.disabled = false; }
    });
    document.addEventListener("modics:lang", () => { if (!aiRun.disabled) aiRun.textContent = aiRun.dataset.force === "1" ? T.ai_rerun : T.ai_run; if (lastAI) renderAI(lastAI); });
    resetBtn();
  }

  // ---------- Interactions ----------
  document.querySelector(".machines").addEventListener("click", (e) => {
    const b = e.target.closest(".machine");
    if (!b) return;
    document.querySelectorAll(".machine").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); state.machine = b.dataset.machine; load();
  });
  $("presets").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-preset]");
    if (!b) return;
    applyPreset(b.dataset.preset); load();
  });
  $("filters").addEventListener("change", (e) => {
    if (e.target === startEl || e.target === endEl) applyPreset("custom");
    load();
  });
  document.addEventListener("modics:lang", (e) => {
    T = I18N[e.detail]; fmt = new Intl.NumberFormat(T.locale);
    M.applyI18n(T); render();
    if (state.data) applyMeta(state.data.meta);
  });
  document.addEventListener("modics:theme", () => { setChartDefaults(); render(); });

  // Rafraîchissement automatique (suspendu quand l'onglet n'est pas visible)
  setInterval(() => { if (!document.hidden) load(); }, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });

  M.applyI18n(T);
  setChartDefaults();
  applyPreset(state.preset);
  setLive(false, T.connecting);
  load();
})();
