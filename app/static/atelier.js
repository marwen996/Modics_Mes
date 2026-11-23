(function () {
  // Page Atelier. Source : /api/live/fleet (toutes les 4 s).
  // Tout texte venant des données passe par textContent : jamais innerHTML.
  const M = window.MODICS;
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 4000, TODO_LIMIT = 5, STALE_S = 20;

  const L = {
    fr: {
      sub_shift: (n, a, b) => `Équipe ${n} · ${a}–${b}`,
      p1_tag: "Les personnes", p1_q: (n) => n === 1 ? "machine a besoin de quelqu'un" : "machines ont besoin de quelqu'un",
      p1_help: (st) => st ? `Dont ${st} à l'arrêt. Une machine appelle quand elle est arrêtée, ralentie ou qu'elle jette trop de pièces.` : "Une machine appelle quand elle est arrêtée, ralentie ou qu'elle jette trop de pièces.",
      p2_tag: "Moins de gaspillage", p2_q: "des pièces fabriquées sont jetées",
      p2_help: (r, t) => `${r.toLocaleString("fr-FR")} pièces jetées sur ${t.toLocaleString("fr-FR")} dans les ordres en cours. Chaque rebut, c'est de la matière et de l'énergie perdues.`,
      p2_none: "Aucune pièce comptée pour l'instant.",
      p3_tag: "Fiabilité des données", p3_q: "des terminaux répondent",
      p3_help: (on, tot, off) => off ? `${on} sur ${tot}. Les ${off} autres n'envoient rien : sans eux on ne voit pas l'état réel de ces presses.` : `${on} sur ${tot} : toutes les presses sont visibles.`,
      todo_title: "À faire maintenant", all_title: "Toutes les presses", search: "Chercher une presse, une pièce, un ordre…", no_match: "Aucune presse ne correspond.",
      todo_count: (n) => n === 1 ? "1 presse" : `${n} presses`,
      more: (n) => `Voir les ${n} autres`, less: "Réduire",
      todo_none: "Rien d'urgent : toutes les presses connectées fonctionnent normalement.",
      head_ok: "Tout va bien", head_none: "Aucune presse connectée",
      head_stop: (n) => n === 1 ? "1 presse est à l'arrêt" : `${n} presses sont à l'arrêt`,
      head_attn: (n) => n === 1 ? "1 presse est à surveiller" : `${n} presses sont à surveiller`,
      sub_ok: (run, on) => `${run} presse${run > 1 ? "s" : ""} en production sur ${on} connectée${on > 1 ? "s" : ""}.`,
      sub_bad: (run, on, attn) => `${run} en production sur ${on} connectées · ${attn} demande${attn > 1 ? "nt" : ""} de l'attention.`,
      sub_none: "Vérifiez le réseau ou les terminaux des presses.",
      f_all: "Toutes", f_attn: "À surveiller", f_run: "En production", f_stop: "À l'arrêt", f_idle: "En attente", f_off: "Non connectées",
      lg_run: "En production", lg_stop: "À l'arrêt", lg_idle: "En attente", lg_off: "Non connectées",
      st: { run: "En production", stop: "À l'arrêt", idle: "En attente", offplan: "Hors planning", offline: "Non connectée" },
      ico: { run: "▶", stop: "■", idle: "◔", offplan: "⏸", offline: "○" },
      urgent: "Urgent", watch: "À voir",
      since: (d) => `depuis ${d}`, of_qty: (p, q) => `${p.toLocaleString("fr-FR")} / ${q.toLocaleString("fr-FR")} pièces`, noof: "Pas d'ordre en cours",
      cause: "Cause de l'arrêt", planned: "planifié",
      legend: "▶ en production · ■ à l'arrêt · ◔ en attente d'un ordre · ⏸ hors planning · ○ terminal qui ne répond pas. Cliquez sur une presse pour sa fiche.",
      stale: "Les données ne se mettent plus à jour — dernière mise à jour il y a",
      open_live: "Ouvrir le suivi en direct", close: "Fermer",
      d_order: "Ordre de fabrication", d_part: "Pièce", d_made: "Fabriquées", d_target: "Objectif", d_good: "Bonnes", d_rej: "Jetées", d_trs: "TRS de l'ordre", d_speed: "Vitesse réelle / prévue",
      d_alerts: "À savoir", d_conn: "Connexion", d_none: "Aucun ordre en cours sur cette presse.",
      err: { unreachable: (d) => `Le terminal ne répond pas${d ? ` (${d})` : ""}.`, auth: () => "Le terminal refuse la clé d'accès : la clé de cette presse est à vérifier.", http: (d) => `Le terminal a répondu par une erreur${d ? ` ${d}` : ""}.`, no_key: () => "Aucune clé d'accès n'est configurée pour cette presse.", other: (d) => `Erreur : ${d || "inconnue"}` },
      al: {
        offline: () => "Le terminal ne répond pas",
        stopped: (p) => p.min < 1 ? "À l'arrêt" : `À l'arrêt depuis ${p.partial ? "plus de " : ""}${p.min} min`,
        over_qty: (p) => `Elle a dépassé la quantité de l'ordre de ${p.over.toLocaleString("fr-FR")} pièces (+${p.pct} %)`,
        rejects: (p) => `${p.rate} % de pièces jetées (${p.rejects} sur ${p.total})`,
        trs_low: (p) => `Rendement de l'ordre à ${p.trs} % (objectif ${p.target} %)`,
        cadence_low: (p) => `Cadence à ${p.pct} % de la vitesse prévue`,
        no_pieces: (p) => `En marche mais aucune pièce comptée depuis ${p.min} min : vérifier le capteur`,
        clock_skew: (p) => `Horloge du terminal décalée de ${Math.abs(p.min)} min`,
      },
    },
    en: {
      sub_shift: (n, a, b) => `Shift ${n} · ${a}–${b}`,
      p1_tag: "People", p1_q: (n) => n === 1 ? "machine needs someone" : "machines need someone",
      p1_help: (st) => st ? `Including ${st} stopped. A machine calls for help when it is stopped, slow, or scrapping too many parts.` : "A machine calls for help when it is stopped, slow, or scrapping too many parts.",
      p2_tag: "Less waste", p2_q: "of the parts made are scrapped",
      p2_help: (r, t) => `${r.toLocaleString("en-GB")} parts scrapped out of ${t.toLocaleString("en-GB")} in the running orders. Every scrap is material and energy lost.`,
      p2_none: "No parts counted yet.",
      p3_tag: "Data reliability", p3_q: "of terminals are answering",
      p3_help: (on, tot, off) => off ? `${on} of ${tot}. The other ${off} send nothing: without them we cannot see the real state of those presses.` : `${on} of ${tot}: every press is visible.`,
      todo_title: "To do now", all_title: "All presses", search: "Find a press, a part, an order…", no_match: "No press matches.",
      todo_count: (n) => n === 1 ? "1 press" : `${n} presses`,
      more: (n) => `Show ${n} more`, less: "Show less",
      todo_none: "Nothing urgent: every connected press is running normally.",
      head_ok: "Everything is fine", head_none: "No press connected",
      head_stop: (n) => n === 1 ? "1 press is stopped" : `${n} presses are stopped`,
      head_attn: (n) => n === 1 ? "1 press needs attention" : `${n} presses need attention`,
      sub_ok: (run, on) => `${run} press${run > 1 ? "es" : ""} producing out of ${on} connected.`,
      sub_bad: (run, on, attn) => `${run} producing out of ${on} connected · ${attn} need${attn > 1 ? "" : "s"} attention.`,
      sub_none: "Check the network or the press terminals.",
      f_all: "All", f_attn: "Needs attention", f_run: "Producing", f_stop: "Stopped", f_idle: "Waiting", f_off: "Not connected",
      lg_run: "Producing", lg_stop: "Stopped", lg_idle: "Waiting", lg_off: "Not connected",
      st: { run: "Producing", stop: "Stopped", idle: "Waiting", offplan: "Off schedule", offline: "Not connected" },
      ico: { run: "▶", stop: "■", idle: "◔", offplan: "⏸", offline: "○" },
      urgent: "Urgent", watch: "Check",
      since: (d) => `for ${d}`, of_qty: (p, q) => `${p.toLocaleString("en-GB")} / ${q.toLocaleString("en-GB")} parts`, noof: "No order running",
      cause: "Stop cause", planned: "planned",
      legend: "▶ producing · ■ stopped · ◔ waiting for an order · ⏸ off schedule · ○ terminal not answering. Click a press for its detail sheet.",
      stale: "Data is no longer updating — last update",
      open_live: "Open live monitoring", close: "Close",
      d_order: "Shop order", d_part: "Part", d_made: "Made", d_target: "Target", d_good: "Good", d_rej: "Scrapped", d_trs: "Order OEE", d_speed: "Actual / planned speed",
      d_alerts: "Worth knowing", d_conn: "Connection", d_none: "No order running on this press.",
      err: { unreachable: (d) => `The terminal is not answering${d ? ` (${d})` : ""}.`, auth: () => "The terminal rejects the access key: this press's key needs checking.", http: (d) => `The terminal answered with an error${d ? ` ${d}` : ""}.`, no_key: () => "No access key is configured for this press.", other: (d) => `Error: ${d || "unknown"}` },
      al: {
        offline: () => "The terminal is not answering",
        stopped: (p) => p.min < 1 ? "Stopped" : `Stopped for ${p.partial ? "over " : ""}${p.min} min`,
        over_qty: (p) => `Over the order quantity by ${p.over.toLocaleString("en-GB")} parts (+${p.pct}%)`,
        rejects: (p) => `${p.rate}% scrapped (${p.rejects} of ${p.total})`,
        trs_low: (p) => `Order OEE at ${p.trs}% (target ${p.target}%)`,
        cadence_low: (p) => `Running at ${p.pct}% of planned speed`,
        no_pieces: (p) => `Running but no part counted for ${p.min} min: check the sensor`,
        clock_skew: (p) => `Terminal clock off by ${Math.abs(p.min)} min`,
      },
    },
  };
  const T = () => L[M.lang];
  const loc = () => M.lang === "en" ? "en-GB" : "fr-FR";

  // Gravité d'une alerte, pour classer les presses (plus grand = plus urgent)
  const WEIGHT = { stopped: (a) => (a.level === "crit" ? 100 : 60), rejects: (a) => (a.level === "crit" ? 90 : 45), no_pieces: () => 80,
    trs_low: (a) => (a.level === "crit" ? 70 : 40), cadence_low: () => 50, over_qty: () => 20, clock_skew: () => 10 };
  const weight = (a) => (WEIGHT[a.code] ? WEIGHT[a.code](a) : 5);

  let fleet = null, fetchedAt = 0, filter = "all", query = "", expanded = false, openMachine = null;

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const dur = (s) => { s = Math.max(0, Math.round(s)); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return d ? `${d} j ${h} h` : h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`; };
  const json = (r) => { if (!r.ok) throw new Error(r.status); return r.json(); };
  const alertText = (a) => { const f = T().al[a.code]; try { return f ? f(a.params || {}) : a.code; } catch (e) { return a.code; } };
  const num = (v, d = 0) => (v == null ? "—" : Number(v).toLocaleString(loc(), { maximumFractionDigits: d }));

  const alertsOf = (r) => (r.online ? (r.alert_list || []) : []);
  const needs = (r) => alertsOf(r).length > 0;
  const score = (r) => Math.max(0, ...alertsOf(r).map(weight));
  const sev = (r) => (alertsOf(r).some((a) => a.level === "crit") ? "crit" : "warn");
  const stateOf = (r) => (r.online ? r.state : "offline");

  const FILTERS = [
    ["all", "f_all", () => true], ["attn", "f_attn", needs], ["run", "f_run", (r) => stateOf(r) === "run"],
    ["stop", "f_stop", (r) => stateOf(r) === "stop"], ["idle", "f_idle", (r) => stateOf(r) === "idle" || stateOf(r) === "offplan"],
    ["off", "f_off", (r) => stateOf(r) === "offline"],
  ];

  // ---------- 1. Situation ----------
  function renderStatus(rows) {
    const t = T(), on = rows.filter((r) => r.online);
    const run = on.filter((r) => r.state === "run").length, stop = on.filter((r) => r.state === "stop").length;
    const attn = on.filter(needs).length, crit = on.filter((r) => needs(r) && sev(r) === "crit").length;
    let tone = "ok", head = t.head_ok, orb = "✓";
    if (!on.length) { tone = "warn"; head = t.head_none; orb = "!"; }
    else if (stop) { tone = "crit"; head = t.head_stop(stop); orb = "■"; }
    else if (attn) { tone = crit ? "crit" : "warn"; head = t.head_attn(attn); orb = "!"; }
    $("status").className = "at-status " + tone;
    $("orb").textContent = orb;
    $("headline").textContent = head;
    $("subline").textContent = !on.length ? t.sub_none : attn ? t.sub_bad(run, on.length, attn) : t.sub_ok(run, on.length);

    const parts = [["run", "lg_run", "var(--good)"], ["stop", "lg_stop", "var(--bad)"], ["idle", "lg_idle", "var(--warn)"], ["off", "lg_off", "var(--idle)"]];
    const count = (k) => rows.filter(FILTERS.find((f) => f[0] === k)[2]).length;
    const bar = $("bar"), leg = $("legend");
    bar.replaceChildren(); leg.replaceChildren();
    bar.setAttribute("aria-label", parts.map(([k, l]) => `${count(k)} ${t[l]}`).join(", "));
    parts.forEach(([k, label, color]) => {
      const n = count(k);
      if (n) { const seg = el("i"); seg.style.flexGrow = n; seg.style.background = color; seg.title = `${t[label]} : ${n}`; seg.addEventListener("click", () => setFilter(k)); bar.append(seg); }
      const b = el("button", "at-lg"); b.type = "button";
      const sw = el("i", "at-sw"); sw.style.background = color;
      b.append(sw, el("b", null, n), el("span", null, t[label]));
      b.addEventListener("click", () => setFilter(k)); leg.append(b);
    });
  }

  // ---------- 2. Priorités ----------
  function renderTodo(rows) {
    const t = T(), box = $("todo"), more = $("todo-more");
    const items = rows.filter(needs).sort((a, b) => score(b) - score(a) || a.machine.localeCompare(b.machine, undefined, { numeric: true }));
    box.replaceChildren();
    $("todo-count").textContent = items.length ? t.todo_count(items.length) : "";
    if (!items.length) {
      const li = el("li", "at-good"); li.append(el("span", "at-sev", "✓"), el("span", null, t.todo_none)); box.append(li); more.hidden = true; return;
    }
    const shown = expanded ? items : items.slice(0, TODO_LIMIT);
    shown.forEach((r) => {
      const al = alertsOf(r).slice().sort((a, b) => weight(b) - weight(a));
      const li = el("li", "at-item " + sev(r)); li.tabIndex = 0; li.setAttribute("role", "button");
      li.append(el("span", "at-sev", sev(r) === "crit" ? "!" : "•"));
      const body = el("div"); body.append(el("div", "at-who", r.machine), el("div", "at-why", alertText(al[0])));
      const tags = [r.state === "stop" && r.stop_cause && r.stop_cause.code ? `${t.cause} : ${r.stop_cause.code}` : null, ...al.slice(1).map(alertText)].filter(Boolean);
      if (tags.length) { const w = el("div", "at-tags"); tags.forEach((x) => w.append(el("span", "at-tag", x))); body.append(w); }
      li.append(body, el("span", "at-go", "›"));
      li.addEventListener("click", () => openDrawer(r.machine));
      li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDrawer(r.machine); } });
      box.append(li);
    });
    more.hidden = items.length <= TODO_LIMIT;
    more.textContent = expanded ? t.less : t.more(items.length - TODO_LIMIT);
  }

  // ---------- 3. Piliers ----------
  function setPillar(id, tone) { $(id).classList.remove("warn", "bad"); if (tone) $(id).classList.add(tone); }
  function renderPillars(rows) {
    const t = T(), on = rows.filter((r) => r.online);
    const n = on.filter(needs).length, st = on.filter((r) => r.state === "stop").length;
    $("p1-num").textContent = n; $("p1-q").textContent = t.p1_q(n); $("p1-help").textContent = t.p1_help(st);
    setPillar("pl-people", st ? "bad" : n ? "warn" : null);

    let rej = 0, tot = 0;
    on.forEach((r) => { if (r.of_active) { rej += r.rejects || 0; tot += (r.good || 0) + (r.rejects || 0); } });
    const rate = tot ? rej / tot * 100 : null;
    $("p2-num").replaceChildren(document.createTextNode(rate == null ? "—" : num(rate, 1)), ...(rate == null ? [] : [el("small", null, "%")]));
    $("p2-help").textContent = tot ? t.p2_help(rej, tot) : t.p2_none;
    setPillar("pl-planet", rate == null ? null : rate >= 5 ? "bad" : rate >= 2 ? "warn" : null);

    const pct = rows.length ? Math.round(on.length / rows.length * 100) : 0;
    $("p3-num").replaceChildren(document.createTextNode(pct), el("small", null, "%"));
    $("p3-help").textContent = t.p3_help(on.length, rows.length, rows.length - on.length);
    setPillar("pl-resil", pct < 50 ? "bad" : pct < 90 ? "warn" : null);
  }

  // ---------- 4. Grille ----------
  function setFilter(k) { filter = k; renderChips(fleet.machines); renderGrid(fleet.machines); $("grid").scrollIntoView({ behavior: "smooth", block: "nearest" }); }

  function renderChips(rows) {
    const box = $("chips"); box.replaceChildren();
    FILTERS.forEach(([key, label, fn]) => {
      const n = rows.filter(fn).length;
      if (key !== "all" && key !== filter && !n) return;
      const b = el("button", "at-chip" + (key === filter ? " on" : ""), T()[label]); b.type = "button"; b.setAttribute("aria-pressed", key === filter);
      b.append(el("b", null, n)); b.addEventListener("click", () => setFilter(key)); box.append(b);
    });
  }

  function tile(r) {
    const t = T(), st = stateOf(r);
    const a = el("button", "at-tile " + st); a.type = "button";
    if (needs(r)) a.append(el("span", "at-flag" + (sev(r) === "crit" ? " crit" : ""), sev(r) === "crit" ? t.urgent : t.watch));
    const top = el("div", "at-t-top"); top.append(el("span", "at-t-name", r.machine));
    top.append(el("span", "at-pill", `${t.ico[st] || ""} ${t.st[st] || st}`)); a.append(top);
    if (r.online) {
      // since_partial : l'état a commencé avant le début de l'historique (serveur récemment redémarré) → durée inconnue
      const since = r.state_since && fleet && !r.since_partial ? t.since(dur(fleet.server_time - r.state_since)) : "";
      a.append(el("div", "at-t-meta", [r.of_active ? (r.part_number || r.shop_order) : null, since].filter(Boolean).join(" · ") || t.noof));
      if (r.of_active && r.quantity) {
        a.append(el("div", "at-t-meta", t.of_qty(r.produced || 0, r.quantity)));
        const bar = el("div", "at-prog"), i = el("i"); i.style.width = Math.min(100, (r.produced || 0) / r.quantity * 100) + "%"; bar.append(i); a.append(bar);
      }
    } else a.append(el("div", "at-t-meta", ""));
    a.addEventListener("click", () => openDrawer(r.machine));
    return a;
  }

  function renderGrid(rows) {
    const fn = FILTERS.find((f) => f[0] === filter)[2], q = query.trim().toLowerCase();
    const rank = { stop: 0, idle: 1, offplan: 2, run: 3 };
    const list = rows.filter(fn)
      .filter((r) => !q || [r.machine, r.part_number, r.shop_order].some((v) => String(v || "").toLowerCase().includes(q)))
      .sort((a, b) => (a.online === b.online ? 0 : a.online ? -1 : 1) || score(b) - score(a) || (rank[a.state] ?? 9) - (rank[b.state] ?? 9) || a.machine.localeCompare(b.machine, undefined, { numeric: true }));
    $("grid").replaceChildren(...list.map(tile));
    $("grid-empty").hidden = list.length > 0;
  }

  // ---------- Fiche presse ----------
  let lastFocus = null;
  function openDrawer(name) {
    openMachine = name; lastFocus = document.activeElement;
    $("scrim").hidden = false; $("drawer").hidden = false; renderDrawer(); $("dr-close").focus();
  }
  function closeDrawer() { openMachine = null; $("scrim").hidden = true; $("drawer").hidden = true; if (lastFocus && lastFocus.focus) lastFocus.focus(); }

  function kv(label, value) { const d = el("div"); d.append(el("b", null, value), el("span", null, label)); return d; }
  function renderDrawer() {
    if (!openMachine || !fleet) return;
    const r = fleet.machines.find((x) => x.machine === openMachine); if (!r) return closeDrawer();
    const t = T(), st = stateOf(r), body = $("dr-body");
    $("dr-title").textContent = r.machine;
    const pill = el("span", "at-pill", `${t.ico[st]} ${t.st[st]}`); pill.style.setProperty("--tc", st === "run" ? "var(--good)" : st === "stop" ? "var(--bad)" : st === "offline" ? "var(--idle)" : "var(--warn)");
    $("dr-state").replaceChildren(pill, ...(r.online && r.state_since && !r.since_partial ? [document.createTextNode("  " + t.since(dur(fleet.server_time - r.state_since)))] : []));
    body.replaceChildren();

    if (!r.online) {
      const sec = el("div", "at-dr-sec"); sec.append(el("div", "at-dr-lbl", t.d_conn));
      const f = t.err[r.error_code] || t.err.other; sec.append(el("div", "at-note crit", f(r.error_detail))); body.append(sec);
    } else {
      const al = alertsOf(r).slice().sort((a, b) => weight(b) - weight(a));
      if (al.length || (r.state === "stop" && r.stop_cause)) {
        const sec = el("div", "at-dr-sec"); sec.append(el("div", "at-dr-lbl", t.d_alerts));
        if (r.state === "stop" && r.stop_cause && r.stop_cause.code) sec.append(el("div", "at-note crit", `${t.cause} : ${r.stop_cause.code}${r.stop_cause.planned ? " (" + t.planned + ")" : ""}`));
        al.forEach((a) => sec.append(el("div", "at-note" + (a.level === "crit" ? " crit" : ""), alertText(a)))); body.append(sec);
      }
      const sec = el("div", "at-dr-sec"); sec.append(el("div", "at-dr-lbl", t.d_order));
      if (r.of_active) {
        const g = el("div", "at-kv");
        g.append(kv(t.d_order, r.shop_order || "—"), kv(t.d_part, r.part_number || "—"), kv(t.d_made, num(r.produced)), kv(t.d_target, num(r.quantity)),
          kv(t.d_good, num(r.good)), kv(t.d_rej, num(r.rejects)), kv(t.d_trs, r.trs != null ? num(r.trs, 1) + " %" : "—"),
          kv(t.d_speed, r.perf_live_pct != null ? num(r.perf_live_pct) + " %" : "—"));
        sec.append(g);
      } else sec.append(el("div", "at-note", t.d_none));
      body.append(sec);
    }
    const live = $("dr-live"); live.href = "/live?machine=" + encodeURIComponent(r.machine); live.textContent = t.open_live;
    $("dr-close").setAttribute("aria-label", t.close);
  }

  // ---------- Cycle ----------
  function shiftLabel() {
    const h = new Date().getHours(), t = T();
    const [n, a, b] = h >= 6 && h < 14 ? ["A", "06:00", "14:00"] : h >= 14 && h < 22 ? ["B", "14:00", "22:00"] : ["C", "22:00", "06:00"];
    $("shift-label").textContent = t.sub_shift(n, a, b);
  }

  function render() {
    shiftLabel();
    M.applyI18n(Object.fromEntries(Object.entries(T()).filter(([, v]) => typeof v === "string")));
    $("q").placeholder = T().search;
    if (!fleet) return;
    const rows = fleet.machines;
    renderStatus(rows); renderTodo(rows); renderPillars(rows); renderChips(rows); renderGrid(rows); renderDrawer();
  }

  function setLive(ok) {
    $("live").classList.toggle("off", !ok);
    $("live-text").textContent = ok ? (M.lang === "en" ? "Live" : "En direct") : (M.lang === "en" ? "No link" : "Hors liaison");
  }
  function checkStale() {
    const b = $("banner"), age = (Date.now() - fetchedAt) / 1000;
    if (fetchedAt && age > STALE_S) { b.textContent = `${T().stale} ${dur(age)}`; b.hidden = false; setLive(false); } else b.hidden = true;
  }

  async function load() {
    try { fleet = await fetch("/api/live/fleet").then(json); fetchedAt = Date.now(); setLive(true); render(); }
    catch (e) { setLive(false); }
    checkStale();
  }

  $("q").addEventListener("input", (e) => { query = e.target.value; if (fleet) renderGrid(fleet.machines); });
  $("todo-more").addEventListener("click", () => { expanded = !expanded; renderTodo(fleet.machines); });
  $("scrim").addEventListener("click", closeDrawer);
  $("dr-close").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && openMachine) closeDrawer();
    if (e.key === "Tab" && openMachine) { // le focus reste dans la fiche tant qu'elle est ouverte
      const f = [...$("drawer").querySelectorAll("button, a[href]")];
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  document.addEventListener("modics:lang", render);
  setInterval(() => { $("clock").textContent = new Date().toLocaleTimeString(loc()); checkStale(); }, 1000);
  setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  shiftLabel();
  load();
})();
