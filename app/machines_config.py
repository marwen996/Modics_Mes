"""
Configuration des presses : app/machines.json (ou MODICS_MACHINES_FILE).

Précédence pour chaque machine : variable d'environnement (MODICS_PI_URL_<NN>, MODICS_PI_KEY_<NN>)
> machines.json > défaut (clé MODICS_PI_KEY, IP lue en base). MODICS_MACHINES (liste séparée par
des virgules) remplace la liste des noms si elle est définie.
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)
PATH = os.environ.get("MODICS_MACHINES_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "machines.json")


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception("machines.json illisible (%s)", PATH)
        return {}


_cfg = _load()
_by_name = {m["name"].strip(): m for m in _cfg.get("machines", []) if m.get("name")}


def names():
    env = os.environ.get("MODICS_MACHINES")
    if env is not None:
        return [m.strip() for m in env.split(",") if m.strip()]
    return list(_by_name)


def port():
    return int(os.environ.get("MODICS_PI_PORT") or _cfg.get("port") or 8080)


def machine(name):
    """(num, url, key) d'une presse ; url/key peuvent être None."""
    num = re.sub(r"\D", "", name)
    j = _by_name.get(name, {})
    url = (os.environ.get(f"MODICS_PI_URL_{num}") or j.get("url") or "").rstrip("/") or None
    key = os.environ.get(f"MODICS_PI_KEY_{num}") or j.get("key") or os.environ.get("MODICS_PI_KEY") or _cfg.get("default_key")
    return num, url, key


def is_maintenance(name):
    """True si la presse est marquée en maintenance dans machines.json."""
    return bool(_by_name.get(name, {}).get("maintenance"))
