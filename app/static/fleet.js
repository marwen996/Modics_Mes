(function () {
  // Vue globale du parc. Source : /api/live/fleet (toutes les 4 s). Deux modes sur le même DOM :
  //  - bureau : grille auto-fill défilante, tri par priorité ou par nom, filtres, clic → page Live de la presse ;
  //  - TV (?tv=1 ou bouton) : tout le parc sur un écran. Les tuiles ne bougent jamais (tri par numéro : les
  //    opérateurs mémorisent l'emplacement), la grille c × r est calculée pour maximiser la taille des tuiles,
  //    le texte est dimensionné d'après la hauteur réelle d'une tuile (--ch) et un bandeau fait tourner les alertes.
  const M = window.MODICS;
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 4000, STALE_S = 20, TICK_MS = 6000, TV_RELOAD_MS = 12 * 3600 * 1000, CURSOR_MS = 3000;
  const TILE_ASPECT = 1.45;   // largeur / hauteur visée d'une tuile TV

  const L = {
    fr: {
      title: "Parc", subtitle: "Vue globale des presses", tv: "Mode TV", tv_exit: "Quitter le mode TV", search: "Presse, pièce, ordre…",
      sort_prio: "Par priorité", sort_name: "Par numéro", no_match: "Aucune presse ne correspond.",
      shift: (n, a, b) => `Équipe ${n} · ${a}–${b}`,
      head_ok: "Tout va bien", head_none: "Aucune presse connectée",
      head_stop: (n) => n === 1 ? "1 presse à l'arrêt" : `${n} presses à l'arrêt`,
      head_attn: (n) => n === 1 ? "1 presse à surveiller" : `${n} presses à surveiller`,
      sub: (run, on, tot, attn) => `${run} en production · ${on} connectées sur ${tot}${attn ? ` · ${attn} à surveiller` : ""}`,
      c_run: "En production", c_stop: "À l'arrêt", c_idle: "En attente", c_off: "Non connectées", c_all: "Toutes",
      st: { run: "En production", stop: "À l'arrêt", idle: "En attente", offplan: "Hors planning", offline: "Non connectée", maintenance: "En maintenance" },
      ico: { run: "▶", stop: "■", idle: "◔", offplan: "⏸", offline: "○", maintenance: "⚙" },
      urgent: "Urgent", watch: "À voir", noof: "Pas d'ordre", cause: "Cause", trs: "TRS", cad: "Cadence",
      since: (d) => `depuis ${d}`, pcs: (p, q) => `${p} / ${q}`,
      tk_none: "Rien d'urgent : toutes les presses connectées fonctionnent normalement.", tk_off: (n) => `${n} presse${n > 1 ? "s" : ""} non connectée${n > 1 ? "s" : ""}`,
      stale: "Les données ne se mettent plus à jour — dernière mise à jour il y a",
      err: { unreachable: "Terminal injoignable", auth: "Clé d'accès refusée", http: "Erreur du terminal", no_key: "Pas de clé configurée", other: "Erreur", maintenance: "En maintenance" },
      al: {
        offline: () => "Le terminal ne répond pas",
        stopped: (p) => p.min < 1 ? "À l'arrêt" : `À l'arrêt depuis ${p.partial ? "plus de " : ""}${p.min} min`,
        over_qty: (p) => `Quantité de l'ordre dépassée de ${p.over} pièces (+${p.pct} %)`,
        rejects: (p) => `${p.rate} % de pièces jetées (${p.rejects} sur ${p.total})`,
        trs_low: (p) => `Rendement de l'ordre à ${p.trs} % (objectif ${p.target} %)`,
        cadence_low: (p) => `Cadence à ${p.pct} % de la vitesse prévue`,
        no_pieces: (p) => `En marche mais aucune pièce comptée depuis ${p.min} min : vérifier le capteur`,
        clock_skew: (p) => `Horloge du terminal décalée de ${Math.abs(p.min)} min`,
      },
    },
    en: {
      title: "Fleet", subtitle: "All presses at a glance", tv: "TV mode", tv_exit: "Exit TV mode", search: "Press, part, order…",
      sort_prio: "By priority", sort_name: "By number", no_match: "No press matches.",
      shift: (n, a, b) => `Shift ${n} · ${a}–${b}`,
      head_ok: "Everything is fine", head_none: "No press connected",
      head_stop: (n) => n === 1 ? "1 press stopped" : `${n} presses stopped`,
      head_attn: (n) => n === 1 ? "1 press needs attention" : `${n} presses need attention`,
      sub: (run, on, tot, attn) => `${run} producing · ${on} connected of ${tot}${attn ? ` · ${attn} need attention` : ""}`,
      c_run: "Producing", c_stop: "Stopped", c_idle: "Waiting", c_off: "Not connected", c_all: "All",
      st: { run: "Producing", stop: "Stopped", idle: "Waiting", offplan: "Off schedule", offline: "Not connected", maintenance: "Under maintenance" },
      ico: { run: "▶", stop: "■", idle: "◔", offplan: "⏸", offline: "○", maintenance: "⚙" },
      urgent: "Urgent", watch: "Check", noof: "No order", cause: "Cause", trs: "OEE", cad: "Rate",
      since: (d) => `for ${d}`, pcs: (p, q) => `${p} / ${q}`,
      tk_none: "Nothing urgent: every connected press is running normally.", tk_off: (n) => `${n} press${n > 1 ? "es" : ""} not connected`,
      stale: "Data is no longer updating — last update",
      err: { unreachable: "Terminal unreachable", auth: "Access key rejected", http: "Terminal error", no_key: "No key configured", other: "Error", maintenance: "Under maintenance" },
      al: {
        offline: () => "The terminal is not answering",
        stopped: (p) => p.min < 1 ? "Stopped" : `Stopped for ${p.partial ? "over " : ""}${p.min} min`,
        over_qty: (p) => `Order quantity exceeded by ${p.over} parts (+${p.pct}%)`,
        rejects: (p) => `${p.rate}% scrapped (${p.rejects} of ${p.total})`,
        trs_low: (p) => `Order OEE at ${p.trs}% (target ${p.target}%)`,
        cadence_low: (p) => `Running at ${p.pct}% of planned speed`,
        no_pieces: (p) => `Running but no part counted for ${p.min} min: check the sensor`,
        clock_skew: (p) => `Terminal clock off by ${Math.abs(p.min)} min`,
      },
    },
  };
  const T = () => L[M.lang];
  const loc = () => (M.lang === "en" ? "en-GB" : "fr-FR");

  // Poids d'une alerte : classe les presses dans la vue bureau et le bandeau TV
  const WEIGHT = { stopped: (a) => (a.level === "crit" ? 100 : 60), rejects: (a) => (a.level === "crit" ? 90 : 45), no_pieces: () => 80,
    trs_low: (a) => (a.level === "crit" ? 70 : 40), cadence_low: () => 50, over_qty: () => 20, clock_skew: () => 10 };
  const weight = (a) => (WEIGHT[a.code] ? WEIGHT[a.code](a) : 5);

  // Plan d'atelier : 3 lignes (1 par allée) × 10 colonnes — correspond au plan physique de l'atelier
  const TV_LAYOUT = [
    ["PRS 77", "PRS 73", "PRS 2",  "PRS 61", "PRS 67", "PRS 4",  "PRS 5",  "PRS 6",  "PRS 7",  "PRS 62"],
    ["PRS 80", "PRS 81", "PRS 83", "PRS 79", "PRS 40", "PRS 29", "PRS 66", "PRS 78", null,     null    ],
    ["PRS 63", "PRS 84", "PRS 72", "PRS 71", "PRS 76", "PRS 75", "PRS 74", "PRS 70", "PRS 69", "PRS 68"],
  ];

  let fleet = null, oeeAll = null, fetchedAt = 0, filter = "all", sort = "prio", query = "", tv = false;
  let tvRow = 0, tvRowTimer = null;
  const TV_ROW_MS = 7000; // 7 secondes par ligne

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const dur = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`; };
  const num = (v) => (v == null ? "—" : Number(v).toLocaleString(loc()));
  const json = (r) => { if (!r.ok) throw new Error(r.status); return r.json(); };
  const alertText = (a) => { const f = T().al[a.code]; try { return f ? f(a.params || {}) : a.code; } catch (e) { return a.code; } };
  const byNum = (a, b) => a.machine.localeCompare(b.machine, undefined, { numeric: true });

  const alertsOf = (r) => (r.online ? (r.alert_list || []).slice().sort((a, b) => weight(b) - weight(a)) : []);
  const needs = (r) => alertsOf(r).length > 0;
  const score = (r) => Math.max(0, ...alertsOf(r).map(weight));
  const sev = (r) => (alertsOf(r).some((a) => a.level === "crit") ? "crit" : "warn");
  const stateOf = (r) => (r.maintenance ? "maintenance" : r.online ? r.state : "offline");

  const FILTERS = {
    all: () => true, run: (r) => stateOf(r) === "run", stop: (r) => stateOf(r) === "stop",
    idle: (r) => stateOf(r) === "idle" || stateOf(r) === "offplan",
    off: (r) => stateOf(r) === "offline" || stateOf(r) === "maintenance",
  };

  // ---------- En-tête ----------
  function renderTop(rows) {
    const t = T(), on = rows.filter((r) => r.online);
    const run = on.filter((r) => r.state === "run").length, stop = on.filter((r) => r.state === "stop").length, attn = on.filter(needs).length;
    let tone = "ok", head = t.head_ok, orb = "✓";
    if (!on.length) { tone = "warn"; head = t.head_none; orb = "!"; }
    else if (stop) { tone = "crit"; head = t.head_stop(stop); orb = "■"; }
    else if (attn) { tone = on.some((r) => needs(r) && sev(r) === "crit") ? "crit" : "warn"; head = t.head_attn(attn); orb = "!"; }
    const top = document.querySelector(".fb-top"); top.className = "fb-top " + tone;
    $("orb").textContent = orb; $("headline").textContent = head;
    $("subline").textContent = t.sub(run, on.length, rows.length, attn);

    const box = $("counts"); box.replaceChildren();
    [["run", "c_run", "var(--good)"], ["stop", "c_stop", "var(--bad)"], ["idle", "c_idle", "var(--warn)"], ["off", "c_off", "var(--idle)"]].forEach(([k, label, c]) => {
      const b = el("button", "fb-ct" + (filter === k ? " on" : "")); b.type = "button"; b.style.setProperty("--c", c); b.setAttribute("aria-pressed", filter === k);
      b.append(el("i"), el("b", null, rows.filter(FILTERS[k]).length), el("span", null, t[label]));
      b.addEventListener("click", () => { filter = filter === k ? "all" : k; render(); });
      box.append(b);
    });
    const s = $("sort"); s.replaceChildren();
    [["prio", "sort_prio"], ["name", "sort_name"]].forEach(([k, label]) => {
      const b = el("button", k === sort ? "on" : "", t[label]); b.type = "button"; b.setAttribute("aria-pressed", k === sort);
      b.addEventListener("click", () => { sort = k; render(); }); s.append(b);
    });
    $("q").placeholder = t.search;
    $("tv-btn").textContent = tv ? t.tv_exit : t.tv;
  }

  // ---------- Tuiles ----------
  function tile(r) {
    const t = T(), st = stateOf(r), al = alertsOf(r);
    const b = el("button", `ft ${st}` + (al.length && sev(r) === "crit" ? " urgent" : "")); b.type = "button";
    const head = el("div", "ft-head"); head.append(el("span", "ft-name", r.machine));
    if (al.length) head.append(el("span", "ft-badge" + (sev(r) === "crit" ? " crit" : ""), sev(r) === "crit" ? t.urgent : t.watch));
    b.append(head);
    const stLabel = (tv && st === "idle" && !r.shop_order) ? "No Active Order" : t.st[st];
    const state = el("div", "ft-state"); state.append(el("i", null, t.ico[st]), el("span", null, stLabel));
    // Durée affichée seulement si elle est connue (pas de troncature d'historique) et significative (≥ 1 min)
    if (!tv && r.online && r.state_since && !r.since_partial && fleet.server_time - r.state_since >= 60) state.append(el("span", null, "· " + t.since(dur(fleet.server_time - r.state_since))));
    b.append(state);

    // Ligne d'information : la plus utile selon l'état (cause d'arrêt > alerte > pièce/ordre > raison hors ligne)
    let line = "", alertLine = false;
    if (st === "maintenance") line = t.err.maintenance;
    else if (!r.online) line = t.err[r.error_code] || t.err.other;
    else if (st === "stop" && r.stop_cause && r.stop_cause.code) { line = `${t.cause} : ${r.stop_cause.code}`; alertLine = true; }
    else if (al.length) { line = alertText(al[0]); alertLine = true; }
    else if (r.of_active) line = [r.part_number, r.shop_order].filter(Boolean).join(" · ");
    else line = t.noof;
    b.append(el("div", "ft-line" + (alertLine ? " alert" : ""), line));

    const _mOee = oeeAll && oeeAll.machines && oeeAll.machines[r.machine];
    const _oeeDb = _mOee && _mOee.today && _mOee.today.oee != null ? _mOee.today.oee : null;
    const oeeVal = r.trs != null ? r.trs : _oeeDb;  // terminal (temps réel) > base SQL (aujourd'hui)
    if (r.online && r.of_active && r.quantity) {
      const p = (r.produced || 0) / r.quantity * 100;
      const prog = el("div", "ft-prog" + (p > 100 ? " over" : "")), i = el("i"); i.style.width = Math.min(100, p) + "%"; prog.append(i);
      const foot = el("div", "ft-foot");
      if (tv) {
        if (r.shop_order) foot.append(el("span", "ft-order", "OF : " + r.shop_order));
        if (r.perf_live_pct != null) foot.append(el("span", "trs " + (r.perf_live_pct < 70 ? "bad" : r.perf_live_pct < 85 ? "warn" : "good"), `OEE ${Math.min(100, Math.round(r.perf_live_pct))} %`));
        b.append(foot); b.append(prog);
      } else {
        b.append(prog);
        foot.append(el("span", null, t.pcs(num(r.produced), num(r.quantity))));
        if (r.perf_live_pct != null) foot.append(el("span", "trs " + (r.perf_live_pct < 70 ? "bad" : r.perf_live_pct < 85 ? "warn" : "good"), `OEE ${Math.min(100, Math.round(r.perf_live_pct))} %`));
        b.append(foot);
      }
    } else {
      const foot = el("div", "ft-foot");
      if (r.online && r.perf_live_pct != null) foot.append(el("span", "trs " + (r.perf_live_pct < 70 ? "bad" : r.perf_live_pct < 85 ? "warn" : "good"), `OEE ${Math.min(100, Math.round(r.perf_live_pct))} %`));
      b.append(el("div", "ft-prog")); b.append(foot);
    }
    if (!tv) b.addEventListener("click", () => { location.href = "/live?machine=" + encodeURIComponent(r.machine); });
    return b;
  }

  // TV : toutes les machines apparaissent dans la grille (positions fixes, par numéro), y compris les déconnectées.
  function splitTV() {
    const all = fleet.machines.slice().sort(byNum);
    return { grid: all, off: [] };
  }
  function visibleRows() {
    const rows = fleet.machines, q = query.trim().toLowerCase();
    if (tv) return splitTV().grid;
    const list = rows.filter(FILTERS[filter]).filter((r) => !q || [r.machine, r.part_number, r.shop_order].some((v) => String(v || "").toLowerCase().includes(q)));
    if (sort === "name") return list.sort(byNum);
    const rank = { stop: 0, idle: 1, offplan: 1, run: 2, offline: 3, maintenance: 4 };
    return list.sort((a, b) => (a.online === b.online ? 0 : a.online ? -1 : 1) || score(b) - score(a) || rank[stateOf(a)] - rank[stateOf(b)] || byNum(a, b));
  }

  function renderGrid() {
    const grid = $("grid");
    if (tv) {
      const row = TV_LAYOUT[tvRow];
      const byName = Object.fromEntries(fleet.machines.map(r => [r.machine, r]));
      const list = row.filter(Boolean).map(n => byName[n]).filter(Boolean);
      grid.replaceChildren(...list.map(tile));
      $("empty").hidden = true;
      fitGrid(list.length);
    } else {
      const list = visibleRows();
      grid.replaceChildren(...list.map(tile));
      $("empty").hidden = list.length > 0; $("empty").textContent = T().no_match;
      grid.dataset.level = "full"; grid.style.cssText = "";
    }
    renderOff();
  }

  function renderOff() {
    const t = T(), box = $("off"), off = tv ? splitTV().off : [];
    box.hidden = !off.length;
    if (!off.length) return;
    // Libellé : total + répartition par cause (« 16 non connectées · 15 injoignables · 1 erreur ») ; pastilles : nom seul,
    // la cause n'est répétée que sur les pastilles dont la cause n'est pas la plus fréquente.
    const counts = {}; off.forEach((r) => { const k = r.maintenance ? "maintenance" : (r.error_code || "other"); counts[k] = (counts[k] || 0) + 1; });
    const major = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
    const lbl = $("off-lbl"); lbl.replaceChildren(el("b", null, off.length), document.createTextNode(t.c_off.toLowerCase()));
    const detail = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${(t.err[k] || t.err.other).toLowerCase()}`).join(" · ");
    if (Object.keys(counts).length > 1) lbl.append(el("small", null, detail));
    $("off-list").replaceChildren(...off.map((r) => {
      const k = r.maintenance ? "maintenance" : (r.error_code || "other");
      const p = el("span", "fb-off-pill" + (k === "auth" || k === "no_key" ? " auth" : k === "maintenance" ? " maint" : ""));
      p.append(el("b", null, r.machine));
      if (k !== major) p.append(el("span", null, t.err[k] || t.err.other));
      return p;
    }));
  }

  // Grille TV : pour chaque nombre de colonnes, la taille de tuile obtenue est bornée par la largeur (ramenée en
  // hauteur via le ratio visé) et par la hauteur ; on garde la combinaison qui donne la plus grande tuile.
  function fitGrid(n) {
    const grid = $("grid"); if (!n) return;
    const W = grid.clientWidth, H = grid.clientHeight; if (!W || !H) return;
    let best = null;
    for (let c = 1; c <= n; c++) {
      const r = Math.ceil(n / c), gap = Math.max(2, H / r * 0.04);
      const tw = (W - gap * (c - 1)) / c, th = (H - gap * (r - 1)) / r;
      const size = Math.min(tw / TILE_ASPECT, th);
      if (!best || size > best.size) best = { c, r, tw, th, size };
    }
    grid.style.setProperty("--cols", best.c); grid.style.setProperty("--rows", best.r);
    grid.style.setProperty("--ch", best.th + "px"); grid.style.setProperty("--tw", best.tw + "px");
    grid.dataset.level = best.th >= 150 ? "full" : best.th >= 95 ? "mid" : "min";
  }

  // ---------- Bandeau TV ----------
  let tickIdx = 0, tickTimer = null, tickKey = "";
  function tickerItems() {
    const t = T(), items = fleet.machines.filter(needs).sort((a, b) => score(b) - score(a) || byNum(a, b))
      .map((r) => { const al = alertsOf(r); const cause = r.state === "stop" && r.stop_cause && r.stop_cause.code ? ` · ${t.cause} : ${r.stop_cause.code}` : "";
        return { sev: sev(r), who: r.machine, txt: alertText(al[0]) + cause }; });
    return items;  // les non connectées ont leur propre bande : pas de doublon dans le bandeau
  }
  function renderTicker(advance) {
    if (!tv || !fleet) return;
    const items = tickerItems(), tk = $("ticker");
    if (!items.length) { tk.className = "fb-ticker ok"; $("tk-sev").textContent = "✓"; $("tk-who").textContent = ""; $("tk-txt").textContent = T().tk_none; $("tk-idx").textContent = ""; return; }
    if (advance) tickIdx++;
    tickIdx %= items.length;
    const it = items[tickIdx], key = it.who + it.txt;
    tk.className = "fb-ticker " + it.sev;
    if (key !== tickKey) { tk.classList.add("swap"); setTimeout(() => tk.classList.remove("swap"), 500); tickKey = key; }
    $("tk-sev").textContent = it.sev === "crit" ? "!" : "•"; $("tk-who").textContent = it.who; $("tk-txt").textContent = it.txt;
    $("tk-idx").textContent = items.length > 1 ? `${tickIdx + 1} / ${items.length}` : "";
  }

  // ---------- Mode TV ----------
  let wakeLock = null, cursorTimer = null;
  async function keepAwake() {
    if (!tv || document.hidden || !("wakeLock" in navigator)) return;
    try { wakeLock = await navigator.wakeLock.request("screen"); } catch (e) { /* refusé par le navigateur : réglages d'alimentation */ }
  }
  function hideCursorSoon() {
    document.body.classList.remove("no-cursor"); clearTimeout(cursorTimer);
    if (tv) cursorTimer = setTimeout(() => document.body.classList.add("no-cursor"), CURSOR_MS);
  }
  function setTV(on, fromUser) {
    tv = on;
    document.body.classList.toggle("fb-tv", on);
    const url = new URL(location.href); if (on) url.searchParams.set("tv", "1"); else url.searchParams.delete("tv"); history.replaceState(null, "", url);
    if (on) {
      if (fromUser && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
      keepAwake(); hideCursorSoon();
      clearInterval(tickTimer); tickTimer = setInterval(() => renderTicker(true), TICK_MS);
      tvRow = 0; clearInterval(tvRowTimer);
      tvRowTimer = setInterval(() => {
        tvRow = (tvRow + 1) % TV_LAYOUT.length;
        const g = $("grid"); g.classList.remove("tv-anim"); void g.offsetWidth; g.classList.add("tv-anim");
        renderGrid(); renderTicker(false);
      }, TV_ROW_MS);
    } else {
      if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
      if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
      clearInterval(tickTimer); tickTimer = null; document.body.classList.remove("no-cursor");
      clearInterval(tvRowTimer); tvRowTimer = null; tvRow = 0;
    }
    render();
  }
  $("tv-btn").addEventListener("click", () => setTV(!tv, true));
  document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && tv) setTV(false, false); });
  document.addEventListener("mousemove", hideCursorSoon);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && tv) setTV(false, false); });
  setTimeout(() => { if (tv) location.reload(); }, TV_RELOAD_MS);   // une TV allumée des semaines récupère les mises à jour de la page

  // ---------- Cycle ----------
  function shiftLabel() {
    const h = new Date().getHours();
    const [n, a, b] = h >= 6 && h < 14 ? ["A", "06:00", "14:00"] : h >= 14 && h < 22 ? ["B", "14:00", "22:00"] : ["C", "22:00", "06:00"];
    $("shift").textContent = T().shift(n, a, b);
  }
  function render() {
    shiftLabel();
    M.applyI18n(Object.fromEntries(Object.entries(T()).filter(([, v]) => typeof v === "string")));
    document.title = `MODICS — ${T().title}`;
    $("tv-btn").textContent = tv ? T().tv_exit : T().tv;
    if (!fleet) return;
    renderTop(fleet.machines);
    if (tv) $("subline").textContent = `Ligne ${tvRow + 1} / ${TV_LAYOUT.length}`;
    renderGrid(); renderTicker(false);
  }
  function checkStale() {
    const b = $("banner"), age = (Date.now() - fetchedAt) / 1000;
    if (fetchedAt && age > STALE_S) { b.textContent = `${T().stale} ${dur(age)}`; b.hidden = false; } else b.hidden = true;
  }
  async function load() {
    try { [fleet, oeeAll] = await Promise.all([fetch("/api/live/fleet").then(json), fetch("/api/live/oee/all").then(json)]); fetchedAt = Date.now(); render(); } catch (e) { /* garde la dernière vue ; le bandeau signale l'ancienneté */ }
    checkStale();
  }

  $("q").addEventListener("input", (e) => { query = e.target.value; if (fleet) renderGrid(); });
  document.addEventListener("modics:lang", render);
  new ResizeObserver(() => { if (tv && fleet) fitGrid(TV_LAYOUT[tvRow].filter(Boolean).length); }).observe($("grid"));
  setInterval(() => { $("clock").textContent = new Date().toLocaleTimeString(loc(), { hour: "2-digit", minute: "2-digit" }); checkStale(); }, 1000);
  setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { load(); keepAwake(); } });
  render();
  if (new URLSearchParams(location.search).get("tv") === "1") setTV(true, false);
  load();
})();
