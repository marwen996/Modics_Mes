"""
Analyse IA des données MODICS avec Claude (API Anthropic).

Les chiffres (tendance, prévision de référence, Pareto…) sont calculés ici avec pandas ;
Claude les interprète et produit alertes, prévisions commentées et actions.

Variables d'environnement :
  ANTHROPIC_API_KEY  : clé API Anthropic (obligatoire ; sans elle les routes répondent 503)
  MODICS_AI_MODEL    : modèle (défaut claude-opus-5-5)
  MODICS_AI_EFFORT   : low | medium | high | xhigh | max (défaut medium)
  MODICS_AI_CACHE    : durée de réutilisation d'une analyse, en secondes (défaut 900)

Routes : POST /api/ai/insights  {machine, shift, start, end, force}
         POST /api/ai/ask       {question, machine, shift, start, end}
"""
import json
import os
import threading
import time

import anthropic
import numpy as np
import pandas as pd
from flask import Blueprint, current_app, jsonify, request

MODEL = os.environ.get("MODICS_AI_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("MODICS_AI_EFFORT", "medium")
CACHE_SECONDS = int(os.environ.get("MODICS_AI_CACHE", "900"))
# Bêta « fallbacks: default » : si les filtres de sécurité refusent la requête par erreur,
# l'API la rejoue sur le modèle de repli recommandé au lieu de renvoyer un refus.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_QUESTION = 1000

SYSTEM = """Tu es ingénieur méthodes / amélioration continue dans un atelier de moulage par injection \
(presses Arburg). Tu analyses les données MODICS d'une ou plusieurs presses : TRS (OEE) par équipe \
et journal des arrêts.

Règles :
- Réponds en français (ou en anglais si la demande le précise), de façon concrète et chiffrée, \
pour un responsable de production. Les champs à valeurs imposées (gravité, direction, confiance) \
gardent leurs valeurs françaises.
- Appuie-toi uniquement sur les données fournies ; cite les chiffres qui justifient chaque point.
- Les prévisions doivent partir de la « prévision de référence » calculée ; tu peux l'ajuster en \
expliquant pourquoi. Avec peu de jours de données, dis que la confiance est faible.
- Journée de production : Shift A → Shift B → Shift C (nuit, rattachée au jour J-1).
- TRS = Disponibilité × Performance × Qualité. Les arrêts « Arrêt non declaré » et les codes vides \
sont des arrêts sans cause saisie : signale-les s'ils pèsent lourd.
- Ne propose pas d'actions génériques : chaque action doit viser un code d'arrêt, une équipe, \
une référence ou un créneau précis des données."""

INSIGHTS_REQUEST = """Analyse ces données et produis :
- un résumé de la situation (3 à 5 phrases) ;
- la tendance du TRS ;
- les alertes (anomalies, dérives, pertes principales) ;
- des prévisions pour les prochains jours (TRS, arrêts, risques) ;
- les actions prioritaires."""

_GRAVITE = {"type": "string", "enum": ["haute", "moyenne", "basse"]}
INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "resume": {"type": "string"},
        "tendance_trs": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["hausse", "baisse", "stable", "indéterminée"]},
                "commentaire": {"type": "string"},
            },
            "required": ["direction", "commentaire"],
            "additionalProperties": False,
        },
        "alertes": {"type": "array", "items": {
            "type": "object",
            "properties": {"titre": {"type": "string"}, "detail": {"type": "string"}, "gravite": _GRAVITE},
            "required": ["titre", "detail", "gravite"],
            "additionalProperties": False,
        }},
        "predictions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "sujet": {"type": "string"},
                "prevision": {"type": "string"},
                "horizon": {"type": "string"},
                "confiance": {"type": "string", "enum": ["faible", "moyenne", "élevée"]},
                "justification": {"type": "string"},
            },
            "required": ["sujet", "prevision", "horizon", "confiance", "justification"],
            "additionalProperties": False,
        }},
        "actions": {"type": "array", "items": {
            "type": "object",
            "properties": {"action": {"type": "string"}, "impact_attendu": {"type": "string"}, "priorite": _GRAVITE},
            "required": ["action", "impact_attendu", "priorite"],
            "additionalProperties": False,
        }},
    },
    "required": ["resume", "tendance_trs", "alertes", "predictions", "actions"],
    "additionalProperties": False,
}

_client = None
_lock = threading.Lock()
_cache = {}  # clé des filtres → (horodatage, analyse)


class AIError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _get_client():
    global _client
    if _client is None:
        # Le proxy IIS (ARR) coupe à 120 s : une tentative de 100 s max, sans relance automatique
        _client = anthropic.Anthropic(timeout=100.0, max_retries=0)
    return _client


# ---------- Contexte chiffré envoyé à Claude ----------

def _pct(v):
    return None if pd.isna(v) else round(float(v) * 100, 1)


def _forecast(daily: pd.DataFrame):
    """Prévision de référence : TRS journalier (moyenne des équipes en production) et
    nombre d'arrêts, moyenne 7 j + régression linéaire sur les 14 derniers jours."""
    prod = daily[daily["run_min"] > 0]
    per_day = prod.groupby("day")["oee"].mean().sort_index()
    out = {"jours_avec_production": int(len(per_day))}
    if len(per_day) < 3:
        out["note"] = "Moins de 3 jours de production : pas de prévision statistique fiable."
        return out
    last = per_day.tail(14)
    x = np.arange(len(last))
    slope, intercept = np.polyfit(x, last.values, 1)
    nxt = [min(max(intercept + slope * (len(last) + i), 0), 1) for i in range(7)]
    out.update({
        "trs_moyen_7_derniers_jours_pct": _pct(per_day.tail(7).mean()),
        "ecart_type_7j_pct": _pct(per_day.tail(7).std()),
        "pente_trs_points_par_jour": round(float(slope) * 100, 2),
        "trs_prevu_j+1_pct": _pct(nxt[0]),
        "trs_prevu_j+7_pct": _pct(nxt[-1]),
        "methode": "régression linéaire sur les 14 derniers jours de production, bornée à [0, 100] %",
    })
    return out


def build_context(stops: pd.DataFrame, daily: pd.DataFrame, f: dict) -> str:
    machines = ", ".join(sorted(daily["machine"].unique())) or "—"
    parts = [
        f"# Données MODICS — machine(s) : {machines}",
        f"Filtres : équipe = {f.get('shift') or 'toutes'}, du {f.get('start') or 'début'} au {f.get('end') or 'fin'}.",
    ]
    if daily.empty:
        parts.append("Aucun enregistrement de production pour ces filtres.")
        return "\n".join(parts)

    prod = daily[daily["run_min"] > 0]
    kpis = {
        "trs_moyen_pct": _pct(prod["oee"].mean()), "disponibilite_pct": _pct(prod["availability"].mean()),
        "performance_pct": _pct(prod["performance"].mean()), "qualite_pct": _pct(prod["quality"].mean()),
        "pieces_bonnes": int(daily["good_qty"].sum()), "rebuts": int(daily["reject_qty"].sum()),
        "marche_min": round(float(daily["run_min"].sum())), "arret_min": round(float(daily["down_min"].sum())),
        "nb_arrets": int(len(stops)), "minutes_arrets": round(float(stops["duration_min"].sum()), 1),
        "arrets_horodatage_incoherent": int(stops["duration_min"].isna().sum()),
    }
    parts += ["## Indicateurs globaux", json.dumps(kpis, ensure_ascii=False),
              "## Prévision de référence (calculée)", json.dumps(_forecast(daily), ensure_ascii=False)]

    cols = ["day", "shift", "part_no", "run_min", "down_min", "good_qty", "reject_qty", "cycle_time",
            "availability", "performance", "quality", "oee"]
    parts += ["## Production par équipe (CSV, taux en fraction 0-1)",
              daily.sort_values(["day", "date"])[cols].to_csv(index=False, float_format="%.3f", date_format="%Y-%m-%d")]

    by_shift = prod.groupby("shift").agg(trs=("oee", "mean"), dispo=("availability", "mean"),
                                         perf=("performance", "mean"), qual=("quality", "mean"),
                                         rebuts=("reject_qty", "sum"), postes=("oee", "size")).round(3)
    parts += ["## Moyennes par équipe (CSV)", by_shift.to_csv()]

    if not stops.empty:
        s = stops.assign(code=stops["code"].fillna("(vide)"), heure=stops["start"].dt.hour)
        agg = dict(nb=("code", "size"), minutes=("duration_min", "sum"), duree_moy=("duration_min", "mean"))
        by_code = s.groupby("code").agg(**agg).sort_values("minutes", ascending=False).round(1)
        by_code_shift = s.groupby(["code", "shift"]).agg(nb=("code", "size"), minutes=("duration_min", "sum")).round(1)
        by_day = s.groupby("day").agg(nb=("code", "size"), minutes=("duration_min", "sum")).round(1)
        by_hour = s.groupby("heure").agg(nb=("code", "size"), minutes=("duration_min", "sum")).round(1)
        by_part = s.groupby("part_no").agg(nb=("code", "size"), minutes=("duration_min", "sum")).round(1)
        by_regleur = s[s["regleur"] != ""].groupby("regleur").agg(nb=("code", "size"), minutes=("duration_min", "sum")).round(1)
        parts += [
            "## Arrêts par code (Pareto, CSV)", by_code.to_csv(),
            "## Arrêts par code et équipe (CSV)", by_code_shift.to_csv(),
            "## Arrêts par jour de production (CSV)", by_day.to_csv(date_format="%Y-%m-%d"),
            "## Arrêts par heure de début (CSV)", by_hour.to_csv(),
            "## Arrêts par référence pièce (CSV)", by_part.to_csv(),
            "## Arrêts par régleur (CSV)", by_regleur.to_csv(),
            "## 60 derniers arrêts (CSV)",
            s.sort_values("start").tail(60)[["start", "end", "duration_min", "code", "shift", "part_no", "regleur"]]
             .to_csv(index=False, date_format="%Y-%m-%d %H:%M"),
        ]
    return "\n".join(parts)


# ---------- Appel à Claude ----------

def _call(context: str, user_content: str, output_format=None, max_tokens=8000):
    params = dict(
        model=MODEL,
        max_tokens=max_tokens,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        # Contexte en bloc système mis en cache : les questions suivantes sur les mêmes données le relisent à ~10 % du prix
        system=[{"type": "text", "text": SYSTEM},
                {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
        output_config={"effort": EFFORT, **({"format": output_format} if output_format else {})},
    )
    try:
        resp = _get_client().beta.messages.create(**params)
    except anthropic.AuthenticationError:
        raise AIError("Clé API Anthropic invalide", 503)
    except anthropic.PermissionDeniedError:
        raise AIError("La clé API n'a pas accès à ce modèle", 503)
    except anthropic.RateLimitError:
        raise AIError("Limite de requêtes Claude atteinte, réessayez dans une minute", 429)
    except anthropic.APIStatusError as e:
        raise AIError(f"Erreur API Claude ({e.status_code}) : {e.message}")
    except anthropic.APITimeoutError:
        raise AIError("Claude a mis trop de temps à répondre, réessayez", 504)
    except anthropic.APIConnectionError:
        raise AIError("Impossible de joindre l'API Claude (réseau / proxy ?)")

    u = resp.usage
    current_app.logger.info("Claude %s : %s in, %s cache lu, %s cache écrit, %s out", resp.model,
                            u.input_tokens, u.cache_read_input_tokens, u.cache_creation_input_tokens, u.output_tokens)
    if resp.stop_reason == "refusal":
        raise AIError("Claude a refusé cette demande")
    if resp.stop_reason == "max_tokens":
        raise AIError("Réponse de Claude tronquée (limite de longueur atteinte)")
    return next((b.text for b in resp.content if b.type == "text"), "")


def _filters(body):
    f = {k: (body.get(k) or None) for k in ("machine", "shift", "start", "end")}
    f["lang"] = "en" if body.get("lang") == "en" else "fr"
    return f


def _in_lang(user_content, f):
    return user_content + ("\n\nWrite all free-text fields in English." if f["lang"] == "en" else "")


def make_blueprint(get_data, apply_filters):
    """get_data() → (stops, daily) ; apply_filters(df, filtres) → df filtré."""
    bp = Blueprint("ai_insights", __name__, url_prefix="/api/ai")

    def _context(f):
        stops, daily = get_data()
        return build_context(apply_filters(stops, f), apply_filters(daily, f), f)

    @bp.before_request
    def _check_key():
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return jsonify({"error": "ANTHROPIC_API_KEY non configurée sur le serveur"}), 503

    @bp.errorhandler(AIError)
    def _ai_error(e):
        return jsonify({"error": str(e)}), e.status

    @bp.route("/insights", methods=["POST"])
    def insights():
        body = request.get_json(silent=True) or {}
        f = _filters(body)
        key = json.dumps(f, sort_keys=True)
        # Verrou : un double clic ne déclenche (et ne facture) qu'une seule analyse
        with _lock:
            hit = _cache.get(key)
            if hit and not body.get("force") and time.time() - hit[0] < CACHE_SECONDS:
                return jsonify({**hit[1], "cached": True})
            text = _call(_context(f), _in_lang(INSIGHTS_REQUEST, f),
                         output_format={"type": "json_schema", "schema": INSIGHTS_SCHEMA})
            try:
                result = {"analysis": json.loads(text), "model": MODEL,
                          "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            except json.JSONDecodeError:
                raise AIError("Réponse de Claude illisible")
            _cache[key] = (time.time(), result)
        return jsonify({**result, "cached": False})

    @bp.route("/ask", methods=["POST"])
    def ask():
        body = request.get_json(silent=True) or {}
        question = str(body.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Question vide"}), 400
        if len(question) > MAX_QUESTION:
            return jsonify({"error": f"Question trop longue (max {MAX_QUESTION} caractères)"}), 400
        f = _filters(body)
        answer = _call(_context(f),
                       _in_lang(question + "\n\nRéponds en texte simple (pas de tableau Markdown), en 15 lignes maximum.", f),
                       max_tokens=4000)
        return jsonify({"answer": answer, "model": MODEL})

    return bp
