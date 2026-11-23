"""
Supervision temps réel : relais vers l'API HTTP du terminal Raspberry Pi de la presse
(script moul.py, port 8080). Le navigateur n'appelle que ce serveur : la clé API du Pi
reste côté serveur et il n'y a pas de problème CORS / contenu mixte.

Une machine = un terminal. Un fil d'échantillonnage par machine interroge son terminal toutes les
POLL_SECONDS (une machine injoignable ne ralentit donc pas les autres) et garde HISTORY_HOURS
d'historique en mémoire (perdu au redémarrage du serveur). On en dérive ce que le terminal ne
fournit pas : chronologie des états, cadence réelle vs théorique, MTBF / MTTR, alertes.

Machines : data_source.MACHINES (MODICS_MACHINES), ex. « PRS 63,PRS 68,PRS 78,PRS 80,PRS 81 ».

Variables d'environnement :
  MODICS_PI_KEY : clé du terminal ([api] api_key de config_modics.ini) — obligatoire
  MODICS_PI_KEY_<NN> : clé propre à la machine PRS <NN> si elle diffère de MODICS_PI_KEY
  MODICS_PI_URL_<NN> : ex. http://192.168.80.50:8080 pour PRS <NN> ; si absente, l'IP est lue dans
                  IP_Address_Table_Machines_Mould.IP_address_Mould_<NN> (mise à jour par le Pi au démarrage)
  MODICS_PI_PORT : port si l'IP vient de la base (défaut 8080)
  MODICS_PI_POLL : période d'échantillonnage en secondes (défaut 5)

Routes : GET /live (page)  ·  GET /api/live?machine= (état, file d'OF, alertes, indicateurs, historique)
         GET /api/live/fleet (résumé de toutes les machines)
"""
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, render_template, request
from sqlalchemy import text

import data_source
import db
import machines_config

PI_PORT = machines_config.port()
POLL_SECONDS = int(os.environ.get("MODICS_PI_POLL", "5"))
POLL_WORKERS = int(os.environ.get("MODICS_PI_WORKERS", "16"))   # terminaux interrogés en parallèle
OFFLINE_POLL_SECONDS = int(os.environ.get("MODICS_PI_OFFLINE_POLL", "30"))  # terminal injoignable : on insiste moins
FLEET_TTL = 2        # la vue d'ensemble est mise en cache : N écrans ouverts = un seul calcul toutes les 2 s
TIMEOUT = 3          # le Pi est sur le réseau local : au-delà, on le considère injoignable
IP_TTL = 300         # l'IP lue en base est relue toutes les 5 min
HISTORY_HOURS = 24          # couvre toujours la journée de production entière
DAY_START_HOUR = 6          # journée de production : 06:00 → 06:00 (Shift A, B, C)
SHIFT_HOURS = [6, 14, 22]   # débuts des équipes A, B, C
BUCKET_SECONDS = 600         # histogramme de cadence : tranches de 10 min
CADENCE_WINDOW = 30 * 60     # cadence « live » mesurée sur les 30 dernières minutes

# Seuils d'alerte
REJECT_WARN, REJECT_CRIT = 2.0, 5.0      # taux de rebut (%)
TRS_WARN, TRS_CRIT = 75.0, 60.0          # TRS de l'OF (%)
CADENCE_WARN = 85.0                      # cadence réelle / théorique (%)
STOP_CRIT_MIN = 10                       # arrêt en cours : critique au-delà de N min
CLOCK_SKEW_WARN = 120                    # écart d'horloge Pi / serveur (s)
NEXT_OF_WARN_H = 1.0                     # file ERP vide et fin d'OF dans moins de N h

logger = logging.getLogger(__name__)
bp = Blueprint("pi_live", __name__)
_lock = threading.Lock()


class _Machine:
    """Terminal d'une presse : dernier échantillon, historique, IP en cache, fil d'échantillonnage."""

    def __init__(self, name):
        self.name = name
        # Numéro de presse : sert de suffixe à la colonne IP et aux variables d'environnement.
        # Uniquement des chiffres : il est inséré dans une requête SQL (nom de colonne).
        self.num, self.url, self.key = machines_config.machine(name)
        self.maintenance = machines_config.is_maintenance(name)
        self.next_at = 0.0       # prochain échantillonnage (reculé quand le terminal est injoignable)
        self.busy = False        # un échantillonnage est en cours
        self.latest = {}
        self.history = deque(maxlen=HISTORY_HOURS * 3600 // POLL_SECONDS)
        self.ip = {"at": 0.0, "url": None}
        self.started = False


_machines = {m: _Machine(m) for m in data_source.MACHINES}


def _machine(name):
    """Machine demandée (défaut : la première) ; 404 si elle n'est pas dans la liste configurée."""
    name = name or next(iter(_machines), None)
    if name not in _machines:
        abort(404, description=f"Machine inconnue : {name}")
    return _machines[name]


# ---------- Accès au terminal ----------

def _base_url(mc):
    if mc.url:
        return mc.url
    if time.time() - mc.ip["at"] > IP_TTL or not mc.ip["url"]:
        if not data_source.SQL_CONN:
            raise RuntimeError(f"MODICS_PI_URL_{mc.num} non configurée et pas de base MODICS pour lire l'IP du Pi")
        if not mc.num:
            raise RuntimeError(f"Numéro de presse introuvable dans « {mc.name} »")
        with db.get_engine(data_source.SQL_CONN).connect() as conn:
            ip = conn.execute(text(f"SELECT TOP 1 IP_address_Mould_{mc.num} FROM IP_Address_Table_Machines_Mould")).scalar()
        if not ip:
            raise RuntimeError(f"IP du terminal {mc.name} absente de IP_Address_Table_Machines_Mould")
        mc.ip.update(at=time.time(), url=f"http://{str(ip).strip()}:{PI_PORT}")
    return mc.ip["url"]


def _get(mc, path):
    req = urllib.request.Request(_base_url(mc) + path, headers={"X-Api-Key": mc.key or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch(mc):
    """error_code (no_key | auth | http | unreachable | other) + error_detail : la page traduit le message."""
    out = {"fetched_at": time.time(), "online": False, "error_code": None, "error_detail": None,
           "status": None, "queue": []}
    if not mc.key:
        out["error_code"] = "no_key"
        return out
    try:
        out["status"] = _get(mc, "/api/v1/status")
        out["queue"] = _get(mc, "/api/v1/queue").get("orders", [])
        out["online"] = True
    except urllib.error.HTTPError as e:
        out["error_code"], out["error_detail"] = ("auth", None) if e.code == 401 else ("http", str(e.code))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        url = mc.url or mc.ip["url"]
        mc.ip["at"] = 0.0  # l'IP a peut-être changé (redémarrage du Pi) : relue au prochain appel
        out["error_code"], out["error_detail"] = "unreachable", f"{url} ({getattr(e, 'reason', e)})"
    except Exception as e:  # base injoignable pour l'IP, réponse illisible…
        out["error_code"], out["error_detail"] = "other", str(e)
    return out


def _state(data):
    """run | stop | idle | offplan | offline. Le terminal renvoie « Production », « Arret »/« Arrêt » ou ''.
    offplan : l'opérateur a mis la presse hors planning après la fin de production (champ out_of_plan du terminal)."""
    if not data["online"]:
        return "offline"
    s = data["status"]
    if s.get("out_of_plan"):
        return "offplan"
    if not s.get("of_active"):
        return "idle"
    st = str(s.get("state") or "").lower()
    if st == "production":
        return "run"
    if st.startswith("arr"):
        return "stop"
    return "idle"


# ---------- Échantillonnage ----------

def _poll_once(mc):
    data = _fetch(mc)
    s = data["status"] or {}
    sample = {"t": data["fetched_at"], "state": _state(data), "so": s.get("shop_order"),
              "produced": s.get("produced") if data["online"] else None}
    with _lock:
        mc.latest.clear()
        mc.latest.update(data)
        mc.history.append(sample)


def _run_poll(mc):
    try:
        _poll_once(mc)
    except Exception:
        logger.exception("Échantillonnage du terminal %s", mc.name)
    finally:
        online = mc.latest.get("online")
        mc.next_at = time.time() + (POLL_SECONDS if online or online is None else OFFLINE_POLL_SECONDS)
        mc.busy = False


def _scheduler():
    """Un seul fil d'ordonnancement + un pool de POLL_WORKERS : un terminal lent ou injoignable
    n'en retarde plus d'autres, et le nombre de fils ne dépend plus du nombre de machines."""
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=POLL_WORKERS, thread_name_prefix="pi-live")
    while True:
        now = time.time()
        for mc in _machines.values():
            if mc.started and not mc.busy and now >= mc.next_at:
                mc.busy = True
                pool.submit(_run_poll, mc)
        time.sleep(0.5)


def start_sampler():
    """Active l'échantillonnage de toutes les machines ayant une clé (une seule fois)."""
    for mc in _machines.values():
        with _lock:
            if mc.started or not mc.key or mc.maintenance:
                continue
            mc.started = True
    with _lock:
        if not _saver["sched"] and any(m.started for m in _machines.values()):
            _saver["sched"] = True
            threading.Thread(target=_scheduler, name="pi-live-scheduler", daemon=True).start()
    with _lock:
        if _saver["started"] or not data_source.SQL_CONN or not any(m.started for m in _machines.values()):
            return
        _saver["started"] = True
    threading.Thread(target=_save_loop, name="pi-timeline-saver", daemon=True).start()


# ---------- Sauvegarde de la chronologie (base MODICS) ----------
# La chronologie vit en mémoire (perdue au redémarrage) : on en enregistre les plages d'état, par journée
# de production 06:00 → 06:00, dans Machine_Timeline_Mould. Une plage = (machine, jour, début) ; sa fin est
# mise à jour tant qu'elle est en cours, donc relancer l'enregistrement ne crée jamais de doublon.

SAVE_SECONDS = 60
_saver = {"started": False, "table_ok": False, "sched": False}

_DDL = """
IF OBJECT_ID('dbo.Machine_Timeline_Mould', 'U') IS NULL
CREATE TABLE dbo.Machine_Timeline_Mould (
    machine     NVARCHAR(20)  NOT NULL,
    prod_day    DATE          NOT NULL,   -- journée de production (06:00 → 06:00) ; date de son début
    state       NVARCHAR(10)  NOT NULL,   -- run | stop | idle | offplan | offline
    start_ts    DATETIME2(0)  NOT NULL,
    end_ts      DATETIME2(0)  NOT NULL,
    duration_s  INT           NOT NULL,
    updated_at  DATETIME2(0)  NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_Machine_Timeline_Mould PRIMARY KEY (machine, prod_day, start_ts)
)"""

_MERGE = """
MERGE dbo.Machine_Timeline_Mould AS t
USING (SELECT :machine AS machine, :prod_day AS prod_day, :start_ts AS start_ts) AS s
   ON t.machine = s.machine AND t.prod_day = s.prod_day AND t.start_ts = s.start_ts
WHEN MATCHED AND (t.end_ts <> :end_ts OR t.state <> :state) THEN
    UPDATE SET state = :state, end_ts = :end_ts, duration_s = :duration_s, updated_at = SYSDATETIME()
WHEN NOT MATCHED THEN
    INSERT (machine, prod_day, state, start_ts, end_ts, duration_s) VALUES (:machine, :prod_day, :state, :start_ts, :end_ts, :duration_s);"""


def _timeline_rows(mc, now):
    """Plages de la journée de production en cours et de la précédente, coupées à 06:00."""
    with _lock:
        hist = list(mc.history)
    segs = _segments(hist, now)
    today = _day_start(now)
    rows = []
    for w0 in (today - 24 * 3600, today):
        w1 = w0 + 24 * 3600
        for x in segs:
            s, e = max(x["start"], w0), min(x["end"], w1)
            if e <= s:
                continue
            s_dt, e_dt = datetime.fromtimestamp(s).replace(microsecond=0), datetime.fromtimestamp(e).replace(microsecond=0)
            rows.append({"machine": mc.name, "prod_day": datetime.fromtimestamp(w0).date(), "state": x["state"],
                         "start_ts": s_dt, "end_ts": e_dt, "duration_s": int((e_dt - s_dt).total_seconds())})
    return rows


def save_timelines(now=None):
    """Enregistre les chronologies de toutes les machines ; renvoie le nombre de plages écrites."""
    now = now or time.time()
    rows = [r for mc in _machines.values() for r in _timeline_rows(mc, now)]
    eng = db.get_engine(data_source.SQL_CONN)
    with eng.begin() as conn:
        if not _saver["table_ok"]:
            conn.execute(text(_DDL))
            _saver["table_ok"] = True
        if rows:
            conn.execute(text(_MERGE), rows)
    return len(rows)


def _save_loop():
    while True:
        time.sleep(SAVE_SECONDS)
        try:
            save_timelines()
        except Exception:
            logger.exception("Sauvegarde de la chronologie")


# ---------- Indicateurs dérivés de l'historique ----------

def _segments(hist, now):
    """Plages d'état contiguës ; un trou (serveur arrêté) coupe la plage."""
    segs = []
    for s in hist:
        end = min(s["t"] + POLL_SECONDS, now)
        if segs and segs[-1]["state"] == s["state"] and s["t"] - segs[-1]["end"] <= max(2 * POLL_SECONDS, OFFLINE_POLL_SECONDS + POLL_SECONDS):
            segs[-1]["end"] = end
        else:
            segs.append({"state": s["state"], "start": s["t"], "end": end})
    return segs


def _pieces(hist):
    """(instant, pièces comptées depuis l'échantillon précédent). Nouvel OF = compteur remis à zéro."""
    out, prev = [], None
    for s in hist:
        if s["produced"] is None:
            prev = None
            continue
        if prev is not None:
            d = s["produced"] - prev["produced"]
            out.append((s["t"], d if d > 0 and s["so"] == prev["so"] else 0))
        prev = s
    return out


def _day_start(now):
    """Début de la journée de production en cours (06:00 ; avant 06:00 → 06:00 la veille)."""
    d = datetime.fromtimestamp(now)
    start = d.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
    if d < start:
        start -= timedelta(days=1)
    return start.timestamp()


def _metrics(hist, status, now):
    segs = _segments(hist, now)
    pieces = _pieces(hist)
    day = _day_start(now)
    m = {"window_start": day, "window_end": day + 24 * 3600, "shift_hours": SHIFT_HOURS,
         "poll_seconds": POLL_SECONDS, "history_start": hist[0]["t"] if hist else None,
         "observed_min": round((now - hist[0]["t"]) / 60, 1) if hist else 0}

    # État courant : sur tout l'historique (un arrêt commencé avant 06:00 garde sa vraie durée)
    cur = segs[-1] if segs else None
    m["state"] = cur["state"] if cur else None
    m["state_since"] = cur["start"] if cur else None
    m["since_partial"] = bool(cur) and cur is segs[0]  # l'état a commencé avant le début de l'historique

    # Indicateurs de la journée de production : plages coupées à 06:00
    segs = [dict(x, start=max(x["start"], day)) for x in segs if x["end"] > day]
    pieces = [(t, d) for t, d in pieces if t >= day]
    run = [x["end"] - x["start"] for x in segs if x["state"] == "run"]
    stops = [x["end"] - x["start"] for x in segs if x["state"] == "stop"]
    m["availability_pct"] = round(100 * sum(run) / (sum(run) + sum(stops)), 1) if (run or stops) and sum(run) + sum(stops) > 0 else None
    m["stops_count"] = len(stops)
    m["mttr_min"] = round(sum(stops) / len(stops) / 60, 1) if stops else None
    m["mtbf_min"] = round(sum(run) / len(run) / 60, 1) if run else None

    cav = float(status.get("cavities") or 0)
    ct = float(status.get("cycle_time_target") or 0)
    m["cadence_th_pcs_h"] = round(cav * 3600 / ct) if cav and ct else None
    span = min(CADENCE_WINDOW, now - hist[0]["t"]) if hist else 0
    recent = sum(d for t, d in pieces if t >= now - CADENCE_WINDOW)
    m["cadence_pcs_h"] = round(recent * 3600 / span) if span >= 300 else None  # au moins 5 min observées
    m["cadence_window_min"] = round(span / 60)
    m["perf_live_pct"] = (round(100 * m["cadence_pcs_h"] / m["cadence_th_pcs_h"], 1)
                          if m["cadence_pcs_h"] is not None and m["cadence_th_pcs_h"] else None)
    m["cycle_live_s"] = round(cav * 3600 / m["cadence_pcs_h"], 1) if m["cadence_pcs_h"] and cav else None
    last = next((t for t, d in reversed(pieces) if d > 0), None)
    m["last_piece_ago_s"] = round(now - last) if last else None

    # Histogramme : pièces par tranche de 10 min depuis 06:00 (ou depuis le début de l'historique)
    start = day
    buckets = {}
    for t, d in pieces:
        b = int((t - start) // BUCKET_SECONDS)
        buckets[b] = buckets.get(b, 0) + d
    first = max(0, int((hist[0]["t"] - start) // BUCKET_SECONDS)) if hist else 0
    last_b = int((now - start) // BUCKET_SECONDS)
    m["buckets"] = [{"t": start + b * BUCKET_SECONDS, "pieces": buckets.get(b, 0)} for b in range(first, last_b + 1)]
    m["bucket_target"] = round(cav * BUCKET_SECONDS / ct) if cav and ct else None
    m["bucket_minutes"] = BUCKET_SECONDS // 60
    m["timeline"] = [{"state": x["state"], "start": round(x["start"]), "end": round(x["end"])} for x in segs]
    return m


def _alert(level, code, **params):
    """Alerte = code + valeurs ; le texte (FR/EN) est composé par la page (static/live.js)."""
    return {"level": level, "code": code, "params": params}


def _alerts(data, m, now):
    """Alertes de supervision, de la plus grave à la moins grave."""
    if not data.get("online"):
        return [_alert("crit", "offline", error=data.get("error_code"), detail=data.get("error_detail"))]
    s, out = data["status"], []

    if m["state"] == "stop" and m["state_since"]:
        mins = (now - m["state_since"]) / 60
        out.append(_alert("crit" if mins >= STOP_CRIT_MIN else "warn", "stopped",
                          min=round(mins), partial=m["since_partial"]))

    qty, prod = s.get("quantity") or 0, s.get("produced") or 0
    if s.get("of_active") and qty and prod > qty:
        out.append(_alert("warn", "over_qty", so=s.get("shop_order"), produced=prod, qty=qty,
                          over=prod - qty, pct=round((prod - qty) / qty * 100)))

    good, rej = s.get("good") or 0, s.get("rejects") or 0
    if good + rej >= 50:
        rate = rej / (good + rej) * 100
        if rate >= REJECT_WARN:
            out.append(_alert("crit" if rate >= REJECT_CRIT else "warn", "rejects",
                              rate=round(rate, 1), rejects=rej, total=good + rej))

    trs = s.get("trs_global")
    if s.get("of_active") and trs and trs < TRS_WARN:
        out.append(_alert("crit" if trs < TRS_CRIT else "warn", "trs_low", trs=round(trs, 1), target=TRS_WARN))

    if m["state"] == "run" and m["perf_live_pct"] is not None and m["perf_live_pct"] < CADENCE_WARN:
        out.append(_alert("warn", "cadence_low", rate=m["cadence_pcs_h"], th=m["cadence_th_pcs_h"],
                          window=m["cadence_window_min"], pct=round(m["perf_live_pct"])))

    # État « Production » sans pièce comptée : capteur noyau ou câblage à vérifier
    ct = float(s.get("cycle_time_target") or 0)
    silent = max(300, 3 * ct)
    if m["state"] == "run" and m["state_since"] and now - m["state_since"] > silent and \
            (m["last_piece_ago_s"] is None or m["last_piece_ago_s"] > silent):
        out.append(_alert("warn", "no_pieces", min=round(silent / 60)))

    if s.get("time"):
        try:
            skew = time.mktime(time.strptime(s["time"][:19], "%Y-%m-%dT%H:%M:%S")) - data["fetched_at"]
            if abs(skew) > CLOCK_SKEW_WARN:
                out.append(_alert("warn", "clock_skew", min=round(skew / 60)))
        except ValueError:
            pass

    rest, cav = s.get("remaining") or 0, float(s.get("cavities") or 0)
    if s.get("of_active") and not data.get("queue") and cav and ct:
        hours_left = rest / cav * ct / 3600
        if hours_left < NEXT_OF_WARN_H:
            out.append(_alert("info", "no_next_of", done=rest <= 0, min=round(hours_left * 60)))
    if not s.get("of_active") and not s.get("out_of_plan"):  # hors planning : aucun OF attendu, pas d'alerte
        out.append(_alert("info", "no_of"))

    order = {"crit": 0, "warn": 1, "info": 2}
    return sorted(out, key=lambda a: order[a["level"]])


# ---------- Routes ----------

def _snapshot(mc):
    """Dernier échantillon + indicateurs + alertes d'une machine."""
    if mc.maintenance:
        now = time.time()
        m = {"state": "maintenance", "state_since": None, "since_partial": False,
             "poll_seconds": POLL_SECONDS, "history_start": None, "observed_min": 0,
             "window_start": _day_start(now), "window_end": _day_start(now) + 24 * 3600,
             "shift_hours": SHIFT_HOURS, "availability_pct": None, "stops_count": 0,
             "mttr_min": None, "mtbf_min": None, "cadence_th_pcs_h": None,
             "cadence_pcs_h": None, "cadence_window_min": 0, "perf_live_pct": None,
             "cycle_live_s": None, "last_piece_ago_s": None,
             "buckets": [], "bucket_target": None, "bucket_minutes": BUCKET_SECONDS // 60, "timeline": []}
        return {"machine": mc.name, "online": False, "maintenance": True,
                "error_code": None, "error_detail": None, "status": None, "queue": [],
                "state": "maintenance", "server_time": now, "metrics": m, "alerts": []}
    with _lock:
        empty = not mc.latest
    if empty:  # premier appel : on n'attend pas le fil d'échantillonnage
        _poll_once(mc)
    now = time.time()
    with _lock:
        data, hist = dict(mc.latest), list(mc.history)
    m = _metrics(hist, data.get("status") or {}, now)
    return {**data, "machine": mc.name, "server_time": now, "metrics": m, "alerts": _alerts(data, m, now)}


@bp.route("/live")
def live_page():
    return render_template("live.html", active="live", machines=list(_machines))


@bp.route("/api/live")
def api_live():
    start_sampler()
    return jsonify(_snapshot(_machine(request.args.get("machine"))))


@bp.route("/api/live/timeline")
def api_live_timeline():
    """Chronologie enregistrée en base : ?machine=&day=YYYY-MM-DD (défaut : journée de production en cours)."""
    if not data_source.SQL_CONN:
        abort(503, description="Base MODICS non configurée")
    mc = _machine(request.args.get("machine"))
    day = request.args.get("day") or datetime.fromtimestamp(_day_start(time.time())).strftime("%Y-%m-%d")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        abort(400, description="day doit être au format YYYY-MM-DD")
    with db.get_engine(data_source.SQL_CONN).connect() as conn:
        if not conn.execute(text("SELECT OBJECT_ID('dbo.Machine_Timeline_Mould', 'U')")).scalar():
            return jsonify({"machine": mc.name, "day": day, "segments": []})
        rows = conn.execute(text("SELECT state, start_ts, end_ts, duration_s FROM dbo.Machine_Timeline_Mould "
                                 "WHERE machine = :m AND prod_day = :d ORDER BY start_ts"), {"m": mc.name, "d": day}).fetchall()
    return jsonify({"machine": mc.name, "day": day, "segments": [
        {"state": r[0], "start": r[1].strftime("%Y-%m-%d %H:%M:%S"), "end": r[2].strftime("%Y-%m-%d %H:%M:%S"), "duration_s": r[3]}
        for r in rows]})


STOP_CAUSE_TTL = 15   # la page interroge toutes les 3 s : la base n'est lue qu'une fois par TTL et par machine
_stop_cause = {}


LIVE_STATE_TTL = 3        # secondes : la table est lue en entier, une fois par TTL pour toutes les machines
LIVE_STATE_MAX_AGE = 180  # au-delà, la ligne n'est plus mise à jour (terminal éteint) : on ne s'y fie plus
_live_state = {"at": 0, "rows": {}}


def _live_state_row(machine):
    """Ligne de dbo.Machine_Live_State_Mould (état en direct écrit par le terminal) : dict ou None si absente/périmée.
    Contrairement à Machine_Stop_Table_Mould, elle porte la cause de l'arrêt EN COURS, son début et l'indicateur « planifié »."""
    if not data_source.SQL_CONN:
        return None
    if time.time() - _live_state["at"] > LIVE_STATE_TTL:
        rows = {}
        try:
            with db.get_engine(data_source.SQL_CONN).connect() as conn:
                for r in conn.execute(text(
                        "SELECT Machine_Name_Mould, State_Mould, Code_Stop_Mould, Stop_Start_Mould, Shop_Order_Mould, "
                        "Part_Number_Mould, Shift_Mould, Is_Planned_Mould, Updated_Mould FROM dbo.Machine_Live_State_Mould")):
                    rows[(r[0] or "").strip()] = {
                        "state": (r[1] or "").strip(), "code": (r[2] or "").strip(),
                        "stop_start": r[3].timestamp() if r[3] else None,
                        "shop_order": (r[4] or "").strip(), "part_number": (r[5] or "").strip(),
                        "shift": (r[6] or "").strip(), "planned": bool(r[7]),
                        "updated": r[8].timestamp() if r[8] else None}
        except Exception:
            logger.exception("Lecture de Machine_Live_State_Mould")
            rows = _live_state["rows"]  # garde la dernière lecture réussie
        _live_state.update(at=time.time(), rows=rows)
    row = _live_state["rows"].get(machine)
    if not row or not row["updated"] or time.time() - row["updated"] > LIVE_STATE_MAX_AGE:
        return None
    return row


def _stop_info(machine):
    """Cause de l'arrêt affichée : celle de la table d'état en direct si elle existe, sinon la dernière enregistrée."""
    live = _live_state_row(machine)
    if live and live["code"]:
        at = datetime.fromtimestamp(live["stop_start"]).strftime("%Y-%m-%d %H:%M:%S") if live["stop_start"] else None
        return {"code": live["code"], "at": at, "since": live["stop_start"], "planned": live["planned"], "live": True}
    return _last_stop_cause(machine)


def _last_stop_cause(machine):
    """Dernière cause d'arrêt enregistrée dans Machine_Stop_Table_Mould : {"code", "at"} ou None.
    Repli quand la machine n'a pas de ligne dans la table d'état en direct : la cause n'arrive alors en base qu'une fois
    l'arrêt synchronisé (dates en texte jj/mm/aaaa, d'où TRY_CONVERT style 103 pour trier chronologiquement)."""
    hit = _stop_cause.get(machine)
    if hit and time.time() - hit[0] < STOP_CAUSE_TTL:
        return hit[1]
    value = None
    if data_source.SQL_CONN:
        try:
            with db.get_engine(data_source.SQL_CONN).connect() as conn:
                row = conn.execute(text(
                    "SELECT TOP 1 Code_Stop_Mould, TRY_CONVERT(datetime, Date_Insert_Mould, 103) "
                    "FROM dbo.Machine_Stop_Table_Mould WHERE Machine_Name_Mould = :m "
                    "ORDER BY TRY_CONVERT(datetime, Date_Insert_Mould, 103) DESC"), {"m": machine}).fetchone()
            if row:
                value = {"code": (row[0] or "").strip(), "at": row[1].strftime("%Y-%m-%d %H:%M:%S") if row[1] else None}
        except Exception:
            logger.exception("Lecture de la cause d'arrêt (%s)", machine)
    _stop_cause[machine] = (time.time(), value)
    return value


_fleet_cache = {"at": 0.0, "data": None}


@bp.route("/api/live/fleet")
def api_live_fleet():
    """Une ligne par machine : de quoi afficher la vue d'ensemble sans transférer l'historique."""
    start_sampler()
    with _lock:
        hit = _fleet_cache["data"] if time.time() - _fleet_cache["at"] < FLEET_TTL else None
    if hit is not None:
        return jsonify(hit)
    rows = []
    for mc in _machines.values():
        if mc.maintenance:
            rows.append({
                "machine": mc.name, "online": False, "maintenance": True,
                "error_code": None, "error_detail": None, "state": "maintenance",
                "state_since": None, "since_partial": False, "stop_cause": None, "shift": None,
                "off_since": None, "shop_order": None, "part_number": None,
                "quantity": None, "produced": None, "of_active": False,
                "trs": None, "perf_live_pct": None,
                "alerts": [], "alert_list": [], "good": None, "rejects": None,
            })
            continue
        d = _snapshot(mc)
        s, m = d.get("status") or {}, d["metrics"]
        rows.append({
            "stop_cause": _stop_info(mc.name) if d["online"] and m["state"] == "stop" else None,
            "shift": (_live_state_row(mc.name) or {}).get("shift"),
            # durée hors planning mesurée par le terminal (secondes) : indépendante de l'horloge du Pi
            "off_since": (time.time() - float(s["out_of_plan_s"])) if m["state"] == "offplan" and s.get("out_of_plan_s") is not None else None,
            "machine": mc.name, "online": d["online"], "error_code": d["error_code"], "error_detail": d["error_detail"],
            "state": m["state"] if d["online"] else "offline", "state_since": m["state_since"],
            "since_partial": m["since_partial"], "shop_order": s.get("shop_order"), "part_number": s.get("part_number"),
            "quantity": s.get("quantity"), "produced": s.get("produced"), "of_active": bool(s.get("of_active")),
            "trs": s.get("trs_global") if s.get("of_active") else None, "perf_live_pct": m["perf_live_pct"],
            "cadence_pcs_h": m["cadence_pcs_h"], "cadence_th_pcs_h": m["cadence_th_pcs_h"],
            "alerts": [a["level"] for a in d["alerts"] if a["level"] != "info"],
            "alert_list": [a for a in d["alerts"] if a["level"] != "info"],
            "good": s.get("good") if d["online"] else None, "rejects": s.get("rejects") if d["online"] else None,
        })
    out = {"server_time": time.time(), "machines": rows}
    with _lock:
        _fleet_cache.update(at=time.time(), data=out)
    return jsonify(out)
