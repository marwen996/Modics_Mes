(function () {
  // Supervision temps réel : /api/live relaie le terminal Raspberry Pi et ajoute alertes,
  // indicateurs et historique calculés côté serveur.
  // Tout le texte venant du terminal est inséré via textContent (aucun HTML interprété).
  const POLL_MS = 3000;
  const STOPS_MS = 60000;
  const $ = (id) => document.getElementById(id);

  // ---------- Traductions ----------
  // Textes fixes : attribut data-i18n="clé" dans live.html. Les fonctions reçoivent des valeurs.
  const I18N = {
    fr: {
      locale: "fr-FR",
      title: "MODICS — Live",
      brand_sub: "Supervision temps réel · terminal presse",
      fl_so: "Shop order", fl_pn: "Référence", fl_pcs: "pcs", fl_stop: "ARRÊT", fl_stop_planned: "ARRÊT PLANIFIÉ", fl_cause_none: "cause non renseignée",
      fl_cause_at: (t) => `Dernière cause enregistrée en base (arrêt clôturé le ${t})`, fl_oee_of: "TRS OF", fl_oee_24h: "TRS 24 h", fl_oee_wtd: "TRS semaine", fl_no_of: "Aucun OF", fl_alerts: (n) => `${n} alerte${n > 1 ? "s" : ""}`, fl_ok: "RAS",
      nav_dashboard: "Tableau de bord", nav_live: "Live",
      tv: "Mode TV", tv_all: "TV · toutes les machines", tv_exit: "Quitter TV", tv_hint: "Mode TV · Échap pour quitter",
      connecting: "Connexion au terminal…",
      online: (t) => `Terminal en ligne · échantillon ${t}`,
      server_down: "Serveur MODICS injoignable — nouvelle tentative…",
      alerts: "Alertes",
      oee_today: "TRS aujourd'hui", oee_24h: "TRS 24 dernières heures", oee_wtd: "TRS semaine (WTD)",
      oee_sub: (a, p, q, n) => `Disp. ${a} % · Perf. ${p} % · Qual. ${q} % · ${n} éq.`,
      g_trs: "TRS de l'OF", g_trs_sub: "calculé par le terminal", g_perf: "Cadence réelle", g_qual: "Qualité",
      perf_sub: (r, th, w) => `${r} / ${th} pcs/h (${w} min)`, perf_wait: "mesure après 5 min d'observation",
      qual_sub: (r, t) => `${r} rejet(s) sur ${t}`,
      of_title: "Ordre de fabrication", so: "Shop Order", part: "Référence", tool: "Outil", cycle_target: "Cycle cible",
      cav_short: "empr.", terminal_time: (t) => `terminal ${t}`,
      good: "Bonnes", rejects: "Rejets", remaining: "Restant",
      prog: (p, q, pct) => `${p} / ${q} pcs · ${pct} %`,
      eta: (d, real) => `Fin estimée ${d} (${real ? "cadence réelle" : "cadence théorique"})`,
      over: (n) => `Quantité dépassée de ${n} pcs`,
      st_run: "Production", st_stop: "Arrêt", st_idle: "En attente d'OF", st_offline: "Hors ligne", st_offline_lg: "Terminal hors ligne", st_offplan: "Hors planning", fl_since: "depuis",
      last_piece: (d) => `Dernière pièce il y a ${d}`, observed: (m) => `Historique : ${m} min observées`,
      timeline_title: "Chronologie de la presse", window: (a, b) => `· journée de production ${a} → ${b}`,
      shift: (x) => `Équipe ${x}`,
      m_av: "Disponibilité observée", m_stops: "Arrêts", m_mttr: "MTTR (durée moy. d'arrêt)",
      m_mtbf: "MTBF (marche moy. entre arrêts)", m_cycle: "Cycle réel moyen (30 min)",
      note: (t) => `Historique disponible depuis ${t} : il est collecté par le serveur et remis à zéro à chaque redémarrage du serveur MODICS.`,
      c_title: (n) => `Cadence · pièces par tranche de ${n} min`, target: (n, m) => `cible ${n} pcs / ${m} min`,
      ds_pieces: "Pièces", ds_target: "Cible",
      queue_title: "File des OF (ERP)", q_count: (n) => `${n} OF en attente`, q_empty: "Aucun OF en attente sur le terminal.",
      q_seq: "Séq.", q_qty: "Quantité", q_cycle: "Cycle (s)", q_cav: "Empr.", q_due: "Échéance",
      stops_title: "Arrêts du jour", stops_src: "base MODICS (après synchro du terminal)", stops_empty: "Aucun arrêt enregistré aujourd'hui.",
      s_start: "Début", s_end: "Fin", s_dur: "Durée (min)", s_code: "Code", s_shift: "Équipe", s_setter: "Régleur",
      no_code: "(sans code)",
      a_none: ["Aucune anomalie", "Tous les indicateurs sont dans les seuils."],
      err: { no_key: "MODICS_PI_KEY non configurée sur le serveur", auth: "Clé API refusée par le terminal",
        http: (d) => `Erreur HTTP ${d} du terminal`, unreachable: (d) => `Terminal injoignable sur ${d}`, other: (d) => d },
      a: {
        offline: () => ["MODICS OFFLINE", ""],
        stopped: (p) => ["Presse à l'arrêt", `Depuis ${p.partial ? "au moins " : ""}${p.min} min.`],
        over_qty: (p, n) => ["Quantité de l'OF dépassée", `OF ${p.so} : ${n(p.produced)} pièces pour ${n(p.qty)} demandées (+${n(p.over)}, +${p.pct} %). Clôturer l'OF sur le terminal ?`],
        rejects: (p, n) => ["Taux de rebut élevé", `${n(p.rate)} % (${n(p.rejects)} rejets sur ${n(p.total)} pièces).`],
        trs_low: (p, n) => ["TRS de l'OF bas", `${n(p.trs)} % (objectif ≥ ${p.target} %).`],
        cadence_low: (p, n) => ["Cadence en dessous de la cible", `${n(p.rate)} pcs/h sur ${p.window} min contre ${n(p.th)} pcs/h théoriques (${p.pct} %).`],
        no_pieces: (p) => ["Aucune pièce comptée", `État « Production » mais compteur figé depuis plus de ${p.min} min : vérifier le capteur.`],
        clock_skew: (p) => ["Horloge du terminal décalée", `${p.min > 0 ? "+" : ""}${p.min} min par rapport au serveur : les arrêts seront mal datés.`],
        no_next_of: (p) => ["Aucun OF suivant dans la file ERP", p.done ? "L'OF en cours est terminé." : `Fin de l'OF dans ~${p.min} min.`],
        no_of: () => ["Aucun OF actif", "Le terminal attend le lancement d'un ordre de fabrication."],
      },
    },
    en: {
      locale: "en-GB",
      title: "MODICS — Live",
      brand_sub: "Real-time monitoring · press terminal",
      fl_so: "Shop order", fl_pn: "Part no.", fl_pcs: "pcs", fl_stop: "STOPPED", fl_stop_planned: "PLANNED STOP", fl_cause_none: "cause not recorded",
      fl_cause_at: (t) => `Last cause recorded in the database (stop closed on ${t})`, fl_oee_of: "Order OEE", fl_oee_24h: "OEE 24 h", fl_oee_wtd: "OEE week", fl_no_of: "No order", fl_alerts: (n) => `${n} alert${n > 1 ? "s" : ""}`, fl_ok: "OK",
      nav_dashboard: "Dashboard", nav_live: "Live",
      tv: "TV mode", tv_all: "TV · all machines", tv_exit: "Exit TV", tv_hint: "TV mode · press Esc to exit",
      connecting: "Connecting to terminal…",
      online: (t) => `Terminal online · sample ${t}`,
      server_down: "MODICS server unreachable — retrying…",
      alerts: "Alerts",
      oee_today: "OEE today", oee_24h: "OEE last 24 hrs", oee_wtd: "OEE week to date (WTD)",
      oee_sub: (a, p, q, n) => `Avail. ${a}% · Perf. ${p}% · Qual. ${q}% · ${n} shifts`,
      g_trs: "Order OEE", g_trs_sub: "computed by the terminal", g_perf: "Actual rate", g_qual: "Quality",
      perf_sub: (r, th, w) => `${r} / ${th} pcs/h (${w} min)`, perf_wait: "measured after 5 min of observation",
      qual_sub: (r, t) => `${r} reject(s) out of ${t}`,
      of_title: "Shop order", so: "Shop Order", part: "Part number", tool: "Tool", cycle_target: "Target cycle",
      cav_short: "cav.", terminal_time: (t) => `terminal ${t}`,
      good: "Good", rejects: "Rejects", remaining: "Remaining",
      prog: (p, q, pct) => `${p} / ${q} pcs · ${pct} %`,
      eta: (d, real) => `Estimated end ${d} (${real ? "actual rate" : "theoretical rate"})`,
      over: (n) => `Quantity exceeded by ${n} pcs`,
      st_run: "Running", st_stop: "Stopped", st_idle: "Waiting for order", st_offline: "Offline", st_offline_lg: "Terminal offline", st_offplan: "Out of schedule", fl_since: "for",
      last_piece: (d) => `Last part ${d} ago`, observed: (m) => `History: ${m} min observed`,
      timeline_title: "Press timeline", window: (a, b) => `· production day ${a} → ${b}`,
      shift: (x) => `Shift ${x}`,
      m_av: "Observed availability", m_stops: "Stops", m_mttr: "MTTR (mean stop duration)",
      m_mtbf: "MTBF (mean run between stops)", m_cycle: "Actual mean cycle (30 min)",
      note: (t) => `History available since ${t}: it is collected by the server and reset whenever the MODICS server restarts.`,
      c_title: (n) => `Output · parts per ${n}-min slot`, target: (n, m) => `target ${n} pcs / ${m} min`,
      ds_pieces: "Parts", ds_target: "Target",
      queue_title: "Order queue (ERP)", q_count: (n) => `${n} order(s) waiting`, q_empty: "No order waiting on the terminal.",
      q_seq: "Seq.", q_qty: "Quantity", q_cycle: "Cycle (s)", q_cav: "Cav.", q_due: "Due date",
      stops_title: "Today's stops", stops_src: "MODICS database (after terminal sync)", stops_empty: "No stop recorded today.",
      s_start: "Start", s_end: "End", s_dur: "Duration (min)", s_code: "Code", s_shift: "Shift", s_setter: "Setter",
      no_code: "(no code)",
      a_none: ["No anomaly", "All indicators are within thresholds."],
      err: { no_key: "MODICS_PI_KEY not configured on the server", auth: "API key rejected by the terminal",
        http: (d) => `HTTP error ${d} from the terminal`, unreachable: (d) => `MODICS OFFLINE`, other: (d) => d },
      a: {
        offline: () => ["MODICS OFFLINE", ""],
        stopped: (p) => ["Press stopped", `For ${p.partial ? "at least " : ""}${p.min} min.`],
        over_qty: (p, n) => ["Order quantity exceeded", `Order ${p.so}: ${n(p.produced)} parts for ${n(p.qty)} requested (+${n(p.over)}, +${p.pct} %). Close the order on the terminal?`],
        rejects: (p, n) => ["High reject rate", `${n(p.rate)} % (${n(p.rejects)} rejects out of ${n(p.total)} parts).`],
        trs_low: (p, n) => ["Low order OEE", `${n(p.trs)} % (target ≥ ${p.target} %).`],
        cadence_low: (p, n) => ["Rate below target", `${n(p.rate)} pcs/h over ${p.window} min vs ${n(p.th)} pcs/h theoretical (${p.pct} %).`],
        no_pieces: (p) => ["No parts counted", `State is "Running" but the counter has not moved for over ${p.min} min: check the sensor.`],
        clock_skew: (p) => ["Terminal clock out of sync", `${p.min > 0 ? "+" : ""}${p.min} min vs the server: stops will be misdated.`],
        no_next_of: (p) => ["No next order in the ERP queue", p.done ? "The current order is complete." : `Current order ends in ~${p.min} min.`],
        no_of: () => ["No active order", "The terminal is waiting for a shop order to be started."],
      },
    },
  };
  // Langue et thème : gérés par la coque commune (static/shell.js), qui émet modics:lang / modics:theme
  const M = window.MODICS;
  let lang = M.lang;
  let T = I18N[lang], fmt = new Intl.NumberFormat(T.locale);
  const num = (v) => (v == null ? "—" : fmt.format(v));
  const set = (id, v) => ($(id).textContent = v == null || v === "" ? "—" : v);
  const css = (v) => getComputedStyle(document.body).getPropertyValue(v).trim();
  const hhmm = (sec) => new Date(sec * 1000).toLocaleTimeString(T.locale, { hour: "2-digit", minute: "2-digit" });
  const hms = (sec) => new Date(sec * 1000).toLocaleTimeString(T.locale);
  const dur = (s) => (s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`
    : `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`);
  const STATE = () => ({ run: T.st_run, stop: T.st_stop, idle: T.st_idle, offplan: T.st_offplan, offline: T.st_offline });
  const svgNS = "http://www.w3.org/2000/svg";
  let last = null, lastStops = null, clockOffset = 0, chart = null, lastOee = null, lastFleet = null, lastFleetOee = null;

  // ---------- Machine affichée ----------
  // Liste fournie par le serveur (data-machines) ; choix : ?machine= dans l'adresse, sinon dernier choix, sinon la première.
  const MACHINES = JSON.parse($("fleet").dataset.machines);
  const stored = () => { try { return localStorage.getItem("modics_live_machine"); } catch (e) { return null; } };
  let machine = [new URLSearchParams(location.search).get("machine"), stored()].find((m) => MACHINES.includes(m)) || MACHINES[0];
  const q = (m) => encodeURIComponent(m);

  function selectMachine(m) {
    if (m === machine) return;
    machine = m;
    try { localStorage.setItem("modics_live_machine", m); } catch (e) { /* stockage indisponible : choix non mémorisé */ }
    const url = new URL(location.href);
    url.searchParams.set("machine", m);
    history.replaceState(null, "", url);
    last = lastStops = lastOee = null;  // les données de l'ancienne machine ne doivent pas rester affichées
    document.title = `${T.title} ${machine}`;
    set("s-machine", machine);
    setLive(false, T.connecting);
    renderFleet();
    loadLive(); loadStops(); loadOee();
  }

  function applyLang(l) {
    lang = l; T = I18N[l]; fmt = new Intl.NumberFormat(T.locale);
    document.title = `${T.title} ${machine}`;
    M.applyI18n(T);
    if (chart) { chart.data.datasets[0].label = T.ds_pieces; chart.data.datasets[1].label = T.ds_target; }
    updateTvBtn();
    if (last) render(last); else setLive(false, T.connecting);
    if (lastStops) renderStops(lastStops);
    if (lastOee) renderOee(lastOee);
    renderFleet();
  }
  document.addEventListener("modics:lang", (e) => applyLang(e.detail));
  // Changement de thème : le graphique relit ses couleurs à la création
  document.addEventListener("modics:theme", () => { if (chart) { chart.destroy(); chart = null; } if (last) render(last); });

  // ---------- Mode TV (écran d'atelier) ----------
  // Bouton « Mode TV », ou adresse /live?tv=1 pour une TV / un navigateur en kiosque.
  let tv = false, fsEntered = false, wakeLock = null, cursorTimer = null;
  const TV_RELOAD_MS = 12 * 3600 * 1000;  // rechargement périodique : récupère les mises à jour de la page

  // tvAll : écran d'atelier qui affiche toutes les machines en cartes (?tv=all) au lieu du détail d'une seule
  let tvAll = false;
  function updateTvBtn() {
    $("tv-btn").textContent = tv && !tvAll ? T.tv_exit : T.tv;
    $("tv-all-btn").textContent = tv && tvAll ? T.tv_exit : T.tv_all;
  }
  function toast(text) {
    const el = $("tv-toast");
    el.textContent = text; el.hidden = false;
    clearTimeout(toast.timer); toast.timer = setTimeout(() => (el.hidden = true), 3000);
  }
  async function keepAwake() {
    // Empêche la mise en veille de l'écran (navigateurs récents, souvent HTTPS uniquement)
    if (!tv || document.hidden || !("wakeLock" in navigator)) return;
    try { wakeLock = await navigator.wakeLock.request("screen"); } catch (e) { /* refusé : réglages d'alimentation de la TV */ }
  }
  function setTV(on, fromUser, all = false) {
    tv = on;
    tvAll = on && all;
    document.body.classList.toggle("tv", on);
    document.body.classList.toggle("tv-fleet", tvAll);
    const url = new URL(location.href);
    if (on) url.searchParams.set("tv", tvAll ? "all" : "1"); else url.searchParams.delete("tv");
    history.replaceState(null, "", url);
    updateTvBtn();
    renderFleet();
    if (on) {
      // Le plein écran exige un clic : impossible au chargement via ?tv=1 (utiliser le mode kiosque du navigateur)
      if (fromUser && document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().then(() => (fsEntered = true)).catch(() => {});
      }
      keepAwake();
      toast(T.tv_hint);
    } else {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
      document.body.classList.remove("no-cursor");
    }
    if (chart) chart.resize();
  }
  $("tv-btn").addEventListener("click", () => setTV(!(tv && !tvAll), true));
  // La vue atelier complète vit désormais dans /fleet?tv=1 (tout le parc sur un écran, sans défilement)
  $("tv-all-btn").addEventListener("click", () => { location.href = "/fleet?tv=1"; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && tv) setTV(false); });
  // Échap en plein écran est capté par le navigateur : la sortie du plein écran quitte aussi le mode TV
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && fsEntered) { fsEntered = false; if (tv) setTV(false); }
  });
  document.addEventListener("visibilitychange", keepAwake);
  // Curseur masqué après 3 s sans mouvement
  document.addEventListener("mousemove", () => {
    document.body.classList.remove("no-cursor");
    clearTimeout(cursorTimer);
    if (tv) cursorTimer = setTimeout(() => document.body.classList.add("no-cursor"), 3000);
  });
  setInterval(() => { if (tv) location.reload(); }, TV_RELOAD_MS);

  // ---------- Horloge (alignée sur le serveur) ----------
  setInterval(() => {
    $("clock").textContent = new Date(Date.now() + clockOffset).toLocaleTimeString(T.locale);
    if (last) renderSince(last);
  }, 1000);

  function setLive(ok, text) {
    $("live").classList.toggle("off", !ok);
    $("live-text").textContent = text;
  }
  function errorText(d) {
    const e = T.err[d.error_code];
    return typeof e === "function" ? e(d.error_detail) : e || d.error_detail || "";
  }

  // ---------- Jauge SVG 240° ----------
  function arcPath(cx, cy, r, a0, a1) {
    const p = (a) => [cx + r * Math.cos((a - 90) * Math.PI / 180), cy + r * Math.sin((a - 90) * Math.PI / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1} ${y1}`;
  }
  function gauge(id, value, { warn, crit, max = 100, unit = "%" }) {
    const el = $(id);
    if (!el.firstChild) {
      const svg = document.createElementNS(svgNS, "svg");
      svg.setAttribute("viewBox", "0 0 200 160");
      const mk = (cls) => { const p = document.createElementNS(svgNS, "path"); p.setAttribute("class", cls); svg.appendChild(p); return p; };
      mk("g-track").setAttribute("d", arcPath(100, 100, 78, -120, 120));
      mk("g-val");
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", 100); t.setAttribute("y", 108); t.setAttribute("class", "g-text");
      svg.appendChild(t);
      el.appendChild(svg);
    }
    const [, val, txt] = el.firstChild.childNodes;
    const v = value == null ? null : Math.max(0, Math.min(max, value));
    val.setAttribute("d", v ? arcPath(100, 100, 78, -120, -120 + 240 * v / max) : "");
    val.setAttribute("class", "g-val " + (v == null ? "" : value < crit ? "bad" : value < warn ? "warn" : "good"));
    txt.textContent = value == null ? "—" : `${fmt.format(Math.round(value * 10) / 10)}${unit}`;
  }

  // ---------- État ----------
  function renderSince(d) {
    const m = d.metrics;
    if (!m.state_since) { $("s-since").textContent = ""; return; }
    const now = Date.now() / 1000 + clockOffset / 1000;
    $("s-since").textContent = `${m.since_partial ? "≥ " : ""}${dur(now - m.state_since)}`;
  }

  function renderState(d) {
    const m = d.metrics, s = d.status || {};
    const st = d.online ? m.state || "idle" : "offline";
    $("state").className = "state-tile " + st;
    set("s-machine", machine);
    set("s-state", d.online ? STATE()[st] : "MODICS OFFLINE");
    renderSince(d);
    $("s-last").textContent = !d.online ? ""
      : m.last_piece_ago_s != null ? T.last_piece(dur(m.last_piece_ago_s))
      : T.observed(Math.round(m.observed_min));
    // Anneau : progression de l'OF
    const qty = Number(s.quantity) || 0, prod = Number(s.produced) || 0;
    const ring = $("ring"), C = 2 * Math.PI * 52;
    ring.style.strokeDasharray = C;
    ring.style.strokeDashoffset = qty ? C * (1 - Math.min(1, prod / qty)) : C;
  }

  function alertItem(level, [title, detail]) {
    const li = document.createElement("li"); li.className = "alert " + level;
    li.appendChild(Object.assign(document.createElement("b"), { textContent: title }));
    li.appendChild(Object.assign(document.createElement("span"), { textContent: detail || "" }));
    return li;
  }
  function renderAlerts(d) {
    const alerts = d.alerts;
    $("a-count").textContent = alerts.length;
    $("a-count").className = "badge " + (alerts[0] ? alerts[0].level : "ok");
    $("alerts").replaceChildren(...(alerts.length
      ? alerts.map((a) => alertItem(a.level, (T.a[a.code] || (() => [a.code, ""]))(a.params, num, errorText(d))))
      : [alertItem("ok", T.a_none)]));
  }

  function renderOF(d) {
    const s = d.status || {}, m = d.metrics;
    set("s-so", s.shop_order);
    set("s-part", s.part_number);
    set("s-tool", s.tool_number ? `${s.tool_number} · ${s.cavities ?? "?"} ${T.cav_short}` : "");
    set("s-cycle", s.cycle_time_target && s.of_active ? `${s.cycle_time_target} s` : "");
    set("s-time", s.time ? T.terminal_time(s.time.slice(11, 19)) : "");
    const qty = Number(s.quantity) || 0, prod = Number(s.produced) || 0;
    const over = qty && prod > qty;
    $("s-bar").style.width = (qty ? Math.min(100, (prod / qty) * 100) : 0) + "%";
    $("s-bar").classList.toggle("over", !!over);
    set("s-prog", qty ? T.prog(num(prod), num(qty), Math.round((prod / qty) * 100)) : "");
    // Fin estimée : à la cadence réelle si mesurée, sinon théorique
    const rest = Number(s.remaining) || 0;
    const rate = m.cadence_pcs_h || m.cadence_th_pcs_h;
    if (s.of_active && rest > 0 && rate) {
      const end = new Date(Date.now() + (rest / rate) * 3600 * 1000);
      $("s-eta").textContent = T.eta(end.toLocaleString(T.locale, { weekday: "short", hour: "2-digit", minute: "2-digit" }), !!m.cadence_pcs_h);
    } else {
      $("s-eta").textContent = over ? T.over(num(prod - qty)) : "";
    }
    $("s-eta").classList.toggle("bad", !!over);
    set("k-good", num(s.good));
    set("k-rej", num(s.rejects));
    set("k-rest", num(s.remaining));

    const tot = (Number(s.good) || 0) + (Number(s.rejects) || 0);
    gauge("g-trs", s.of_active ? s.trs_global : null, { warn: 75, crit: 60 });
    gauge("g-perf", m.perf_live_pct, { warn: 85, crit: 70, max: 120 });
    $("g-perf-sub").textContent = m.cadence_pcs_h != null
      ? T.perf_sub(num(m.cadence_pcs_h), num(m.cadence_th_pcs_h), m.cadence_window_min) : T.perf_wait;
    gauge("g-qual", tot ? (s.good / tot) * 100 : null, { warn: 98, crit: 95 });
    $("g-qual-sub").textContent = tot ? T.qual_sub(num(s.rejects), num(tot)) : "—";
  }

  // ---------- Chronologie ----------
  // Journée de production 06:00 → 06:00 : équipes A / B / C, repère « maintenant », futur grisé
  function renderTimeline(m, now) {
    const t0 = m.window_start, span = m.window_end - m.window_start, S = STATE();
    const pos = (t) => ((t - t0) / span) * 100 + "%";
    const div = (cls, left, width) => {
      const d = document.createElement("div"); d.className = cls; d.style.left = left;
      if (width != null) d.style.width = width;
      return d;
    };
    const items = m.timeline.map((x) => {
      const seg = div("seg " + x.state, pos(x.start), Math.max(0.12, ((x.end - x.start) / span) * 100) + "%");
      seg.title = `${S[x.state]} · ${hhmm(x.start)} → ${hhmm(x.end)} (${dur(x.end - x.start)})`;
      return seg;
    });
    items.push(div("future", pos(now), (100 - ((now - t0) / span) * 100) + "%"));
    for (let h = 1; h < span / 3600; h++) items.push(div("hour-tick", pos(t0 + h * 3600)));
    m.shift_hours.slice(1).forEach((h) => items.push(div("shift-sep", pos(t0 + (h - m.shift_hours[0]) * 3600))));
    items.push(div("now", pos(now)));
    $("timeline").replaceChildren(...items);

    // Étiquettes d'équipes centrées sur chaque tranche de 8 h
    const bounds = [...m.shift_hours.map((h) => (h - m.shift_hours[0]) * 3600), span];
    $("shifts").replaceChildren(...["A", "B", "C"].map((x, i) => {
      const s = div("shift-lbl" + (now >= t0 + bounds[i] && now < t0 + bounds[i + 1] ? " current" : ""),
        (((bounds[i] + bounds[i + 1]) / 2) / span) * 100 + "%");
      s.textContent = T.shift(x);
      return s;
    }));
    // Graduations toutes les heures, de 06:00 à 06:00
    $("axis").replaceChildren(...Array.from({ length: span / 3600 + 1 }, (_, i) => {
      const s = document.createElement("span");
      s.style.left = ((i * 3600) / span) * 100 + "%"; s.textContent = hhmm(t0 + i * 3600);
      return s;
    }));
    $("t-window").textContent = T.window(hhmm(t0), hhmm(m.window_end));
    set("m-av", m.availability_pct != null ? fmt.format(m.availability_pct) + " %" : "");
    set("m-stops", m.stops_count);
    set("m-mttr", m.mttr_min != null ? fmt.format(m.mttr_min) + " min" : "");
    set("m-mtbf", m.mtbf_min != null ? fmt.format(m.mtbf_min) + " min" : "");
    set("m-cycle", m.cycle_live_s != null ? fmt.format(m.cycle_live_s) + " s" : "");
    $("m-note").textContent = m.history_start && m.history_start > t0 + m.poll_seconds * 2 ? T.note(hhmm(m.history_start)) : "";
  }

  function renderCadence(m) {
    $("c-title").textContent = T.c_title(m.bucket_minutes);
    $("b-target").textContent = m.bucket_target ? T.target(num(m.bucket_target), m.bucket_minutes) : "";
    const labels = m.buckets.map((b) => hhmm(b.t));
    const data = m.buckets.map((b) => b.pieces);
    const colors = data.map((v) => (!m.bucket_target ? css("--d-cyan") : v >= 0.85 * m.bucket_target ? css("--d-good") : v >= 0.5 * m.bucket_target ? css("--d-warn") : css("--d-bad")));
    const target = m.buckets.map(() => m.bucket_target);
    if (!chart) {
      Chart.defaults.color = css("--d-ink2");
      Chart.defaults.borderColor = css("--d-line");
      Chart.defaults.font.family = "Inter, system-ui, sans-serif";
      Chart.defaults.maintainAspectRatio = false;
      chart = new Chart($("c-cadence"), {
        type: "bar",
        data: { labels, datasets: [
          { label: T.ds_pieces, data, backgroundColor: colors, borderRadius: 2 },
          { label: T.ds_target, data: target, type: "line", borderColor: css("--d-ink2"), borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
        ] },
        options: { animation: false, plugins: { legend: { position: "bottom" } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } } } },
      });
    } else {
      chart.data.labels = labels;
      chart.data.datasets[0].data = data;
      chart.data.datasets[0].backgroundColor = colors;
      chart.data.datasets[1].data = target;
      chart.update();
    }
  }

  // ---------- Tableaux ----------
  function row(cells) {
    const tr = document.createElement("tr");
    cells.forEach(([v, cls]) => { const td = document.createElement("td"); if (cls) td.className = cls; td.textContent = v ?? ""; tr.appendChild(td); });
    return tr;
  }
  function emptyRow(cols, text) {
    const tr = document.createElement("tr"), td = document.createElement("td");
    td.colSpan = cols; td.className = "empty"; td.textContent = text; tr.appendChild(td);
    return tr;
  }

  function renderQueue(orders) {
    $("q-count").textContent = T.q_count(orders.length);
    document.querySelector("#t-queue tbody").replaceChildren(...(orders.length ? orders.map((o) => row([
      [o.sequence === 9999 ? "" : o.sequence], [o.shop_order], [o.part_number], [num(o.quantity), "num"],
      [o.cycle_time, "num"], [o.cavities, "num"], [o.due_date || ""],
    ])) : [emptyRow(7, T.q_empty)]));
  }

  function renderStops(rows) {
    document.querySelector("#t-stops tbody").replaceChildren(...(rows.length ? rows.slice(0, 20).map((r) => row([
      [r.start.slice(11, 19)], [r.end ? r.end.slice(11, 19) : ""],
      [r.duration_min == null ? "—" : num(r.duration_min), "num"], [r.code || T.no_code], [r.shift], [r.regleur],
    ])) : [emptyRow(6, T.stops_empty)]));
  }

  function render(d) {
    setLive(d.online, d.online ? T.online(hms(d.fetched_at)) : errorText(d));
    renderState(d);
    renderAlerts(d);
    if (d.online) { renderOF(d); renderQueue(d.queue); }
    renderTimeline(d.metrics, d.server_time);
    renderCadence(d.metrics);
  }

  // Les réponses arrivent dans le désordre : celle d'une machine quittée entre-temps est ignorée.
  const json = (r) => { if (!r.ok) throw new Error(r.status); return r.json(); };

  async function loadLive() {
    const m = machine;
    try {
      const d = await fetch(`/api/live?machine=${q(m)}`).then(json);
      if (m !== machine) return;
      clockOffset = d.server_time * 1000 - Date.now();
      last = d;
      render(d);
    } catch (e) {
      if (m === machine) setLive(false, T.server_down);
    }
  }

  async function loadStops() {
    const m = machine;
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    try {
      const rows = await fetch(`/api/stops?machine=${q(m)}&start=${today}`).then(json);
      if (m !== machine) return;
      lastStops = rows;
      renderStops(lastStops);
    } catch (e) { /* le tableau garde ses dernières valeurs */ }
  }

  // ---------- Vue d'ensemble ----------
  // Couleur d'une carte : état de la machine, puis catégorie de la cause d'arrêt (charte de l'atelier)
  const STOP_COLORS = { "maintenance": "#EAB308", "mecanique": "#F97316", "qualite": "#A855F7", "process": "#06B6D4",
    "production": "#EC4899", "arret planifie": "#6B8FD6" };
  const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();
  function cardColor(r) {
    if (!r.online) return "#64748B";                 // hors ligne
    if (r.state === "run") return "#22C55E";         // en production
    if (r.state === "idle") return "#334155";        // aucun OF
    if (r.state === "offplan") return "#78716C";     // hors planning (carte hachurée en plus de la couleur)
    const sc = r.stop_cause || {};
    return STOP_COLORS[norm(sc.code)] || (sc.planned ? STOP_COLORS["arret planifie"] : "#DC2626");  // autre cause : rouge
  }
  function fleetCard(r) {
    const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
    const card = el("button", `fleet-card ${r.state}${r.machine === machine ? " active" : ""}`);
    card.type = "button";
    const col = cardColor(r);  // --c : bordure, teinte et barres ; --h1/--h2 : dégradé de la plaque du mode TV
    card.style.cssText = `--c:${col};--h1:${col};--h2:color-mix(in srgb, ${col} 62%, #000)`;
    card.title = r.online ? "" : errorText(r);
    card.addEventListener("click", () => selectMachine(r.machine));

    const top = el("div", "fc-top");
    const since = r.state_since ? ` · ${r.since_partial ? "≥ " : ""}${dur(lastFleet.server_time - r.state_since)}` : "";
    top.append(el("span", "fc-name", r.machine), el("span", "fc-state", STATE()[r.state] + since));
    const of = el("div", "fc-of", r.of_active ? [r.shop_order, r.part_number].filter(Boolean).join(" · ") : r.online ? T.fl_no_of : errorText(r));
    const bar = el("div", "fc-bar"), fill = document.createElement("i");
    const pct = r.of_active && r.quantity ? Math.min(100, (r.produced / r.quantity) * 100) : 0;
    fill.style.width = pct + "%";
    bar.appendChild(fill);

    const foot = el("div", "fc-foot");
    const trs = el("span", "fc-trs", r.trs != null ? `${T.g_trs} ${fmt.format(Math.round(r.trs))} %` : "");
    if (r.trs != null) trs.classList.add(r.trs < 60 ? "bad" : r.trs < 75 ? "warn" : "good");
    const worst = r.alerts[0];
    const badge = el("span", `badge ${r.online ? worst || "ok" : "crit"}`, r.alerts.length ? T.fl_alerts(r.alerts.length) : r.online ? T.fl_ok : "!");
    foot.append(trs, badge);
    const prog = el("div", "fc-prog", r.of_active && r.quantity ? T.prog(num(r.produced), num(r.quantity), Math.round(pct)) : "");

    // Mode TV (lecture à distance) : nom, shop order, référence et 3 TRS en grand (masqué en affichage normal).
    // La couleur de la carte porte déjà l'état ; hors ligne / sans OF, une ligne de texte remplace shop order et référence.
    const tvEl = el("div", "fc-tv");
    const field = (label, value, cls) => {
      const f = el("div", "fc-field" + (cls ? " " + cls : ""));
      f.append(el("span", "fc-lab", label), el("span", "fc-fval", value || "—"));
      return f;
    };
    const ids = el("div", "fc-ids");
    if (r.of_active) ids.append(field(T.fl_so, r.shop_order), field(T.fl_pn, r.part_number, "fc-pn"));
    else if (r.state !== "offplan") ids.appendChild(el("span", "fc-status", r.online ? T.fl_no_of : STATE().offline));  // hors planning : le bandeau dédié suffit
    // TRS : OF en cours (terminal), dernières 24 h et semaine en cours (base MODICS, /api/live/oee/all)
    const per = (lastFleetOee && lastFleetOee.machines[r.machine]) || {};
    const oee = (label, v) => {
      const m = el("div", "fc-metric");
      const val = el("span", "fc-val" + (v == null ? "" : v < 60 ? " bad" : v < 75 ? " warn" : " good"));
      val.append(v == null ? "—" : fmt.format(Math.round(v)), ...(v == null ? [] : [el("small", null, "%")]));
      m.append(val, el("span", "fc-lab", label));
      return m;
    };
    const oees = el("div", "fc-oees");
    oees.append(oee(T.fl_oee_of, r.of_active ? r.trs : null),
      oee(T.fl_oee_24h, per.last24h ? per.last24h.oee : null), oee(T.fl_oee_wtd, per.wtd ? per.wtd.oee : null));
    // Progression de la production : pièces produites / quantité de l'OF (barre rayée au-delà de 100 %)
    const out = el("div", "fc-out");
    if (r.of_active && r.quantity) {
      const p = (r.produced || 0) / r.quantity * 100;
      const row = el("div", "fc-out-row");
      row.append(el("span", "fc-out-qty", `${num(r.produced)} / ${num(r.quantity)} ${T.fl_pcs}`), el("span", "fc-out-pct", `${fmt.format(Math.round(p))} %`));
      const track = el("div", "fc-out-bar" + (p > 100 ? " over" : "")), fillBar = document.createElement("i");
      fillBar.style.width = Math.min(100, p) + "%";
      track.appendChild(fillBar);
      out.append(row, track);
    }
    // Plaque d'identité : nom de la machine très grand (blanc sur la couleur de l'état), shop order et référence à droite
    const head = el("div", "fc-head");
    head.append(el("span", "fc-hname", r.machine), ids);
    // Machine à l'arrêt : bandeau rouge avec la dernière cause enregistrée en base et la durée de l'arrêt
    let cause = null;
    if (r.state === "stop") {
      cause = el("div", "fc-cause");
      const code = r.stop_cause && r.stop_cause.code;
      const sc = r.stop_cause || {};
      const label = el("span", "fc-cause-txt", `${sc.planned ? T.fl_stop_planned : T.fl_stop} · ${code || T.fl_cause_none}`);
      if (sc.at) label.title = T.fl_cause_at(sc.at);
      cause.append(label);
      // Début d'arrêt exact de la table d'état en direct si disponible, sinon durée mesurée par le sampler
      if (sc.since) cause.append(el("span", "fc-cause-dur", dur(Math.max(0, lastFleet.server_time - sc.since))));
      else if (r.state_since) cause.append(el("span", "fc-cause-dur", `${r.since_partial ? "≥ " : ""}${dur(lastFleet.server_time - r.state_since)}`));
      if (sc.planned) cause.classList.add("planned");
    }
    // Presse hors planning (fin de production, non reprogrammée) : bandeau dédié à la place de la progression
    let off = null;
    if (r.state === "offplan") {
      off = el("div", "fc-offplan");
      off.append(el("span", "fc-off-txt", STATE().offplan.toUpperCase()));
      if (r.off_since) off.append(el("span", "fc-off-dur", `${T.fl_since} ${dur(Math.max(0, lastFleet.server_time - r.off_since))}`));
    }
    tvEl.append(...[head, cause, off, out, oees].filter(Boolean));
    card.append(top, of, bar, prog, foot, tvEl);
    return card;
  }

  // Grille adaptée à l'écran : on choisit le nombre de colonnes qui donne des cartes proches d'un format 16:9
  // (paysage → plusieurs colonnes ; portrait → 1 à 2 colonnes), quel que soit le nombre de machines.
  const CARD_ASPECT = 2.4;  // le contenu d'une carte TV (nom, ids, 3 TRS) est plus large que haut
  // Atelier complet : au-delà d'une page de 4 × 4 cartes (2 × 4 en portrait) les machines défilent par groupes,
  // pour garder des cartes grandes et lisibles de loin plutôt que d'en afficher 28 minuscules.
  const PAGE_MS = 10000;
  let tvPage = 0, pageTimer = null, pageFlip = false;
  function pageLayout() {  // 4 machines par page : 2 × 2 en paysage, 1 × 4 en portrait
    return window.innerWidth >= window.innerHeight ? { cols: 2, rows: 2 } : { cols: 1, rows: 4 };
  }
  function fleetGrid(n) {
    const w = window.innerWidth, h = window.innerHeight, aspect = CARD_ASPECT;
    let best = { cols: 1, rows: n }, bestScore = Infinity;
    for (let cols = 1; cols <= n; cols++) {
      const rows = Math.ceil(n / cols);
      const score = Math.abs(Math.log((w / cols) / (h / rows) / aspect)) + (cols * rows - n) * 0.02;  // léger malus aux cases vides
      if (score < bestScore) { bestScore = score; best = { cols, rows }; }
    }
    return best;
  }
  window.addEventListener("resize", () => renderFleet());

  function renderFleet() {
    if (!lastFleet) return;
    // Vue atelier : seules les machines en ligne défilent (les hors ligne sont comptées dans l'indicateur de page)
    const online = lastFleet.machines.filter(r => r.online);
    const all = tvAll && online.length ? online : lastFleet.machines, box = $("fleet");
    const skipped = lastFleet.machines.length - all.length;
    const page = pageLayout(), size = page.cols * page.rows;
    const paged = tvAll && all.length > size, pages = paged ? Math.ceil(all.length / size) : 1;
    if (tvPage >= pages) tvPage = 0;
    const shown = paged ? all.slice(tvPage * size, (tvPage + 1) * size) : all;
    const partial = paged && shown.length < size;  // dernière page incomplète : ses cartes occupent tout l'écran
    const { cols, rows } = paged && !partial ? page : fleetGrid(shown.length);
    const cards = shown.map(fleetCard);
    box.style.setProperty("--fleet-cols", cols);
    box.style.setProperty("--fleet-rows", rows);
    box.replaceChildren(...cards);
    box.classList.toggle("paged", paged);
    updatePager(pages, skipped);
    if (pageFlip) { box.classList.remove("flip"); void box.offsetWidth; box.classList.add("flip"); pageFlip = false; }
    if (!tvAll) return;
    // Cases vides sur la dernière ligne (ex. 7 machines en 3×3) : la dernière carte les occupe
    // (en défilement, toutes les pages gardent la même taille de carte : les cases libres restent vides)
    const empty = cols * rows - cards.length;
    if (empty > 0 && (!paged || partial)) cards[cards.length - 1].style.gridColumn = `span ${empty + 1}`;
    // Taille du texte d'après la case réelle d'une carte : contenu ≈ 66 unités de haut (bandeau d'arrêt compris, pour que
    // la taille du texte ne change pas quand une machine s'arrête) et ≈ 90 de large
    const cu = Math.min(box.clientHeight / rows / (paged ? 64 : 66), box.clientWidth / cols / 90);
    if (cu > 0) box.style.setProperty("--cu", cu + "px");
  }

  // Indicateur de page (points + « 1 / 2 ») à côté de l'horloge ; le défilement ne tourne que s'il y a plusieurs pages
  function updatePager(pages, skipped) {
    let p = $("tv-page");
    if (!p) { p = document.createElement("div"); p.id = "tv-page"; p.className = "tv-page"; $("clock").before(p); }
    p.hidden = !(tvAll && (pages > 1 || skipped > 0));
    if (pages <= 1 || !tvAll) { clearInterval(pageTimer); pageTimer = null; }
    if (p.hidden) return;
    const txt = (s) => Object.assign(document.createElement("span"), { textContent: s });
    p.replaceChildren(...(pages > 1 ? [...Array.from({ length: pages }, (_, i) => { const d = document.createElement("i"); if (i === tvPage) d.className = "on"; return d; }),
      txt(`${tvPage + 1} / ${pages}`)] : []), ...(skipped ? [txt(`· ${skipped} ${STATE().offline.toLowerCase()}`)] : []));
    if (pages > 1 && !pageTimer) pageTimer = setInterval(() => { tvPage++; pageFlip = true; renderFleet(); }, PAGE_MS);
  }

  async function loadFleet() {
    try { lastFleet = await fetch("/api/live/fleet").then(json); renderFleet(); } catch (e) { /* garde la dernière vue */ }
  }
  async function loadFleetOee() {
    try { lastFleetOee = await fetch("/api/live/oee/all").then(json); renderFleet(); } catch (e) { /* garde les dernières valeurs */ }
  }

  function renderOee(o) {
    [["o-today", o.today], ["o-24h", o.last24h], ["o-wtd", o.wtd]].forEach(([id, b]) => {
      gauge(id, b.oee, { warn: 75, crit: 60 });
      $(id + "-sub").textContent = b.oee == null ? "—" : T.oee_sub(b.availability, b.performance, b.quality, b.shifts_count);
    });
  }
  async function loadOee() {
    const m = machine;
    try {
      const o = await fetch(`/api/live/oee?machine=${q(m)}`).then(json);
      if (m !== machine) return;
      lastOee = o; renderOee(lastOee);
    } catch (e) { /* garde les dernières valeurs */ }
  }

  applyLang(lang);
  loadOee();
  setInterval(() => { if (!document.hidden) loadOee(); }, STOPS_MS);
  const tvParam = new URLSearchParams(location.search).get("tv");
  if (tvParam === "all") { location.replace("/fleet?tv=1"); return; }  // ancienne adresse des TV d'atelier
  if (tvParam === "1") setTV(true, false);
  loadLive();
  loadStops();
  loadFleet();
  loadFleetOee();
  setInterval(() => { if (!document.hidden) loadFleetOee(); }, STOPS_MS);
  setInterval(() => { if (!document.hidden) { loadLive(); loadFleet(); } }, POLL_MS);
  setInterval(() => { if (!document.hidden) loadStops(); }, STOPS_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { loadLive(); loadStops(); loadFleet(); } });
})();
