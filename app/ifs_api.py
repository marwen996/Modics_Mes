"""
API de réception IFS → MODICS.

IFS pousse ses ordres de fabrication (shop orders) par POST ; on les stocke dans la table
`IFS_Shop_Orders` (créée automatiquement). Une ligne par (shop_order, component, tool_group) :
un OF avec plusieurs composants ou groupes d'outils est envoyé en plusieurs lignes.

Variables d'environnement :
  IFS_API_KEY  : clé partagée avec IFS, envoyée dans l'en-tête `X-API-Key` (obligatoire)
  IFS_DB_CONN  : base de stockage ; par défaut MODICS_SQL_CONN, sinon SQLite data/ifs_inbox.db
"""
import hmac
import os
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String, Table,
                        UniqueConstraint, and_, select)

import db

bp = Blueprint("ifs_api", __name__, url_prefix="/api/ifs")

MAX_BATCH = 1000
_metadata = MetaData()
shop_orders = Table(
    "IFS_Shop_Orders", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("production_line", String(50)),
    Column("part_no", String(50), nullable=False),
    Column("shop_order", String(30), nullable=False),
    Column("tool_group", String(50), nullable=False),
    Column("component", String(50), nullable=False),
    Column("lot_size", Float, nullable=False),
    Column("tool_quantity", Float),
    Column("received_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("shop_order", "component", "tool_group", name="uq_ifs_shop_order"),
)
FIELDS = [c.name for c in shop_orders.columns if c.name not in ("id", "received_at", "updated_at")]
KEY = ("shop_order", "component", "tool_group")
REQUIRED = ("shop_order", "part_no", "lot_size")
TEXT = ("production_line", "part_no", "shop_order", "tool_group", "component")


def _canon(name) -> str:
    """'Production Line', 'PRODUCTION_LINE', 'ProductionLine' → 'productionline'."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


# Accepte snake_case, libellés ("Shop Order"), IFS PL/SQL (ORDER_NO) et IFS Cloud OData (OrderNo)
_ALIASES = {_canon(f): f for f in FIELDS}
_ALIASES.update({
    "partnumber": "part_no", "shoporderno": "shop_order", "orderno": "shop_order",
    "line": "production_line", "productionlineid": "production_line",
    "toolgroupid": "tool_group", "toolid": "tool_group",
    "componentpartno": "component", "componentpart": "component", "compoment": "component",
    "lotsize": "lot_size", "revisedqtydue": "lot_size", "qty": "lot_size",
    "toolqty": "tool_quantity",
})

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        conn = os.environ.get("IFS_DB_CONN") or os.environ.get("MODICS_SQL_CONN")
        if not conn:
            os.makedirs("data", exist_ok=True)
            conn = "sqlite:///" + os.path.join("data", "ifs_inbox.db")
        _engine = db.get_engine(conn)
        _metadata.create_all(_engine)
    return _engine


@bp.before_request
def _check_api_key():
    expected = os.environ.get("IFS_API_KEY")
    if not expected:
        return jsonify({"error": "IFS_API_KEY non configurée sur le serveur"}), 503
    if not hmac.compare_digest(request.headers.get("X-API-Key", ""), expected):
        return jsonify({"error": "Clé API invalide"}), 401


def _normalize(item: dict):
    """Renvoie (ligne, erreurs) pour une ligne reçue."""
    row, errors = {}, []
    for k, v in item.items():
        field = _ALIASES.get(_canon(k))
        if field:
            row[field] = v.strip() if isinstance(v, str) else v
    for f in REQUIRED:
        if row.get(f) in (None, ""):
            errors.append(f"{f} manquant")
    for f in TEXT:
        if row.get(f) is not None:
            row[f] = str(int(row[f])) if isinstance(row[f], float) and row[f].is_integer() else str(row[f])
    row["component"] = row.get("component") or ""
    row["tool_group"] = row.get("tool_group") or ""
    for f, minimum in (("lot_size", "> 0"), ("tool_quantity", ">= 0")):
        if row.get(f) in (None, ""):
            if f in row:
                row[f] = None
            continue
        try:
            row[f] = float(row[f])
        except (TypeError, ValueError):
            errors.append(f"{f} n'est pas un nombre")
            continue
        if (row[f] <= 0) if minimum == "> 0" else (row[f] < 0):
            errors.append(f"{f} doit être {minimum}")
    return row, errors


@bp.route("/shop-orders", methods=["POST"])
def post_shop_orders():
    body = request.get_json(silent=True)
    if isinstance(body, dict) and isinstance(body.get("items"), list):
        items = body["items"]
    elif isinstance(body, dict):
        items = [body]
    elif isinstance(body, list):
        items = body
    else:
        return jsonify({"error": "Corps JSON attendu (objet, liste, ou {\"items\": [...]})"}), 400
    if not items:
        return jsonify({"error": "Aucune ligne reçue"}), 400
    if len(items) > MAX_BATCH:
        return jsonify({"error": f"Maximum {MAX_BATCH} lignes par appel"}), 413

    rows, errors = [], []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"index": i, "errors": ["objet JSON attendu"]})
            continue
        row, errs = _normalize(item)
        if errs:
            errors.append({"index": i, "shop_order": row.get("shop_order"), "errors": errs})
        rows.append(row)
    if errors:  # lot rejeté en entier : IFS renvoie après correction
        return jsonify({"error": "Validation échouée, rien n'a été enregistré", "details": errors}), 400

    now = datetime.now()
    inserted = updated = 0
    with _get_engine().begin() as conn:
        for row in rows:
            where = and_(*(shop_orders.c[k] == row[k] for k in KEY))
            exists = conn.execute(select(shop_orders.c.id).where(where)).first()
            if exists:
                conn.execute(shop_orders.update().where(where).values(**row, updated_at=now))
                updated += 1
            else:
                conn.execute(shop_orders.insert().values(**row, received_at=now, updated_at=now))
                inserted += 1
    return jsonify({"received": len(rows), "inserted": inserted, "updated": updated}), 200


@bp.route("/shop-orders", methods=["GET"])
def get_shop_orders():
    q = select(shop_orders).order_by(shop_orders.c.updated_at.desc())
    for f in TEXT:
        if request.args.get(f):
            q = q.where(shop_orders.c[f] == request.args[f])
    q = q.limit(min(int(request.args.get("limit", 500)), 5000))
    with _get_engine().connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(q)]
    for r in rows:
        for k, v in r.items():
            if isinstance(v, datetime):
                r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(rows)
