import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request
import pandas as pd
import ai_insights
import data_source
import ifs_api
import machines_config
import pi_live
import public_gate

app = Flask(__name__)
public_gate.install(app)  # mot de passe pour l'accès venant d'Internet (tunnel) ; le réseau interne reste libre
app.register_blueprint(ifs_api.bp)
app.register_blueprint(pi_live.bp)
pi_live.start_sampler()  # historique live (24 h) collecté même sans écran ouvert

# Les tables sont relues au plus toutes les REFRESH_SECONDS (MODICS_REFRESH, défaut 30 s)
REFRESH_SECONDS = int(os.environ.get("MODICS_REFRESH", "30"))
_lock = threading.Lock()
_cache = {"stops": None, "daily": None, "loaded_at": 0.0, "updated_at": None, "error": None}


def _refresh(force=False):
    with _lock:
        if not force and _cache["daily"] is not None and time.time() - _cache["loaded_at"] < REFRESH_SECONDS:
            return
        try:
            _cache["stops"], _cache["daily"] = data_source.load()
            _cache["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _cache["error"] = None
        except Exception as e:  # base injoignable : on garde les dernières données
            if _cache["daily"] is None:
                raise
            _cache["error"] = str(e)
            app.logger.warning("Rechargement MODICS échoué : %s", e)
        _cache["loaded_at"] = time.time()


def get_data():
    _refresh()
    return _cache["stops"], _cache["daily"]


def _meta(daily):
    return {
        "updated_at": _cache["updated_at"],
        "error": _cache["error"],
        "refresh_seconds": REFRESH_SECONDS,
        "machines": sorted(daily["machine"].unique()),
        "min_date": daily["day"].min().strftime("%Y-%m-%d"),
        "max_date": daily["day"].max().strftime("%Y-%m-%d"),
    }


_refresh()


def _filters():
    return {
        "machine": request.args.get("machine") or None,
        "shift": request.args.get("shift") or None,
        "start": request.args.get("start") or None,
        "end": request.args.get("end") or None,
    }


def _apply(df: pd.DataFrame, f, date_col="day"):
    if f["machine"]:
        df = df[df["machine"] == f["machine"]]
    if f["shift"]:
        df = df[df["shift"] == f["shift"]]
    if f["start"]:
        df = df[df[date_col] >= pd.Timestamp(f["start"])]
    if f["end"]:
        df = df[df[date_col] <= pd.Timestamp(f["end"])]
    return df


app.register_blueprint(ai_insights.make_blueprint(get_data, _apply))


def _records(df: pd.DataFrame):
    out = df.copy()
    for c in out.select_dtypes(include=["datetime"]).columns:
        out[c] = out[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    # En object : sur une colonne float, where(..., None) remettrait NaN (JSON invalide pour le navigateur)
    return out.astype(object).where(pd.notna(out), None).to_dict(orient="records")


@app.route("/")
def index():
    """Accueil « Atelier » : l'état de l'atelier en langage simple, centré sur les personnes."""
    return render_template("atelier.html", active="atelier", machines=list(pi_live._machines))


@app.route("/fleet")
def fleet():
    """Vue globale du parc : bureau (grille défilante) et TV (?tv=1 : tout le parc sur un écran)."""
    return render_template("fleet.html", active="fleet", machines=list(pi_live._machines))


@app.route("/analyse")
def analysis():
    _, daily = get_data()
    return render_template(
        "index.html",
        machines=sorted(daily["machine"].unique()),
        shifts=sorted(daily["shift"].dropna().unique()),
        min_date=daily["day"].min().strftime("%Y-%m-%d"),
        max_date=daily["day"].max().strftime("%Y-%m-%d"),
        # Panneau Claude masqué tant qu'aucune clé API n'est configurée
        ai_enabled=bool(os.environ.get("ANTHROPIC_API_KEY")),
        active="dashboard",
    )


def _kpis(d: pd.DataFrame, s: pd.DataFrame):
    producing = d[d["run_min"] > 0]
    pct = lambda col: round(float(producing[col].mean()) * 100, 1) if len(producing) else 0
    return {
        "oee": pct("oee"), "availability": pct("availability"),
        "performance": pct("performance"), "quality": pct("quality"),
        "good_qty": int(d["good_qty"].sum()), "reject_qty": int(d["reject_qty"].sum()),
        "run_min": round(float(d["run_min"].sum()), 1), "down_min": round(float(d["down_min"].sum()), 1),
        "stops_count": int(len(s)), "stops_min": round(float(s["duration_min"].sum()), 1),
        "shifts_count": int(len(d)),
    }


def _compare(daily, stops, f):
    """KPIs de la période précédente de même longueur (pour les variations) ; None sans bornes ou sans données."""
    if not (f["start"] and f["end"]):
        return None
    start, end = pd.Timestamp(f["start"]), pd.Timestamp(f["end"])
    length = end - start + pd.Timedelta(days=1)
    prev = {**f, "start": (start - length).strftime("%Y-%m-%d"), "end": (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d")}
    k = _kpis(_apply(daily, prev), _apply(stops, prev))
    return k if k["shifts_count"] else None


def _per_day(d: pd.DataFrame, s: pd.DataFrame):
    """Série journalière pour les sparklines des KPI."""
    per_day = (d.groupby("day").agg(good_qty=("good_qty", "sum"), reject_qty=("reject_qty", "sum"),
                                    run_min=("run_min", "sum"), down_min=("down_min", "sum")).reset_index())
    oee_day = d[d["run_min"] > 0].groupby("day")["oee"].mean() * 100
    per_day["oee"] = per_day["day"].map(oee_day).round(1)
    stops_day = s.groupby("day").agg(stops_count=("code", "size"), stops_min=("duration_min", "sum"))
    per_day = per_day.merge(stops_day, left_on="day", right_index=True, how="left")
    per_day[["stops_count", "stops_min"]] = per_day[["stops_count", "stops_min"]].fillna(0)
    per_day["stops_count"] = per_day["stops_count"].astype(int)
    num_cols = per_day.columns.drop("day")
    per_day[num_cols] = per_day[num_cols].round(1)
    return _records(per_day.sort_values("day"))


@app.route("/api/summary")
def api_summary():
    stops, daily = get_data()
    f = _filters()
    d = _apply(daily, f)
    s = _apply(stops, f)
    kpis = _kpis(d, s)

    # OEE trend per shift record (chronological, grouped by production day: Shift C → day - 1)
    trend = d.sort_values(["day", "date"])[["day", "date", "machine", "shift", "oee", "availability",
                                   "performance", "quality", "good_qty", "reject_qty", "run_min", "down_min"]]

    # Stops by code (Pareto)
    by_code = (s.groupby("code")
                .agg(count=("code", "size"), minutes=("duration_min", "sum"))
                .sort_values("minutes", ascending=False)
                .reset_index())
    by_code["minutes"] = by_code["minutes"].round(1)

    # Downtime per machine
    by_machine = (d.groupby("machine")
                   .agg(run_min=("run_min", "sum"), down_min=("down_min", "sum"),
                        good_qty=("good_qty", "sum"))
                   .round(1).reset_index())

    # Stops per day
    per_day = (s.groupby("day").agg(count=("code", "size"), minutes=("duration_min", "sum"))
                .round(1).reset_index())

    return jsonify({
        "meta": _meta(daily),
        "kpis": kpis,
        "compare": _compare(daily, stops, f),
        "per_day": _per_day(d, s),
        "trend": _records(trend),
        "by_code": by_code.to_dict(orient="records"),
        "by_machine": by_machine.to_dict(orient="records"),
        "stops_per_day": _records(per_day),
    })


def _oee_block(d: pd.DataFrame):
    k = _kpis(d, d.iloc[0:0].assign(duration_min=0, code=""))
    return {"oee": k["oee"] if k["shifts_count"] and (d["run_min"] > 0).any() else None,
            "availability": k["availability"], "performance": k["performance"], "quality": k["quality"],
            "good_qty": k["good_qty"], "reject_qty": k["reject_qty"], "shifts_count": k["shifts_count"]}


@app.route("/api/live/oee")
def api_live_oee():
    """OEE du jour de production (06:00 → 06:00), des dernières 24 h glissantes et de la semaine (lundi → aujourd'hui).
    ?machine= : une presse ; sans paramètre, toutes les machines."""
    _, daily = get_data()
    if request.args.get("machine"):
        daily = daily[daily["machine"] == request.args["machine"]]
    return jsonify({**_oee_periods(daily), "updated_at": _cache["updated_at"]})


@app.route("/api/live/oee/all")
def api_live_oee_all():
    """Mêmes périodes que /api/live/oee, une entrée par machine (vue d'ensemble / mode TV)."""
    _, daily = get_data()
    return jsonify({"machines": {m: _oee_periods(g) for m, g in daily.groupby("machine")},
                    "updated_at": _cache["updated_at"]})


def _oee_periods(daily: pd.DataFrame):
    now = datetime.now()
    today = pd.Timestamp(now.replace(hour=0, minute=0, second=0, microsecond=0))
    if now.hour < 6:  # avant 06:00 on est encore dans la journée de production de la veille
        today -= pd.Timedelta(days=1)
    week_start = today - pd.Timedelta(days=today.weekday())
    return {
        "today": _oee_block(daily[daily["day"] == today]),
        "last24h": _oee_block(daily[daily["date"] >= pd.Timestamp(now) - pd.Timedelta(hours=24)]),
        "wtd": _oee_block(daily[(daily["day"] >= week_start) & (daily["day"] <= today)]),
        "day": today.strftime("%Y-%m-%d"), "week_start": week_start.strftime("%Y-%m-%d"),
    }


@app.route("/api/stops")
def api_stops():
    stops, _ = get_data()
    s = _apply(stops, _filters()).sort_values("start", ascending=False)
    return jsonify(_records(s[["machine", "day", "shift", "code", "part_no",
                               "start", "end", "duration_min", "regleur"]]))


@app.route("/api/daily")
def api_daily():
    _, daily = get_data()
    d = _apply(daily, _filters()).sort_values(["day", "date"], ascending=False)
    return jsonify(_records(d))


@app.route("/api/reload", methods=["POST"])
def api_reload():
    _refresh(force=True)
    stops, daily = _cache["stops"], _cache["daily"]
    return jsonify({"stops": len(stops), "daily": len(daily),
                    "updated_at": _cache["updated_at"], "error": _cache["error"]})


@app.route("/mobile")
def mobile():
    """App mobile PWA : contrôle des presses depuis un téléphone (interne ou via tunnel)."""
    return render_template("mobile.html")


@app.route("/proxy/<slug>/api/v1/<path:api_path>", methods=["GET", "POST"])
def proxy_pi(slug, api_path):
    """Relai transparent vers le terminal Pi d'une presse.

    Permet à l'app mobile de joindre les Pi depuis Internet (via tunnel Cloudflare)
    sans exposer les IPs internes ni les clés API dans le navigateur.

    slug = nom de la presse sans espaces ni majuscules : prs81, prs63, …
    """
    slug_clean = re.sub(r"[^a-z0-9]", "", slug.lower())
    machine_name = next(
        (n for n in machines_config.names()
         if re.sub(r"[^a-z0-9]", "", n.lower()) == slug_clean),
        None,
    )
    if not machine_name:
        return jsonify({"error": "Machine not found"}), 404
    _, url, key = machines_config.machine(machine_name)
    if not url:
        return jsonify({"error": "No URL configured for this machine"}), 503

    target = url.rstrip("/") + "/api/v1/" + api_path
    if request.query_string:
        target += "?" + request.query_string.decode("utf-8", errors="replace")

    # L'app mobile envoie sa propre clé ; à défaut on utilise celle de machines.json
    api_key = request.headers.get("X-Api-Key") or key or ""
    body = request.get_data() or None
    try:
        req = urllib.request.Request(
            target, data=body,
            headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
            method=request.method,
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return Response(resp.read(), status=resp.status,
                            content_type=resp.headers.get("Content-Type", "application/json"))
    except urllib.error.HTTPError as e:
        return Response(e.read(), status=e.code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": "Machine unreachable", "detail": str(e)}), 503


if __name__ == "__main__":
    app.run(debug=True, port=5000)
