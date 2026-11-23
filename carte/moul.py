# -*- coding: utf-8 -*-
"""
MODICS - Mold Operation Data Intelligent Collection System
Presse Arburg "PRS 63" - Raspberry Pi 4 + Automation HAT.
Le signal "noyau" de la presse arrive sur l'entrée 2 de l'Automation HAT.

version 0.6 - arrêts obligatoirement déclarés (plus d'« Arrêt non declaré »).
version 0.5 - nettoyage sécurité / fiabilité / lisibilité (voir CHANGELOG
en bas de fichier pour le détail des correctifs apportés).
"""
import configparser
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import smtplib
import socket
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from threading import Thread, Lock

import automationhat
import kivy
import mysql.connector
import pymssql

kivy.require('2.3.0')

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, Rotate, RoundedRectangle
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from collections import deque
from statistics import median

# ---------------------------------------------------------------------------
# Configuration : AUCUN identifiant en dur dans le code. Tout est lu depuis
# config_modics.ini (fichier fourni à côté de ce script, à côté de press.db).
# Si le fichier n'existe pas encore sur la machine, un gabarit est créé
# automatiquement au premier lancement -> à compléter avec les vrais
# mots de passe avant mise en service.
# ---------------------------------------------------------------------------
CONFIG_PATH = os.environ.get("MODICS_CONFIG", "/home/pi/Downloads/config_modics.ini")


def _write_default_config(path):
    parser = configparser.ConfigParser()
    parser["machine"] = {"name": "PRS 63"}
    parser["local_db"] = {"path": "/home/pi/Downloads/press.db"}
    parser["internal_db"] = {
        "host": "localhost",
        "database": "internal_machine_db",
        "user": "internal_user",
        "password": "CHANGE_ME",
    }
    parser["external_db"] = {
        "server": "192.168.80.216",
        "user": "sa",
        "password": "CHANGE_ME",
        "database": "MODICS",
    }
    parser["capteur"] = {
        "edge": "rising",           # front qui compte un cycle : rising (début d'impulsion ON) ou falling
        "poll_hz": "50",            # fréquence de lecture des entrées
        "stable_samples": "3",      # anti-rebond : lectures identiques consécutives requises
        "cycle_input": "2",         # entrée du signal noyau (cycle)
        "stop_input": "1",          # entrée du signal arrêt machine (0 = désactivé)
        "reject_input": "3",        # entrée du signal rebut (0 = désactivé)
        "stop_timeout_factor": "2.0",  # arrêt détecté si aucune impulsion pendant cycle_t x facteur
        "stop_timeout_min": "30",      # ... mais jamais moins de N secondes
        "stop_timeout_max": "300",     # ... ni plus de N secondes
    }
    parser["api"] = {
        "enabled": "true",
        "host": "0.0.0.0",
        "port": "8080",
        "api_key": "CHANGE_ME",     # obligatoire : l'API reste inactive tant que CHANGE_ME n'est pas remplacé
    }
    parser["email"] = {
        "sender": "modics2023@gmail.com",
        "app_password": "CHANGE_ME",
        "receivers_default": "mohamed.aliayari@bulgin.com,marwen.rahal@bulgin.com,marwenrahal80@gmail.com",
    }
    with open(path, "w", encoding="utf-8") as f:
        parser.write(f)


def _load_config(path):
    if not os.path.exists(path):
        _write_default_config(path)
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    return parser


SETTINGS = _load_config(CONFIG_PATH)

# ---------------------------------------------------------------------------
# Logging : remplace les print()/except: silencieux. Consultable a posteriori
# sur un poste kiosque qui n'a pas de console visible.
# ---------------------------------------------------------------------------
LOG_PATH = os.environ.get("MODICS_LOG", "/home/pi/Downloads/modics.log")
logger = logging.getLogger("MODICS")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _file_handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_file_handler)

##############################################################################
# Widgets "Industrie 4.0" dessinés au canvas (aucune bibliothèque externe).
# Purement visuels : ils ne font que représenter des valeurs déjà calculées.
##############################################################################
class OeeGauge(Widget):
    """Jauge demi-cercle à aiguille. value = 0..100 (%)."""
    value = NumericProperty(0)
    low_threshold = NumericProperty(50)    # sous ce % : zone rouge
    high_threshold = NumericProperty(75)   # au-dessus : zone verte

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, value=self._redraw)

    def _redraw(self, *args):
        self.canvas.clear()
        w, h = self.width, self.height
        if w <= 0 or h <= 0:
            return
        r = min(w / 2.0, h) * 0.82
        cx = self.center_x
        cy = self.y + h * 0.12
        lw = max(8.0, r * 0.15)
        a_low = -90 + 180 * (self.low_threshold / 100.0)
        a_high = -90 + 180 * (self.high_threshold / 100.0)
        v = max(0.0, min(100.0, float(self.value))) / 100.0
        with self.canvas:
            Color(0.82, 0.24, 0.24, 1)
            Line(circle=(cx, cy, r, -90, a_low), width=lw)
            Color(0.93, 0.63, 0.18, 1)
            Line(circle=(cx, cy, r, a_low, a_high), width=lw)
            Color(0.16, 0.60, 0.35, 1)
            Line(circle=(cx, cy, r, a_high, 90), width=lw)
            # aiguille : dessinée vers le haut puis tournée (Kivy tourne dans
            # le sens anti-horaire pour un angle positif)
            PushMatrix()
            Rotate(angle=90 - 180 * v, origin=(cx, cy))
            Color(0.05, 0.14, 0.24, 1)
            Line(points=[cx, cy, cx, cy + r * 0.88], width=3, cap='round')
            PopMatrix()
            Ellipse(pos=(cx - 8, cy - 8), size=(16, 16))


class CycleChart(Widget):
    """Courbe des derniers temps de cycle + ligne de cible en pointillés."""
    points = ListProperty([])
    target = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw,
                  points=self._redraw, target=self._redraw)

    def _redraw(self, *args):
        self.canvas.clear()
        pts = [float(p) for p in self.points]
        pad = 10
        x0, y0 = self.x + pad, self.y + pad
        W, H = self.width - 2 * pad, self.height - 2 * pad
        if W <= 0 or H <= 0:
            return
        with self.canvas:
            # grille légère
            Color(0.55, 0.58, 0.62, 0.30)
            for k in range(4):
                yy = y0 + H * k / 3.0
                Line(points=[x0, yy, x0 + W, yy], width=1)
        if len(pts) < 2:
            return
        vals = pts + ([float(self.target)] if self.target else [])
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        lo -= span * 0.2
        hi += span * 0.2
        span = hi - lo

        def sy(v):
            return y0 + (v - lo) / span * H

        n = len(pts)
        step = W / float(n - 1)
        with self.canvas:
            if self.target:
                Color(0.45, 0.45, 0.45, 1)
                ty = sy(float(self.target))
                Line(points=[x0, ty, x0 + W, ty], dash_length=6, dash_offset=4)
            Color(0.16, 0.47, 0.84, 1)
            coords = []
            for i, v in enumerate(pts):
                coords += [x0 + i * step, sy(v)]
            Line(points=coords, width=2)
            Ellipse(pos=(x0 + (n - 1) * step - 4, sy(pts[-1]) - 4), size=(8, 8))


class FormField(TextInput):
    """Champ de saisie stylé (fond arrondi, bordure orange quand actif). Saisie via clavier tactile."""
    locked = False       # valeur imposée (ex. outil / empreintes issus du fichier Machine Group)
    def __init__(self, **kw):
        kw.setdefault('multiline', False)
        kw.setdefault('readonly', True)
        kw.setdefault('cursor_blink', False)
        kw.setdefault('background_normal', '')
        kw.setdefault('background_active', '')
        kw.setdefault('background_color', (0, 0, 0, 0))
        kw.setdefault('foreground_color', (0.10, 0.10, 0.12, 1))
        kw.setdefault('padding', [12, 10, 12, 10])
        kw.setdefault('font_size', 21)
        super().__init__(**kw)
        with self.canvas.before:
            self._fill_c = Color(0.96, 0.97, 0.98, 1)
            self._fill = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
            self._border_c = Color(0.75, 0.78, 0.82, 1)
            self._border = Line(rounded_rectangle=(0, 0, 1, 1, 8), width=1.4)
        self.bind(pos=self._upd, size=self._upd, focus=self._upd)

    def _upd(self, *args):
        self._fill.pos, self._fill.size = self.pos, self.size
        self._border.rounded_rectangle = (self.x + 1, self.y + 1, self.width - 2, self.height - 2, 8)
        if self.focus:
            self._border_c.rgba = (0.95, 0.40, 0.13, 1)
            self._border.width = 2.4
            self._fill_c.rgba = (1, 0.97, 0.94, 1)
        else:
            self._border_c.rgba = (0.75, 0.78, 0.82, 1)
            self._border.width = 1.4
            self._fill_c.rgba = (0.86, 0.88, 0.90, 1) if self.locked else (0.96, 0.97, 0.98, 1)


##############################################################################
# Détection de cycle sur l'entrée 2 (signal noyau) - pur Python, testable.
#
#   OFF ____|‾‾ON‾‾|________|‾‾ON‾‾|____
#                  <------ CYCLE ------>   (front descendant -> front descendant)
#
# Anti-rebond par échantillons consécutifs : un changement d'état n'est validé
# qu'après `stable_samples` lectures identiques (3 x 20 ms = 60 ms à 50 Hz).
##############################################################################
class CycleDetector:
    def __init__(self, stable_samples=3):
        self.stable_samples = max(1, int(stable_samples))
        self.state = None          # dernier état validé (True = ON), None = inconnu
        self._cand = None
        self._cand_n = 0
        self.last_rise = None
        self.last_fall = None
        self.on_duration = 0.0     # durée de la dernière impulsion ON (s)
        self.off_duration = 0.0    # durée du dernier OFF (s)

    def feed(self, is_on, now):
        """Alimente une lecture. Retourne 'rising', 'falling' ou None."""
        if is_on == self.state:
            self._cand, self._cand_n = None, 0
            return None
        if self._cand != is_on:
            self._cand, self._cand_n = is_on, 1
        else:
            self._cand_n += 1
        if self._cand_n < self.stable_samples:
            return None
        first = self.state is None
        self.state, self._cand, self._cand_n = is_on, None, 0
        if is_on:
            if self.last_fall is not None:
                self.off_duration = now - self.last_fall
            self.last_rise = now
            return None if first else 'rising'
        else:
            if self.last_rise is not None:
                self.on_duration = now - self.last_rise
            self.last_fall = now
            return None if first else 'falling'


def _capteur_setting(key, default):
    """Lecture tolérante de la section [capteur] (absente sur les anciennes config)."""
    try:
        return SETTINGS.get("capteur", key, fallback=default)
    except Exception:
        return default


CYCLE_EDGE = str(_capteur_setting("edge", "rising")).strip().lower()       # 'falling' ou 'rising'
POLL_HZ = float(_capteur_setting("poll_hz", 50))
STABLE_SAMPLES = int(_capteur_setting("stable_samples", 3))
POLL_DT = 1.0 / POLL_HZ
CYCLE_INPUT = int(_capteur_setting("cycle_input", 2))     # signal noyau (cycle)
STOP_INPUT = int(_capteur_setting("stop_input", 1))       # signal arrêt machine (0 = désactivé)
REJECT_INPUT = int(_capteur_setting("reject_input", 3))   # signal rebut (0 = désactivé)
# Signal rebut tardif : s'il monte jusqu'à N s APRÈS l'impulsion de cycle, la dernière
# pièce déjà comptée "bonne" est requalifiée en rejet (0 = auto : durée du cycle cible)
REJECT_LATE_WINDOW = float(_capteur_setting("reject_late_window", 0))
# Détection d'arrêt sans signal : pas d'impulsion pendant cycle_t x facteur -> Arrêt non déclaré
STOP_TIMEOUT_FACTOR = float(_capteur_setting("stop_timeout_factor", 2.0))
STOP_TIMEOUT_MIN = float(_capteur_setting("stop_timeout_min", 30))
STOP_TIMEOUT_MAX = float(_capteur_setting("stop_timeout_max", 300))
# Contrôle du temps de cycle (CT) saisi vs temps de cycle réel mesuré
CT_MIN_S = float(_capteur_setting("ct_min_s", 1))                    # CT saisi plausible : mini
CT_MAX_S = float(_capteur_setting("ct_max_s", 70))                   # ... maxi (au-delà : saisie bloquée)
CT_TOLERANCE_S = float(_capteur_setting("ct_tolerance_s", 10))       # écart max accepté CT réel / CT saisi
CT_CONFIRM_CYCLES = int(_capteur_setting("ct_confirm_cycles", 3))    # cycles consécutifs hors tolérance avant alerte
CT_ALERT_PATH = os.path.join(os.path.dirname(SETTINGS["local_db"]["path"]), "modics_ct_alert.json")

# ---- MACHINE_GROUP_BEGIN ---------------------------------------------------
# Fichier "Machine Group M63" : Part Number autorisés sur cette presse, avec leur
# numéro d'outil et leur nombre d'empreintes. Lecture directe du .xlsx : seule la
# petite feuille utile est lue (la feuille source "Sheet1" pèse ~380 Mo et n'est
# JAMAIS chargée). Une copie JSON locale sert de secours si le .xlsx est absent.
MG_XLSX_PATH = SETTINGS.get("machine_group", "xlsx", fallback="/home/pi/Downloads/Machine_Group_M63.xlsx")
MG_SHEET = SETTINGS.get("machine_group", "sheet", fallback="Machine Group M63")
MG_CACHE_PATH = os.path.join(os.path.dirname(MG_XLSX_PATH) or ".", "machine_group_m63.json")
MG_MAX_SHEET_BYTES = 5_000_000
_MG_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_MG_DOC_RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_mg_state = {"sig": None, "data": {}}


def _mg_text(v):
    """12005.0 -> '12005' ; ' 13420/R ' -> '13420/R'."""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v).strip()


def _mg_read_xlsx(path, sheet_name):
    """-> {part: {'tool': str, 'cav': int, 'unscrew': int|None}} dans l'ordre du fichier."""
    with zipfile.ZipFile(path) as z:
        rid = None
        for s in ET.fromstring(z.read("xl/workbook.xml")).iter(_MG_NS + "sheet"):
            if s.get("name") == sheet_name:
                rid = s.get(_MG_DOC_RID)
        if rid is None:
            raise ValueError(f"feuille '{sheet_name}' introuvable")
        target = None
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
            if r.get("Id") == rid:
                target = r.get("Target")
        if not target:
            raise ValueError("relation de feuille introuvable")
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        if z.getinfo(target).file_size > MG_MAX_SHEET_BYTES:
            raise ValueError(f"feuille '{sheet_name}' trop volumineuse (>{MG_MAX_SHEET_BYTES} octets)")
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_MG_NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_MG_NS + "t")))
        rows = []
        for row in ET.fromstring(z.read(target)).iter(_MG_NS + "row"):
            vals = {}
            for c in row.iter(_MG_NS + "c"):
                v = c.find(_MG_NS + "v")
                if v is None or v.text is None:
                    continue
                col = re.match(r"[A-Z]+", c.get("r")).group()
                t = c.get("t")
                if t == "s":
                    vals[col] = shared[int(v.text)]
                elif t in ("str", "inlineStr", "e", "b"):
                    vals[col] = v.text
                else:
                    vals[col] = float(v.text)
            rows.append(vals)
    data, in_table = {}, False
    for vals in rows:
        a = vals.get("A")
        if not in_table:
            in_table = isinstance(a, str) and a.strip().lower().startswith("part number")
            continue
        if a is None or vals.get("B") is None or vals.get("C") is None:
            continue
        part = _mg_text(a)
        try:
            unscrew = int(float(vals["D"])) if vals.get("D") is not None else None
            data[part] = {"tool": _mg_text(vals["B"]), "cav": int(float(vals["C"])), "unscrew": unscrew}
        except (TypeError, ValueError):
            logger.warning("Machine Group : ligne ignorée pour le Part Number %s", part)
    return data


def load_machine_group():
    """Part Number autorisés sur la presse ({} si le fichier est indisponible -> saisie manuelle).
    Relu automatiquement quand le .xlsx change (date de modification)."""
    try:
        if os.path.exists(MG_XLSX_PATH):
            sig = (MG_XLSX_PATH, os.path.getmtime(MG_XLSX_PATH))
            if _mg_state["sig"] == sig:
                return _mg_state["data"]
            data = _mg_read_xlsx(MG_XLSX_PATH, MG_SHEET)
            if data:
                _mg_state.update(sig=sig, data=data)
                try:
                    with open(MG_CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                except Exception:
                    logger.exception("Machine Group : écriture de la copie JSON")
                logger.info("Machine Group : %d Part Number chargés depuis %s", len(data), MG_XLSX_PATH)
                return data
    except Exception:
        logger.exception("Machine Group : lecture du .xlsx impossible, copie JSON utilisée")
    try:
        if _mg_state["data"]:
            return _mg_state["data"]
        if os.path.exists(MG_CACHE_PATH):
            with open(MG_CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _mg_state.update(sig=None, data=data)
            return data
    except Exception:
        logger.exception("Machine Group : copie JSON illisible")
    return {}
# ---- MACHINE_GROUP_END -----------------------------------------------------
_INPUT_NAMES = {1: "one", 2: "two", 3: "three"}


def read_input(n):
    """Lit l'entrée n (1..3) de l'Automation HAT. Renvoie None si désactivée/inconnue."""
    name = _INPUT_NAMES.get(n)
    if name is None:
        return None
    return getattr(automationhat.input, name).is_on()


##############################################################################
# API HTTP locale : l'ERP (IFS) pousse les informations du nouvel OF.
#   GET  /api/v1/health       -> état du service (sans clé)
#   GET  /api/v1/status       -> état de production courant
#   POST /api/v1/shop-order   -> nouvel OF (JSON, en-tête X-Api-Key)
# Le thread HTTP ne touche jamais à l'interface : tout passe par Clock.
##############################################################################
API_FIELDS = {
    # clé API            : (clé interne popup, type, libellé)
    "shop_order":   ("so",       str,   "Shop Order"),
    "part_number":  ("part",     str,   "Part Number"),
    "tool_number":  ("tool",     str,   "Numéro outil"),
    "cycle_time":   ("cycle",    float, "Temps de cycle (s)"),
    "cavities":     ("cav",      int,   "Nombre d'empreintes"),
    "material_ref": ("mati",     str,   "Référence matière"),
    "quantity":     ("quantite", int,   "Quantité demandée"),
}
API_MAX_BODY = 64 * 1024


def validate_of_payload(payload):
    """Valide/convertit un OF JSON -> dict interne {so, part, tool, cycle, cav, mati, quantite,
    sequence, due_date}. Lève ValueError avec un message explicite."""
    if not isinstance(payload, dict):
        raise ValueError("Each order must be a JSON object")
    out = {}
    for api_key, (internal, typ, label) in API_FIELDS.items():
        if api_key not in payload or payload[api_key] in (None, ""):
            raise ValueError(f"Missing field: {api_key}")
        try:
            val = typ(payload[api_key])
        except (TypeError, ValueError):
            raise ValueError(f"Invalid type for {api_key}: expected {typ.__name__}")
        if typ is str:
            val = val.strip()
            if not val:
                raise ValueError(f"Empty field: {api_key}")
        elif val <= 0:
            raise ValueError(f"{api_key} must be > 0")
        if internal == "cycle" and not (CT_MIN_S <= val <= CT_MAX_S):
            raise ValueError(f"{api_key} must be between {CT_MIN_S:g} and {CT_MAX_S:g} s")
        out[internal] = val
    seq = payload.get("sequence")
    out["sequence"] = int(seq) if seq not in (None, "") else 9999
    out["due_date"] = str(payload.get("due_date") or "")
    return out


class _OfApiHandler(BaseHTTPRequestHandler):
    server_version = "MODICS/1.1"

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        """Autorise les appels depuis une page web (planner) sur une autre origine."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")
        self.send_header("Access-Control-Max-Age", "600")

    def do_OPTIONS(self):
        """Préflight CORS : le navigateur l'envoie avant tout POST/DELETE avec X-Api-Key."""
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _authorized(self):
        return self.headers.get("X-Api-Key", "") == self.server.api_key

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("Empty body")
        if length > API_MAX_BODY:
            raise OverflowError("Body too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _check_machine(self, payload):
        m = payload.get("machine")
        if m is not None and str(m).strip().upper() != self.server.manager.machine.upper():
            raise ValueError(f"Wrong machine: {m} (this terminal is {self.server.manager.machine})")

    def log_message(self, fmt, *args):            # logs HTTP -> logger applicatif
        logger.info("API %s - " + fmt, self.address_string(), *args)

    # --- GET -------------------------------------------------------------------
    def do_GET(self):
        if self.path == "/api/v1/health":
            return self._send(200, {"status": "ok", "machine": self.server.manager.machine,
                                    "time": datetime.now().isoformat(timespec="seconds")})
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/api/v1/status":
            return self._send(200, self.server.manager.api_status())
        if self.path == "/api/v1/queue":
            return self._send(200, {"machine": self.server.manager.machine,
                                    "orders": self.server.manager.api_queue()})
        self._send(404, {"error": "not found"})

    # --- POST ------------------------------------------------------------------
    def do_POST(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        try:
            payload = self._read_json()
        except OverflowError:
            return self._send(413, {"error": "body too large"})
        except (ValueError, UnicodeDecodeError) as e:
            return self._send(400, {"error": f"invalid JSON: {e}"})

        if self.path == "/api/v1/shop-order":
            # un seul OF : ajout / mise à jour dans la file
            try:
                self._check_machine(payload)
                values = validate_of_payload(payload)
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            auto_apply = bool(payload.get("auto_apply", False))
            action = self.server.manager.receive_of_from_erp(values, auto_apply)
            return self._send(202, {"accepted": True, "action": action, "shop_order": values["so"]})

        if self.path == "/api/v1/shop-orders":
            # file complète : remplace la liste des OF en attente (idempotent)
            try:
                self._check_machine(payload)
                orders = payload.get("orders")
                if not isinstance(orders, list):
                    raise ValueError("'orders' must be a list")
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            accepted, rejected = [], []
            for i, o in enumerate(orders):
                try:
                    accepted.append(validate_of_payload(o))
                except ValueError as e:
                    rejected.append({"index": i, "shop_order": (o or {}).get("shop_order") if isinstance(o, dict) else None,
                                     "error": str(e)})
            action = self.server.manager.replace_queue_from_erp(accepted)
            return self._send(202 if not rejected else 207,
                              {"accepted": len(accepted), "rejected": rejected, "action": action,
                               "queue": [v["so"] for v in sorted(accepted, key=lambda v: v["sequence"])]})
        self._send(404, {"error": "not found"})

    # --- DELETE ----------------------------------------------------------------
    def do_DELETE(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        prefix = "/api/v1/shop-orders/"
        if not self.path.startswith(prefix):
            return self._send(404, {"error": "not found"})
        from urllib.parse import unquote
        so = unquote(self.path[len(prefix):])
        removed = self.server.manager.remove_from_queue_from_erp(so)
        return self._send(200 if removed else 404, {"shop_order": so, "removed": removed})


class OfApiServer:
    def __init__(self, manager, host, port, api_key):
        self.manager, self.host, self.port, self.api_key = manager, host, int(port), api_key
        self._httpd = None

    def start(self):
        if not self.api_key or self.api_key == "CHANGE_ME":
            logger.warning("API OF désactivée : renseigner [api] api_key dans config_modics.ini")
            return False
        Thread(target=self._serve_forever_resilient, name="modics-api", daemon=True).start()
        return True

    def _serve_forever_resilient(self):
        """Lie le port puis sert ; en cas d'échec (port occupé après un crash, erreur réseau) retente
        toutes les 10 s au lieu de laisser l'API morte jusqu'au prochain redémarrage du terminal."""
        while True:
            try:
                self._httpd = ThreadingHTTPServer((self.host, self.port), _OfApiHandler)
                self._httpd.manager = self.manager
                self._httpd.api_key = self.api_key
                self._httpd.daemon_threads = True
                logger.info("API OF à l'écoute sur http://%s:%d/api/v1/", self.host, self.port)
                self._httpd.serve_forever()
            except Exception:
                logger.exception("API OF arrêtée, nouvelle tentative dans 10 s")
            finally:
                if self._httpd is not None:
                    try:
                        self._httpd.server_close()
                    except Exception:
                        pass
                    self._httpd = None
            time.sleep(10)


Builder.load_file('screen.kv')
conn = sqlite3.connect(SETTINGS["local_db"]["path"])

Window.fullscreen = True
Window.show_cursor = False
Window.size = (800, 480)  # doit correspondre à la vraie résolution de l'écran tactile du Pi
Config.read("/home/pi/Downloads/config.ini")  # réglages fenêtre Kivy (distinct de config_modics.ini)

# BACKEND_URL = "http://192.168.82.202:5000/api/data-test"
##############################################################
# Input Output Declaration
##############################################################

if automationhat.is_automation_hat():
    automationhat.light.power.write(1)
else:
    automationhat.light.power.write(0)

#####################################################################
# Main Screen Manager
#####################################################################

##############################################################################
# Couche accès données : tout ce qui parle MySQL local / SQL Server MODICS
# est ici, indépendamment de Kivy. Les requêtes SQL (tables/colonnes) sont
# EXACTEMENT celles de la version précédente - aucun changement de schéma.
##############################################################################
class Database:
    """
    Encapsule :
    - la connexion au buffer local MySQL (internal_machine_db)
    - la connexion au serveur central MODICS (SQL Server, via pymssql)
    - le pattern générique "écrire en local -> copier vers MODICS -> ne vider
      le local que si la copie est confirmée" utilisé par sync_daily()/sync_stops()
    """

    def __init__(self):
        self._daily_lock = Lock()
        self._stop_lock = Lock()

    # ---- connexions -------------------------------------------------------
    @staticmethod
    def internal_conn():
        """Connexion au buffer local MySQL (tampon avant synchro vers MODICS)."""
        cfg = SETTINGS["internal_db"]
        return mysql.connector.connect(
            host=cfg["host"],
            database=cfg["database"],
            user=cfg["user"],
            password=cfg["password"],
            auth_plugin='mysql_native_password',
            connection_timeout=5,
        )

    @staticmethod
    def external_conn(timeout=10):
        """Connexion au serveur central MODICS (SQL Server)."""
        cfg = SETTINGS["external_db"]
        return pymssql.connect(
            server=cfg["server"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            login_timeout=timeout,
            timeout=timeout,
        )

    # ---- écriture locale synchrone (rapide, ne doit jamais bloquer) ------
    def insert_local(self, insert_sql, params, context):
        """Ecrit une ligne dans le buffer local. Ne lève pas : log et renvoie False si échec."""
        try:
            mydb = self.internal_conn()
            cur = mydb.cursor()
            cur.execute(insert_sql, params)
            mydb.commit()
            mydb.close()
            return True
        except Exception:
            logger.exception("Echec écriture locale (%s)", context)
            return False

    # ---- synchro tampon local -> MODICS, en tâche de fond -----------------
    def _sync_buffer_table(self, lock, table, insert_sql_external, context):
        """
        Pattern générique : SELECT * du buffer local -> INSERT vers MODICS ->
        DELETE du buffer local UNIQUEMENT si l'insertion externe a réussi.
        En cas d'échec réseau, les lignes restent en local pour réessai au
        prochain appel (auto-guérison, pas de perte de données).
        """
        with lock:
            try:
                mydb = self.internal_conn()
                cur = mydb.cursor()
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                if not rows:
                    mydb.close()
                    return

                ext = self.external_conn()
                cur_ext = ext.cursor()
                cur_ext.executemany(insert_sql_external, rows)
                ext.commit()
                ext.close()

                cur.execute(f"DELETE FROM {table}")
                mydb.commit()
                mydb.close()
                logger.info("%d ligne(s) synchronisée(s) vers MODICS (%s)", len(rows), context)
            except Exception:
                logger.exception("Echec synchro MODICS (%s) - conservé en local pour réessai", context)

    def sync_daily_async(self):
        Thread(
            target=self._sync_buffer_table,
            args=(self._daily_lock, "Machine_Daily_Table_Mould", DAILY_INSERT_EXTERNAL_SQL, "bilan de shift"),
            daemon=True,
        ).start()

    def sync_stops_async(self):
        Thread(
            target=self._sync_buffer_table,
            args=(self._stop_lock, "Machine_Stop_Table_Mould", STOP_INSERT_EXTERNAL_SQL, "arrêts"),
            daemon=True,
        ).start()


# Requêtes SQL Server (texte identique à l'ancienne version - schéma inchangé)
DAILY_INSERT_EXTERNAL_SQL = '''INSERT INTO Machine_Daily_Table_Mould
    (Machine_Name_Mould, Date_Insert_Day_Mould, Run_Hours_Day_Mould, Down_Hours_Day_Mould,
     Good_QTY_Day_Mould, Rejects_QTY_Day_Mould, Cycle_Time_Day, Availability_Rate_Day_Mould,
     Performance_Rate_Day_Mould, Quality_Rate_Day_Mould, OEE_Day_Mould, Shift_Mould, Part_Number_Mould)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'''

STOP_INSERT_EXTERNAL_SQL = '''INSERT INTO Machine_Stop_Table_Mould
    (Machine_Name_Mould, Date_Insert_Mould, Part_NO_Mould, Code_Stop_Mould, Debut_Stop_Time_Mould,
     Fin_Stop_Time_Mould, Regleur_Prenom_Mould, Shift)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'''


##############################################################################
# Calculs métier purs (shift, statut de cycle) - aucune dépendance Kivy/BD,
# donc vérifiables/testables isolément.
##############################################################################
class OEECalculator:
    @staticmethod
    def get_shift(now):
        h = now.hour          # 06-13 : A | 14-21 : B | 22-05 : C
        if 6 <= h < 14:
            return 'Shift A'
        if 14 <= h < 22:
            return 'Shift B'
        return 'Shift C'


##############################################################################
# Notifications email - hors thread Kivy (le SMTP ne doit jamais bloquer l'UI)
##############################################################################
class Notifier:
    @staticmethod
    def send_async(msg, receivers):
        cfg = SETTINGS["email"]

        def _send():
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as server:
                    server.login(cfg["sender"], cfg["app_password"])
                    server.sendmail(cfg["sender"], receivers, msg.as_string())
                logger.info("Email d'alerte envoyé")
            except Exception:
                logger.exception("Echec envoi email d'alerte")

        Thread(target=_send, daemon=True).start()


class Manager(AnchorLayout,BoxLayout):
    machine = SETTINGS["machine"]["name"]
    Machine = SETTINGS["machine"]["name"]
    term= 0
    cycle_moy = 0
    pilote=''
    perfermance = 0
    avaibility = 0
    quality = 0
    OEE = 0
    run_hrs = 0
    run=0
    stop_hrs = 0
    stop=0
    stop_planned=0
    empreint = 0
    TRS = 0
    t_c_th=1
    t1=0
    t2=0
    hh=0
    mm=0
    ss=0
    quantitePalanifie = 0
    qtRestante=0
    qtProduite=0
    qtPurge_ajout= 0
    qtPurge = 0
    qtPurge_r=0
    qtRejet=0
    qtBon=0
    qtBon_r=0
    qtRejet_r=0
    duree=3600
    qtRejet_ajout = 0
    qtBon_ajout = 0
    shopOrder =''
    partNumber =''
    touls =''  
    matricule =''  
    progression =0
    step = 1
    cycle = 0
    CodeArret=''
    code=''
    cycle_t=0
    matiere= ''
    start_time=time.time()
    now=datetime.now()    
    brande = ''
    shift=''
    statu='open'
    id_insert_d=1
    id_insert_h=1
    id_insert_s=1
    date = str(datetime.now())[0:19]
    recent=''
    etat='0'
    email_receiver = SETTINGS["email"]["receivers_default"].split(",")
    ###############################################
    # Alerte temps de cycle (CT saisi vs CT réel)
    ###############################################
    ct_alerte = BooleanProperty(False)
    ct_alerte_text = StringProperty('')
    _ct_nb_hors = 0
    _ct_popup = None
    ###############################################
    # started at finished at shop order
    ###############################################
    debut_arret=datetime.now()
    fin_arret=datetime.now()
    start = time.time()
    end = time.time()
    backend_interval = 5
    last_backend_send = 0
    debut_arret_mach_off=datetime.now()
    fin_arret_mach_off=datetime.now()

  
    def __init__(self, **kwargs):     
        super(Manager, self).__init__(**kwargs)
        self.db = Database()
        self._decl_queue = []        # arrêts terminés mais pas encore déclarés
        self._arret_popup = None
        self._restart_code = ''      # cause conservée entre END STOP et le 1er cycle
        self._stop_origin = None     # 'timeout' | 'signal'
        # --- données du tableau de bord (présentation uniquement) ---
        self.cycle_hist = deque(maxlen=30)
        self.detector = CycleDetector(STABLE_SAMPLES)
        self.detector_stop = CycleDetector(STABLE_SAMPLES)
        self.detector_rejet = CycleDetector(STABLE_SAMPLES)
        self.reject_mode = False
        self._last_cycle_t = 0.0        # instant de la dernière impulsion comptée
        self._last_cycle_good = False   # True = dernier cycle compté en Bonnes (requalifiable)
        self._last_cycle_qty = 0        # nb de pièces de ce cycle (= empreint)
        self._late_rej_used = False     # le front rebut courant a déjà requalifié un cycle
        self._auto_stop_code = None     # code de l'arrêt automatique en cours (non déclaré / signal)
        self.cycle_raw = 0.0
        self.cycle_status = 'OK'
        self.Ta_live = self.Tp_live = self.Tq_live = 0
        self.of_stats = {s: self._empty_stats() for s in self.SHIFTS}
        self._period_shift = self._load_period_shift()
        self.resume()
        self._load_of_stats()
        self._ct_load()
        self.refresh_dashboard()
        Clock.schedule_interval(self.tick_chrono, 0.1)
        # --- API ERP (IFS) : file des OF en attente ---
        self.of_queue = []
        self._of_popup = None
        self._queue_popup = None
        self._queue_load()
        if not getattr(self, 'of_active', False):
            Clock.schedule_once(lambda dt: self.open_next_of(mandatory=True), 1.0)
        self.api_server = None
        if str(SETTINGS.get("api", "enabled", fallback="true")).lower() in ("1", "true", "yes"):
            self.api_server = OfApiServer(self, SETTINGS.get("api", "host", fallback="0.0.0.0"),
                                          SETTINGS.get("api", "port", fallback="8080"),
                                          SETTINGS.get("api", "api_key", fallback=""))
            self.api_server.start()
        
        # automationhat.relay.one.on()
        self.etat = '0'
        Clock.schedule_once(self.start_app,5)
    
    def power_off(self):
        os.system("sudo shutdown -h now")

    # ------------------------------------------------------------------
    # Tableau de bord Industrie 4.0 (jauge, KPI, courbe, chrono)
    # ------------------------------------------------------------------
    SHIFTS = ('Shift A', 'Shift B', 'Shift C')
    OF_STATS_PATH = os.path.join(os.path.dirname(SETTINGS["local_db"]["path"]), "modics_of_stats.json")

    @staticmethod
    def _empty_stats():
        return {"run": 0.0, "stop": 0.0, "term": 0, "bon": 0, "rejet": 0}

    def _reset_of_stats(self):
        self.of_stats = {s: self._empty_stats() for s in self.SHIFTS}
        self._save_of_stats()

    def _save_of_stats(self):
        try:
            with open(self.OF_STATS_PATH, "w", encoding="utf-8") as f:
                json.dump({"shopOrder": self.shopOrder, "stats": self.of_stats}, f)
        except Exception:
            logger.exception("Sauvegarde cumuls OF")

    def _load_of_stats(self):
        self.of_stats = {s: self._empty_stats() for s in self.SHIFTS}
        try:
            if os.path.exists(self.OF_STATS_PATH):
                with open(self.OF_STATS_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("shopOrder") == self.shopOrder:
                    for s in self.SHIFTS:
                        self.of_stats[s].update(data.get("stats", {}).get(s, {}))
        except Exception:
            logger.exception("Chargement cumuls OF")

    def _live_window(self):
        """Fenêtre du shift en cours (accumulateurs remis à zéro à chaque fin de shift)."""
        return {"run": float(self.run), "stop": float(self.stop), "term": int(self.term),
                "bon": int(self.qtBon_r), "rejet": int(self.qtRejet_r)}

    def _accumulate_current_window(self, shift=None):
        """Appelé en fin de shift (daily_report) AVANT la remise à zéro des accumulateurs."""
        w = self._live_window()
        st = self.of_stats.setdefault(shift or self._period_shift, self._empty_stats())
        for k in w:
            st[k] += w[k]
        self._save_of_stats()

    def _trs_from(self, st):
        """Mêmes formules que daily_report : A = run/(run+stop), P = cycle_t*term/run, Q = bon/(bon+rejet)."""
        run, stop = float(st["run"]), float(st["stop"])
        term, bon, rejet = st["term"], st["bon"], st["rejet"]
        if run <= 0 or bon <= 0 or not self.cycle_t:
            return 0.0
        a = run / (run + stop) if (run + stop) > 0 else 0.0
        p = (float(self.cycle_t) * term) / run
        q = bon / (bon + rejet) if (bon + rejet) > 0 else 0.0
        return round(a * p * q * 100, 1)

    def _shift_stats_with_live(self, shift):
        st = dict(self.of_stats.get(shift, self._empty_stats()))
        if shift == self._period_shift:
            for k, v in self._live_window().items():
                st[k] += v
        return st

    def _global_stats(self):
        tot = self._empty_stats()
        for s in self.SHIFTS:
            for k, v in self._shift_stats_with_live(s).items():
                tot[k] += v
        return tot

    def refresh_dashboard(self):
        """Pousse les valeurs déjà calculées vers les widgets du dashboard."""
        try:
            ids = self.ids
            alert = self.ct_alerte
            trs_global = self._trs_from(self._global_stats())
            ids.oee_gauge.value = 0 if alert else min(100.0, trs_global)
            ids.oee_pct.text = '--' if alert else f"{trs_global:.0f} %"
            ids.kpi_shift_a.text = '--' if alert else f"{self._trs_from(self._shift_stats_with_live('Shift A')):.0f} %"
            ids.kpi_shift_b.text = '--' if alert else f"{self._trs_from(self._shift_stats_with_live('Shift B')):.0f} %"
            ids.kpi_shift_c.text = '--' if alert else f"{self._trs_from(self._shift_stats_with_live('Shift C')):.0f} %"
            ids.cycle_chart.points = list(self.cycle_hist)
            ids.cycle_chart.target = float(self.cycle_t or 0)
            ids.cycle_target.text = f"cible {float(self.cycle_t or 0):.1f} s"
        except Exception:
            logger.exception("refresh_dashboard")

    # ------------------------------------------------------------------
    # Interface unique : popups avec clavier tactile intégré
    # ------------------------------------------------------------------
    C_NAVY = (0.05, 0.14, 0.24, 1)
    C_NAVY_L = (0.10, 0.22, 0.36, 1)
    C_ORANGE = (0.95, 0.40, 0.13, 1)
    C_GREEN = (0.16, 0.60, 0.35, 1)
    C_RED = (0.82, 0.24, 0.24, 1)
    C_AMBER = (0.93, 0.63, 0.18, 1)
    C_GREY = (0.40, 0.44, 0.50, 1)
    C_MUTED = (0.72, 0.76, 0.82, 1)

    @staticmethod
    def _btn(text, bg, fg=(1, 1, 1, 1), font_size=20, **kw):
        return Button(text=text, background_normal='', background_down='',
                      background_color=bg, color=fg, bold=True, font_size=font_size, **kw)

    def _popup(self, title, content, size_hint):
        return Popup(title=title, title_size=19, title_align='center', title_color=(1, 1, 1, 1),
                     separator_color=self.C_ORANGE, separator_height=3,
                     content=content, size_hint=size_hint, auto_dismiss=False,
                     background_color=self.C_NAVY)

    def _actions(self, ok_text='VALIDER', cancel=True):
        row = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=56)
        ok = self._btn(ok_text, self.C_GREEN, font_size=20)
        row.add_widget(ok)
        cancel_btn = None
        if cancel:
            cancel_btn = self._btn('ANNULER', self.C_GREY, font_size=18)
            row.add_widget(cancel_btn)
        return row, ok, cancel_btn

    def _keypad(self, on_key, mode):
        """
        mode = 'int'    : 3 colonnes  1-9 / C 0 DEL
        mode = 'digits' : 4 colonnes  chiffres + . / - + DEL C ABC
        mode = 'letters': 6 colonnes  A-Z + DEL 123
        """
        from kivy.uix.gridlayout import GridLayout
        layouts = {
            'int': (3, ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'C', '0', 'DEL']),
            'digits': (4, ['1', '2', '3', 'DEL', '4', '5', '6', 'C', '7', '8', '9', '.', '/', '-', '0', 'ABC']),
            'letters': (6, list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + ['DEL', '123']),
        }
        cols, keys = layouts[mode]
        grid = GridLayout(cols=cols, spacing=5)
        colors = {'DEL': self.C_AMBER, 'C': self.C_RED, 'ABC': self.C_NAVY, '123': self.C_NAVY}
        for k in keys:
            bg = colors.get(k, self.C_NAVY_L)
            b = self._btn(k, bg, font_size=18 if len(k) > 1 else 24)
            b.bind(on_press=lambda btn: on_key(btn.text))
            grid.add_widget(b)
        return grid

    def _form_popup(self, title, fields, on_valid, mandatory=False, letters=True, check=None,
                    suggest=None, on_edit=None, extra_action=None):
        """
        Popup formulaire : colonne de champs à gauche, clavier à droite.
        fields : liste de dict {key, label, value, kind} ; kind in ('text','int','float').
        extra_action : (libellé, couleur, callback) -> 2e bouton à côté de VALIDER. Il ne vérifie aucun champ :
        il ferme le formulaire et appelle callback() (ex. arrêt planifié de la machine, sans OF).
        """
        from kivy.uix.floatlayout import FloatLayout
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.scrollview import ScrollView

        root = BoxLayout(orientation='horizontal', spacing=12, padding=[6, 8, 6, 6])
        left = BoxLayout(orientation='vertical', spacing=6, size_hint=(1, 1))
        left_fl = FloatLayout(size_hint_x=0.56)       # le panneau de suggestions flotte par-dessus les champs
        left_fl.add_widget(left)
        right = BoxLayout(orientation='vertical', spacing=8, size_hint_x=0.44)
        inputs, state = {}, {'active': None, 'mode': 'digits'}
        limits, kinds = {}, {}            # verrous de saisie par champ (clé = id du widget)

        grid = GridLayout(cols=2, spacing=[8, 6], row_default_height=46, row_force_default=True)
        for f in fields:
            lab = Label(text=f['label'], font_size=15, color=self.C_MUTED, halign='right',
                        valign='middle', size_hint_x=0.42)
            lab.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], None)))
            ti = FormField(text=str(f.get('value', '')), font_size=21, halign='left')
            if f.get('locked'):
                ti.locked = True
                ti._upd()
                ti.bind(focus=lambda w, foc: setattr(w, 'focus', False) if foc else None)
            else:
                ti.bind(focus=lambda w, foc, key=f['key']: on_focus(w, foc, key))
            inputs[f['key']] = ti
            kinds[id(ti)] = f.get('kind', 'text')
            if f.get('max') is not None:
                limits[id(ti)] = float(f['max'])
            grid.add_widget(lab)
            grid.add_widget(ti)
        left.add_widget(grid)
        error = Label(text='', color=(1, 0.55, 0.45, 1), font_size=14, size_hint_y=None, height=24)
        left.add_widget(error)
        left.add_widget(Widget())  # ressort

        suggest_keys = {f['key'] for f in fields if f.get('suggest')}
        keys_by_id = {id(w): k for k, w in inputs.items()}
        sug = {'panel': None}

        def fill_fields(values):
            for k, v in values.items():
                inputs[k].text = str(v)

        def hide_suggestions(*a):
            p = sug['panel']
            if p is not None:
                if p.parent is not None:
                    p.parent.remove_widget(p)
                sug['panel'] = None

        def pick(values):
            fill_fields(values)
            error.text = ''
            hide_suggestions()

        def show_suggestions(key):
            """Panneau de résultats filtrés selon ce qui est tapé dans le champ `key` (se pose sous le champ)."""
            hide_suggestions()
            if suggest is None or key not in suggest_keys:
                return
            ti = inputs[key]
            rows = suggest(key, ti.text)
            n = len(rows)
            bar_h, row_h = 30, 40
            panel = BoxLayout(orientation='vertical', spacing=4, padding=[6, 4, 6, 6], size_hint=(None, None))
            panel.size = (grid.width, 14 + bar_h + min(n, 4) * (row_h + 4))
            panel.pos = (grid.x, ti.y - panel.height - 2)
            with panel.canvas.before:
                Color(0.05, 0.14, 0.24, 1)
                bg = RoundedRectangle(pos=panel.pos, size=panel.size, radius=[8])
                Color(0.95, 0.40, 0.13, 1)
                border = Line(rounded_rectangle=(panel.x, panel.y, panel.width, panel.height, 8), width=1.6)

            def _sync(*a):
                bg.pos, bg.size = panel.pos, panel.size
                border.rounded_rectangle = (panel.x, panel.y, panel.width, panel.height, 8)
            panel.bind(pos=_sync, size=_sync)
            bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=bar_h, spacing=6)
            info = Label(text=(f"{n} résultat(s) — touchez pour choisir" if n else "Aucun résultat dans le fichier"),
                         font_size=14, color=self.C_MUTED if n else (1, 0.55, 0.45, 1),
                         halign='left', valign='middle')
            info.bind(size=lambda w, s: setattr(w, 'text_size', s))
            close_b = self._btn('X', self.C_GREY, font_size=16, size_hint_x=None, width=44)
            close_b.bind(on_release=hide_suggestions)
            bar.add_widget(info)
            bar.add_widget(close_b)
            panel.add_widget(bar)
            if n:
                sv = ScrollView(do_scroll_x=False)
                lst = GridLayout(cols=1, spacing=4, size_hint_y=None)
                lst.bind(minimum_height=lst.setter('height'))
                for text, values in rows:
                    b = self._btn(text, self.C_NAVY_L, font_size=17, size_hint_y=None, height=row_h)
                    b.markup = True
                    b.halign, b.valign = 'left', 'middle'
                    b.bind(size=lambda w, s: setattr(w, 'text_size', (s[0] - 16, s[1])))
                    b.bind(on_release=lambda w, values=values: pick(values))
                    lst.add_widget(b)
                sv.add_widget(lst)
                panel.add_widget(sv)
            left_fl.add_widget(panel)
            sug['panel'] = panel

        def on_focus(w, foc, key):
            if not foc:
                return
            state['active'] = w
            if key in suggest_keys:
                show_suggestions(key)
            else:
                hide_suggestions()

        def after_edit(ti):
            """Après chaque frappe : champs liés (ex. outil/empreintes) + filtre des suggestions."""
            key = keys_by_id.get(id(ti))
            if key is None:
                return
            if on_edit is not None:
                upd = on_edit(key, ti.text)
                if upd:
                    fill_fields(upd)
            if key in suggest_keys:
                show_suggestions(key)

        pad_holder = BoxLayout()
        right.add_widget(pad_holder)

        def on_key(k):
            if k in ('ABC', '123'):
                state['mode'] = 'letters' if k == 'ABC' else 'digits'
                rebuild()
                return
            ti = state['active']
            if ti is None:
                error.text = 'Touchez d’abord un champ à modifier.'
                return
            error.text = ''
            if k == 'DEL':
                ti.text = ti.text[:-1]
            elif k == 'C':
                ti.text = ''
            else:
                kind = kinds.get(id(ti), 'text')
                if kind in ('int', 'float') and (k not in '0123456789.' or
                                                 (k == '.' and (kind == 'int' or '.' in ti.text))):
                    error.text = 'Chiffres uniquement'
                    return
                new = ti.text + k
                mx = limits.get(id(ti))
                if mx is not None:
                    try:
                        if float(new) > mx:
                            error.text = f"Maximum {mx:g} s"
                            return
                    except ValueError:
                        pass              # saisie intermédiaire (ex. '.') : acceptée
                ti.text = new
            after_edit(ti)

        def rebuild():
            pad_holder.clear_widgets()
            mode = state['mode'] if letters else 'digits'
            pad_holder.add_widget(self._keypad(on_key, mode))
        rebuild()
        if not letters:
            for w in list(pad_holder.children[0].children):
                if w.text == 'ABC':
                    w.disabled = True
                    w.opacity = 0

        actions, ok, cancel = self._actions(cancel=not mandatory)
        extra_btn = None
        if extra_action:
            extra_btn = self._btn(extra_action[0], extra_action[1], font_size=16)
            actions.add_widget(extra_btn, index=0 if cancel is None else 1)   # VALIDER | ARRÊT PLANIFIÉ | (ANNULER)
        right.add_widget(actions)
        root.add_widget(left_fl)
        root.add_widget(right)
        popup = self._popup(title, root, (0.96, 0.95))

        def validate(*a):
            values = {}
            for f in fields:
                raw = inputs[f['key']].text.strip()
                kind = f.get('kind', 'text')
                if raw == '':
                    error.text = f"Champ obligatoire : {f['label']}"
                    inputs[f['key']].focus = True
                    return
                try:
                    if kind == 'int':
                        values[f['key']] = int(float(raw))
                    elif kind == 'float':
                        values[f['key']] = float(raw)
                    else:
                        values[f['key']] = raw
                    if kind in ('int', 'float') and values[f['key']] <= 0:
                        raise ValueError
                except ValueError:
                    error.text = f"Valeur invalide : {f['label']} (nombre > 0 attendu)"
                    inputs[f['key']].focus = True
                    return
            if check is not None:
                msg = check(values)
                if msg:
                    error.text = msg
                    return
            popup.dismiss()
            try:
                on_valid(values)
            except Exception:
                logger.exception("Validation popup '%s'", title)

        ok.bind(on_release=validate)
        if extra_btn is not None:
            def _extra(*a):
                popup.dismiss()
                try:
                    extra_action[2]()
                except Exception:
                    logger.exception("Action '%s' du popup '%s'", extra_action[0], title)
            extra_btn.bind(on_release=_extra)
        if cancel is not None:
            cancel.bind(on_release=popup.dismiss)
        popup.open()
        first = inputs[fields[0]['key']]
        Clock.schedule_once(lambda dt: setattr(first, 'focus', True), 0.2)
        return popup

    # --- Nouvel OF --------------------------------------------------------
    def open_of_popup(self, mandatory=False, prefill=None):
        """prefill : dict {so, part, tool, cycle, cav, mati, quantite} (ex. reçu de l'ERP)."""
        cur = {
            'so': self.shopOrder, 'part': self.ids.part1.text, 'tool': self.touls,
            'cycle': self.cycle_t if self.cycle_t and self.cycle_t != 1 else '',
            'cav': self.empreint or '', 'mati': self.ids.matiere1.text,
            'quantite': self.quantitePalanifie or '',
        }
        src = prefill or cur
        mg = load_machine_group()          # Part Number autorisés sur cette presse (fichier Excel)
        part_extra, suggest_args = {}, {}
        if mg:
            src = dict(src)
            ref = mg.get(str(src['part']).strip())
            if ref is not None:             # outil / empreintes imposés par le fichier
                src['tool'], src['cav'] = ref['tool'], ref['cav']
            else:
                if src['part']:
                    logger.warning("Part Number %s absent du fichier Machine Group : à corriger", src['part'])
                src['tool'], src['cav'] = '', ''
            part_extra = {'suggest': True}

            def _hl(txt, q):
                k = txt.lower().find(q) if q else -1
                return txt if k < 0 else f"{txt[:k]}[color=ff6621][b]{txt[k:k + len(q)]}[/b][/color]{txt[k + len(q):]}"

            def suggest_fn(key, text):
                """Lignes du fichier dont le Part Number (ou le n° d'outil) contient ce qui est tapé."""
                q = text.strip().lower()
                hits = []
                for p, d in mg.items():
                    val = (p if key == 'part' else d['tool']).lower()
                    if not q or q in val:
                        hits.append((0 if val.startswith(q) else 1, p, d))
                hits.sort(key=lambda h: h[0])          # tri stable : ceux qui commencent par la saisie d'abord
                out = []
                for _, p, d in hits:
                    pt = _hl(p, q) if key == 'part' else p
                    tl = _hl(d['tool'], q) if key == 'tool' else d['tool']
                    out.append((f"{pt}    ·    outil {tl}    ·    {d['cav']} empr.",
                                {'part': p, 'tool': d['tool'], 'cav': d['cav']}))
                return out

            def on_edit_fn(key, text):
                """Part Number complet tapé -> outil et empreintes remplis ; sinon vidés (plus de valeur périmée)."""
                if key != 'part':
                    return None
                r = mg.get(text.strip())
                return {'tool': r['tool'], 'cav': r['cav']} if r else {'tool': '', 'cav': ''}
            suggest_args = {'suggest': suggest_fn, 'on_edit': on_edit_fn}
        fields = [
            {'key': 'so', 'label': 'Shop Order', 'value': src['so'], 'kind': 'text'},
            dict({'key': 'part', 'label': 'Part Number', 'value': src['part'], 'kind': 'text'}, **part_extra),
            {'key': 'tool', 'label': 'Numéro outil', 'value': src['tool'], 'kind': 'text', 'suggest': bool(mg)},
            {'key': 'cycle', 'label': f'Temps de cycle ({CT_MIN_S:g}-{CT_MAX_S:g} s)', 'value': src['cycle'],
             'kind': 'float', 'max': CT_MAX_S},
            {'key': 'cav', 'label': "Nombre d'empreintes", 'value': src['cav'], 'kind': 'int', 'locked': bool(mg)},
            {'key': 'mati', 'label': 'Référence matière', 'value': src['mati'], 'kind': 'text'},
            {'key': 'quantite', 'label': 'Quantité demandée', 'value': src['quantite'], 'kind': 'int'},
        ]
        if prefill:
            title = f"OF ERP — {prefill['so']} — vérifier puis valider"
        else:
            title = 'NOUVEL ORDRE DE FABRICATION' if mandatory else "MODIFIER L'ORDRE DE FABRICATION"
        self._close_of_popups()
        extra = (('ARRÊT PLANIFIÉ', self.C_PLANNED, self._start_idle_planned_stop)
                 if (mandatory or prefill) else None)
        self._of_popup = self._form_popup(title, fields, self._apply_of_and_clear,
                                          mandatory=mandatory, letters=True,
                                          check=self._check_of_values, extra_action=extra, **suggest_args)

    def _idle_planned_stop(self):
        """Vrai si la presse est en arrêt planifié SANS OF (arrêt lié à la machine, pas à un ordre)."""
        return (not getattr(self, 'of_active', False)) and self.ids.cas.text == self.STATE_NOT_SCHEDULED

    def _start_idle_planned_stop(self):
        """Bouton « ARRÊT PLANIFIÉ » de l'écran de saisie d'OF : la presse passe en arrêt planifié (hors TRS),
        sans OF ni champ à remplir. Fenêtre « STOP CODE » : END STOP termine l'arrêt puis rouvre la saisie d'OF."""
        self._of_popup = None
        self.shift = OEECalculator.get_shift(self.now)
        self.shopOrder = ''                  # arrêt de la machine : aucun ordre associé
        self.debut_arret = datetime.now()
        self.ids.Arrets.text = self.PLANNED_CODE
        self.Btn()                           # même mécanique qu'une cause choisie dans « DÉCLARER UN ARRÊT »
        logger.info("Arrêt planifié de la machine démarré (sans OF)")

    def _end_idle_planned_stop(self):
        """END STOP pendant un arrêt planifié sans OF : ligne d'arrêt écrite pour la machine (sans shop order),
        puis retour à la saisie du nouvel OF."""
        now = datetime.now()
        self.shift = OEECalculator.get_shift(self.now)
        Clock.unschedule(self.bleu)
        Clock.unschedule(self.rouge)
        Clock.unschedule(self.compteur)
        Clock.unschedule(self.controle)
        self.stop_insert_extern(self.machine, self._fmt(now), '', self.PLANNED_CODE,
                                self._fmt(self.debut_arret), self._fmt(now), self.pilote, self.shift)
        logger.info("Arrêt planifié de la machine terminé (%s -> %s)", self._fmt(self.debut_arret), self._fmt(now))
        self.ids.cas.text = ''
        self.ids.Arrets.text = 'Signaler un Arrêt'
        self.ids.Arrets.background_color = [0, 0, 1, 1]
        self.ids.start.text = ''
        self.ids.horloge.text = ''
        self.hh = self.mm = self.ss = 0
        self.code = ''
        self._restart_code = ''
        self._auto_stop_code = None
        self.etat = '0'
        self.update_data()
        Clock.schedule_once(lambda dt: self.open_next_of(mandatory=True), 0.3)

    def _apply_of_and_clear(self, values):
        self._of_popup = None
        self.apply_of(values)
        self._queue_remove(values['so'])          # l'OF lancé sort de la file

    def _close_of_popups(self):
        for attr in ('_of_popup', '_queue_popup'):
            p = getattr(self, attr, None)
            if p is not None:
                try:
                    p.dismiss()
                except Exception:
                    pass
                setattr(self, attr, None)

    def open_next_of(self, mandatory=True):
        """Point d'entrée unique quand il faut un nouvel OF : liste ERP si elle existe, sinon saisie."""
        if self._idle_planned_stop():
            return                       # arrêt planifié de la machine en cours : la saisie reviendra à END STOP
        if self.of_queue:
            self.open_queue_popup(mandatory=mandatory)
        else:
            self.open_of_popup(mandatory=mandatory)

    def open_queue_popup(self, mandatory=True):
        """Liste des OF en attente reçus de l'ERP : l'opérateur choisit le prochain."""
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.gridlayout import GridLayout
        self._close_of_popups()
        box = BoxLayout(orientation='vertical', spacing=8, padding=10)
        box.add_widget(Label(text=f"{len(self.of_queue)} ordre(s) en attente pour {self.machine} — touchez celui à lancer",
                             font_size=15, color=self.C_MUTED, size_hint_y=None, height=24))
        scroll = ScrollView(do_scroll_x=False)
        grid = GridLayout(cols=1, spacing=6, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        popup = self._popup(f'ORDRES DE FABRICATION EN ATTENTE', box, (0.9, 0.95))
        self._queue_popup = popup

        def pick(order):
            def _cb(*a):
                popup.dismiss()
                self._queue_popup = None
                self.open_of_popup(mandatory=mandatory, prefill=order)
            return _cb

        for o in sorted(self.of_queue, key=lambda v: (v.get('sequence', 9999), v.get('received_at', ''))):
            due = f"   ·   échéance {o['due_date']}" if o.get('due_date') else ''
            txt = (f"[b]{o['so']}[/b]   ·   {o['part']}   ·   {o['quantite']} pcs   ·   "
                   f"cycle {o['cycle']} s   ·   {o['cav']} empr.{due}")
            b = self._btn(txt, self.C_NAVY_L, font_size=17, size_hint_y=None, height=62)
            b.markup = True
            b.halign = 'left'
            b.bind(size=lambda w, sz: setattr(w, 'text_size', (sz[0] - 24, None)))
            b.bind(on_release=pick(o))
            grid.add_widget(b)
        scroll.add_widget(grid)
        box.add_widget(scroll)

        actions = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=56)
        manual = self._btn('SAISIE MANUELLE', self.C_GREY, font_size=18)
        manual.bind(on_release=lambda *a: (popup.dismiss(), setattr(self, '_queue_popup', None),
                                           self.open_of_popup(mandatory=mandatory)))
        actions.add_widget(manual)
        if not mandatory:
            cancel = self._btn('FERMER', self.C_GREY, font_size=18)
            cancel.bind(on_release=lambda *a: (popup.dismiss(), setattr(self, '_queue_popup', None)))
            actions.add_widget(cancel)
        box.add_widget(actions)
        popup.open()

    # --- File d'attente ERP ---------------------------------------------------------
    OF_QUEUE_PATH = os.path.join(os.path.dirname(SETTINGS["local_db"]["path"]), "modics_of_queue.json")

    def _queue_load(self):
        try:
            if os.path.exists(self.OF_QUEUE_PATH):
                with open(self.OF_QUEUE_PATH, encoding="utf-8") as f:
                    self.of_queue = json.load(f)
        except Exception:
            logger.exception("Chargement file OF")
            self.of_queue = []

    def _queue_save(self):
        try:
            with open(self.OF_QUEUE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.of_queue, f, ensure_ascii=False)
        except Exception:
            logger.exception("Sauvegarde file OF")

    def _queue_upsert(self, values):
        values = dict(values)
        values.setdefault('received_at', datetime.now().isoformat(timespec="seconds"))
        self.of_queue = [o for o in self.of_queue if o['so'] != values['so']] + [values]
        self._queue_save()

    def _queue_remove(self, so):
        before = len(self.of_queue)
        self.of_queue = [o for o in self.of_queue if o['so'] != so]
        if len(self.of_queue) != before:
            self._queue_save()
        return len(self.of_queue) != before

    def _refresh_open_queue_popup(self):
        """Si la liste est affichée (presse libre), la rafraîchir avec le nouveau contenu."""
        if getattr(self, '_queue_popup', None) is not None or (not self.of_active and self._of_popup is not None):
            if not self.of_active:
                self.open_next_of(mandatory=True)

    # --- API ERP (appelées depuis le thread HTTP : ne touchent pas l'écran) ----------
    def receive_of_from_erp(self, values, auto_apply=False):
        self._queue_upsert(values)
        if getattr(self, 'of_active', False):
            Clock.schedule_once(lambda dt: self._toast(
                f"OF reçu de l'ERP : {values['so']}\n{len(self.of_queue)} ordre(s) en attente — proposés à la fin de la production."))
            logger.info("OF %s reçu de l'ERP, ajouté à la file (production en cours)", values['so'])
            return "queued"
        if self._idle_planned_stop():
            logger.info("OF %s reçu de l'ERP pendant un arrêt planifié de la machine : mis en file", values['so'])
            return "queued"
        if auto_apply and self._mg_message(values) is None:     # OF hors fichier Machine Group : proposé, pas lancé seul
            def _apply(dt):
                self._close_of_popups()
                self._apply_of_and_clear(values)
                self._toast(f"OF {values['so']} lancé automatiquement depuis l'ERP")
            Clock.schedule_once(_apply)
            logger.info("OF %s reçu de l'ERP, lancement automatique", values['so'])
            return "applied"
        Clock.schedule_once(lambda dt: self.open_next_of(mandatory=True))
        logger.info("OF %s reçu de l'ERP, proposé à l'opérateur", values['so'])
        return "offered"

    def replace_queue_from_erp(self, orders):
        now = datetime.now().isoformat(timespec="seconds")
        current = {o['so'] for o in self.of_queue}
        self.of_queue = [dict(o, received_at=now) for o in orders if o['so'] != self.shopOrder or not self.of_active]
        self._queue_save()
        logger.info("File OF remplacée par l'ERP : %d ordre(s) (%d nouveaux)", len(self.of_queue),
                    len({o['so'] for o in self.of_queue} - current))
        if not getattr(self, 'of_active', False):
            Clock.schedule_once(lambda dt: self.open_next_of(mandatory=True))
            return "offered"
        Clock.schedule_once(lambda dt: self._toast(f"File ERP mise à jour : {len(self.of_queue)} ordre(s) en attente"))
        return "queued"

    def remove_from_queue_from_erp(self, so):
        removed = self._queue_remove(so)
        if removed:
            logger.info("OF %s retiré de la file par l'ERP", so)
            Clock.schedule_once(lambda dt: self._refresh_open_queue_popup())
        return removed

    def api_queue(self):
        return [{"shop_order": o['so'], "part_number": o['part'], "tool_number": o['tool'],
                 "cycle_time": o['cycle'], "cavities": o['cav'], "material_ref": o['mati'],
                 "quantity": o['quantite'], "sequence": o.get('sequence'), "due_date": o.get('due_date') or None,
                 "received_at": o.get('received_at')}
                for o in sorted(self.of_queue, key=lambda v: (v.get('sequence', 9999), v.get('received_at', '')))]

    def api_status(self):
        """Instantané pour GET /api/v1/status (lecture seule)."""
        try:
            trs = self._trs_from(self._global_stats())
        except Exception:
            trs = None
        return {
            "machine": self.machine,
            "state": self.ids.cas.text or "idle",
            "of_active": bool(getattr(self, 'of_active', False)),
            "shop_order": self.shopOrder,
            "part_number": self.ids.part1.text,
            "tool_number": self.touls,
            "cavities": self.empreint,
            "cycle_time_target": self.cycle_t,
            "quantity": self.quantitePalanifie,
            "produced": self.qtProduite,
            "good": self.qtBon,
            "rejects": self.qtRejet,
            "remaining": self.qtRestante,
            "trs_global": trs,
            "queue_length": len(self.of_queue),
            "ct_alert": bool(self.ct_alerte),
            "not_scheduled": self.ids.cas.text == self.STATE_NOT_SCHEDULED,
            "next_shop_order": self.api_queue()[0]["shop_order"] if self.of_queue else None,
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    # ------------------------------------------------------------------
    # Contrôle du temps de cycle saisi (CT) vs temps de cycle réel mesuré.
    # L'alerte est VERROUILLÉE : seule une correction de l'opérateur l'efface.
    # ------------------------------------------------------------------
    def _mg_message(self, values):
        """Part Number / outil / empreintes contre le fichier Machine Group (None si conforme ou fichier absent)."""
        mg = load_machine_group()
        if not mg:
            return None
        ref = mg.get(str(values.get('part', '')).strip())
        if ref is None:
            return "Part Number à choisir dans la liste"
        try:
            cav = int(values.get('cav'))
        except (TypeError, ValueError):
            cav = None
        if str(values.get('tool', '')).strip() != ref['tool'] or cav != ref['cav']:
            return "Outil / empreintes différents du fichier Machine Group"
        return None

    def _check_of_values(self, values):
        """Contrôle d'un OF à la saisie (popup) : Machine Group + plausibilité du CT. Renvoie un message ou None."""
        if 'part' in values:
            msg = self._mg_message(values)
            if msg:
                return msg
        ct = float(values['cycle'])
        if not (CT_MIN_S <= ct <= CT_MAX_S):
            return f"Temps de cycle hors plage ({CT_MIN_S:g} à {CT_MAX_S:g} s)"
        return None

    def _ct_check_value(self, values):
        """Contrôle de la correction : dans la plage ET cohérente avec le CT réel mesuré."""
        msg = self._check_of_values(values)
        if msg:
            return msg
        ref = self._ct_ref()
        if ref is not None and abs(ref - float(values['cycle'])) > CT_TOLERANCE_S:
            return f"Ecart avec le CT réel ({ref:.1f} s) > {CT_TOLERANCE_S:g} s"
        return None

    def _ct_ref(self):
        """CT réel de référence : médiane des derniers cycles mesurés (None si aucun cycle mesuré)."""
        pts = list(self.cycle_hist)[-5:]
        return median(pts) if pts else None

    def _ct_target_invalid(self):
        try:
            ct = float(self.cycle_t)
        except (TypeError, ValueError):
            return True
        return not (CT_MIN_S <= ct <= CT_MAX_S)

    def _ct_message(self):
        ref = self._ct_ref()
        saisi = f"{float(self.cycle_t):g}"
        if ref is None:
            return f"ALERTE CT : saisi {saisi} s - a corriger"
        return f"ALERTE CT : reel {ref:.1f} s / saisi {saisi} s"

    def _ct_save(self):
        try:
            with open(CT_ALERT_PATH, "w", encoding="utf-8") as f:
                json.dump({"shopOrder": self.shopOrder, "alerte": bool(self.ct_alerte)}, f)
        except Exception:
            logger.exception("Sauvegarde alerte CT")

    def _ct_reset(self):
        """Efface l'alerte (correction opérateur, nouvel OF ou fin d'OF)."""
        self._ct_nb_hors = 0
        if self.ct_alerte:
            self.ct_alerte = False
            self.ct_alerte_text = ''
        self._ct_save()

    def _ct_load(self):
        """Au démarrage : réarme l'alerte si elle était active sur l'OF en cours, ou si le CT restauré est invalide."""
        try:
            if not getattr(self, 'of_active', False):
                return
            latched = False
            if os.path.exists(CT_ALERT_PATH):
                with open(CT_ALERT_PATH, encoding="utf-8") as f:
                    d = json.load(f)
                latched = bool(d.get("alerte")) and d.get("shopOrder") == self.shopOrder
            if latched or self._ct_target_invalid():
                self.ct_alerte = True
                self.ct_alerte_text = self._ct_message()
                self._ct_save()
                logger.warning("ALERTE CT réarmée au démarrage (CT saisi %s s)", self.cycle_t)
                Clock.schedule_once(lambda dt: self.open_ct_correction_popup(), 2.0)
        except Exception:
            logger.exception("Chargement alerte CT")

    def _ct_trigger(self, reason):
        if self.ct_alerte:
            return
        self.ct_alerte = True
        self.ct_alerte_text = self._ct_message()
        self._ct_save()
        logger.warning("ALERTE CT (%s) : saisi %s s, réel %s s, tolérance +/-%s s",
                       reason, self.cycle_t, self._ct_ref(), CT_TOLERANCE_S)
        self.refresh_dashboard()
        Clock.schedule_once(lambda dt: self.open_ct_correction_popup(), 0.5)

    def _ct_evaluate(self, real):
        """Appelé à chaque cycle mesuré valide (le 1er cycle après arrêt/démarrage n'a pas de référence)."""
        if self.ct_alerte:
            self.ct_alerte_text = self._ct_message()    # message à jour tant que l'alerte est verrouillée
            return
        if self._ct_target_invalid():
            self._ct_trigger("CT saisi hors plage")
            return
        if abs(real - float(self.cycle_t)) > CT_TOLERANCE_S:
            self._ct_nb_hors += 1
        else:
            self._ct_nb_hors = 0
        if self._ct_nb_hors >= CT_CONFIRM_CYCLES:
            self._ct_trigger("ecart CT reel/saisi")

    def open_ct_correction_popup(self):
        if not self.ct_alerte:
            return
        p = self._ct_popup
        if p is not None and getattr(p, '_window', None) is not None:
            return                                       # déjà ouvert
        fields = [{'key': 'cycle', 'label': f'Nouveau CT ({CT_MIN_S:g}-{CT_MAX_S:g} s)', 'value': '',
                    'kind': 'float', 'max': CT_MAX_S}]
        self._ct_popup = self._form_popup('CORRIGER LE TEMPS DE CYCLE', fields, self._apply_ct_correction,
                                          mandatory=False, letters=False, check=self._ct_check_value)

    def _apply_ct_correction(self, values):
        old, new = self.cycle_t, float(values['cycle'])
        self.cycle_t = new
        self.t_c_th = new
        self._ct_reset()
        self.ids.cycle1.text = str(self.cycle) + '/' + str(self.cycle_t)
        logger.warning("CT corrigé par l'opérateur : %s -> %s s (CT réel médian %s)", old, new, self._ct_ref())
        self.refresh_dashboard()
        self.update_data()

    def _toast(self, text, seconds=5):
        """Message non bloquant qui se ferme seul."""
        lbl = Label(text=text, font_size=17, color=(1, 1, 1, 1), halign='center', valign='middle')
        lbl.bind(size=lambda w, sz: setattr(w, 'text_size', sz))
        p = Popup(title='Information ERP', title_size=16, title_color=(1, 1, 1, 1),
                  separator_color=self.C_ORANGE, separator_height=3, content=lbl,
                  size_hint=(0.6, 0.3), background_color=self.C_NAVY)
        p.open()
        Clock.schedule_once(lambda dt: p.dismiss(), seconds)

    def apply_of(self, v):
        """Lance un OF avec les valeurs du popup (remplace l'ancien submit())."""
        self.cycle_t = float(v['cycle'])
        self.cycle_hist.clear()
        self.t_c_th = self.cycle_t
        self.statu = 'in progress'
        self.shopOrder = v['so']
        self.partNumber = v['part']
        self.empreint = int(v['cav'])
        self.touls = v['tool']
        self.quantitePalanifie = int(v['quantite'])
        self.qtRestante = self.quantitePalanifie
        self.qtProduite = 0
        self.progression = 0
        self._reset_of_stats()
        self._ct_reset()
        self.ids.matiere1.text = v['mati']
        self.ids.touls1.text = f"{self.touls}({self.empreint})"
        self.ids.ShopOrder1.text = self.shopOrder
        self.ids.part1.text = self.partNumber
        self.ids.quantite1.text = str(self.quantitePalanifie)
        self.ids.qtRestante.text = str(self.quantitePalanifie)
        self.ids.progression.max = self.quantitePalanifie
        self.ids.progression.value = self.qtProduite
        self.ids.cycle1.text = str(self.t_c_th)
        self.page = 1
        self.qtBon_ajout = 0
        self.qtRejet_ajout = 0
        Clock.unschedule(self.compteur)
        self.ids.start.text = ''
        self.ids.horloge.text = ''
        self.hh = self.mm = self.ss = 0
        self.ids.Arrets.background_color = [0, 0, 1, 1]
        self.brande = 'production'
        self.temps_technicien_fin = datetime.now()
        Clock.unschedule(self.lecture_capteur)
        Clock.schedule_interval(self.lecture_capteur, POLL_DT)
        Clock.unschedule(self.controle)
        Clock.schedule_once(self.controle, self._stop_timeout())
        self.step = 1
        self.recent = 'Production'
        self.of_active = True
        self.refresh_dashboard()
        self.update_data()
        logger.info("Nouvel OF %s lancé (cycle %.1fs, %d empreintes, %d pièces)",
                    self.shopOrder, self.cycle_t, self.empreint, self.quantitePalanifie)

    # --- Saisies numériques -------------------------------------------------
    def open_number_popup(self, title, label, on_valid, hint=''):
        box = BoxLayout(orientation='vertical', spacing=10, padding=[10, 10, 10, 8])
        box.add_widget(Label(text=label, font_size=15, color=self.C_MUTED, size_hint_y=None, height=22))
        display = FormField(text='', font_size=40, halign='center', size_hint_y=None, height=64)
        box.add_widget(display)
        if hint:
            box.add_widget(Label(text=hint, font_size=13, color=self.C_MUTED, size_hint_y=None, height=20))
        error = Label(text='', color=(1, 0.55, 0.45, 1), font_size=14, size_hint_y=None, height=20)

        def on_key(k):
            error.text = ''
            if k == 'DEL':
                display.text = display.text[:-1]
            elif k == 'C':
                display.text = ''
            elif len(display.text) < 6:
                display.text += k
        box.add_widget(self._keypad(on_key, 'int'))
        box.add_widget(error)
        actions, ok, cancel = self._actions()
        box.add_widget(actions)
        popup = self._popup(title, box, (0.46, 0.95))

        def validate(*a):
            raw = display.text.strip()
            if not raw.isdigit() or int(raw) <= 0:
                error.text = 'Saisir un nombre entier > 0'
                return
            popup.dismiss()
            try:
                on_valid(int(raw))
            except Exception:
                logger.exception("Validation '%s'", title)
        ok.bind(on_release=validate)
        cancel.bind(on_release=popup.dismiss)
        popup.open()
        Clock.schedule_once(lambda dt: setattr(display, 'focus', True), 0.2)

    def _apply_rejet(self, n):
        # Invariant : Bon + Rejet = Produite ; on ne rejette pas plus que produit.
        add = max(0, min(int(n), self.qtBon))
        if add != int(n):
            logger.warning("Rejets saisis (%s) > bonnes (%s) : plafonné", n, self.qtBon)
        self.qtRejet_ajout += add
        self.qtRejet += add
        self.qtRejet_r += add
        self.qtBon -= add
        self.qtBon_r = max(0, self.qtBon_r - add)
        self.ids.qtRejet.text = str(self.qtRejet)
        self.ids.qtBon.text = str(self.qtBon)
        self.refresh_dashboard()

    def _apply_purge(self, n):
        self.qtPurge_ajout += int(n)
        self.qtPurge = self.qtPurge_ajout
        self.qtPurge_r = self.qtPurge_ajout
        self.ids.qtPurge.text = str(self.qtPurge)

    # --- Arrêt ----------------------------------------------------------------
    def _needs_declaration(self):
        """Vrai tant qu'un arrêt (en cours ou déjà terminé) n'a pas reçu de cause déclarée."""
        ongoing = (self.ids.cas.text == self.STATE_STOP
                   and self.ids.Arrets.text not in self.STOP_CAUSES
                   and not self._restart_code)
        return bool(self._decl_queue) or ongoing

    def _open_decl_popup(self):
        """Ouvre le popup OBLIGATOIRE de déclaration s'il y a un arrêt à déclarer (sans doublon)."""
        if not self._needs_declaration():
            return
        p = self._arret_popup
        if p is not None and getattr(p, '_window', None) is not None:
            return
        self.open_arret_popup(mandatory=True)

    def _declare_pending(self, cat):
        """Applique la cause choisie à TOUS les arrêts en attente de déclaration :
        segments déjà terminés (la presse a redémarré avant la déclaration) + arrêt en cours.
        Le début de l'arrêt reste la vraie date d'arrêt : le délai avant déclaration est inclus."""
        planned = (cat == self.PLANNED_CODE)
        queue, self._decl_queue = self._decl_queue, []
        for seg in queue:
            self.stop_insert_extern(self.machine, self._fmt(seg['end']), self.shopOrder, cat,
                                    self._fmt(seg['start']), self._fmt(seg['end']), self.pilote, seg['shift'])
            if planned:      # bascule hors TRS du temps déjà compté en arrêt
                moved = int(round((seg['end'] - seg['start']).total_seconds()))
                moved = max(0, min(moved, int(self.stop)))
                self.stop -= moved
                self.stop_planned += moved
        self.email_receiver = self.STOP_MAIL.get(cat, [])
        ongoing = (self.ids.cas.text == self.STATE_STOP and self.ids.Arrets.text not in self.STOP_CAUSES)
        if ongoing:
            self.ids.Arrets.text = cat
            self.Btn()                      # arrêt toujours en cours : suite habituelle (END STOP, mail)
        elif queue and not planned:
            self.code = cat
            self.send_problem_mail()
        logger.info("Arrêt(s) déclaré(s) : %s (%d segment(s) terminé(s), en cours: %s)", cat, len(queue), ongoing)

    AUTO_STOP_CAUSE = 'Production'      # cause déclarée automatiquement si la presse reprend avant déclaration

    def _auto_declare_pending(self):
        """Déclare automatiquement (cause « Production ») les arrêts terminés restés sans cause. Pas d'e-mail."""
        queue, self._decl_queue = self._decl_queue, []
        for seg in queue:
            self.stop_insert_extern(self.machine, self._fmt(seg['end']), self.shopOrder, self.AUTO_STOP_CAUSE,
                                    self._fmt(seg['start']), self._fmt(seg['end']), self.pilote, seg['shift'])
        if queue:
            logger.info("%d arrêt(s) en attente déclaré(s) automatiquement : %s", len(queue), self.AUTO_STOP_CAUSE)

    def _close_decl_popup(self):
        """Ferme la fenêtre « DÉCLARER UN ARRÊT » si elle est ouverte."""
        p, self._arret_popup = self._arret_popup, None
        if p is not None:
            try:
                p.dismiss()
            except Exception:
                logger.exception("Fermeture du popup de déclaration")

    def open_arret_popup(self, mandatory=False):
        box = BoxLayout(orientation='vertical', spacing=8, padding=10)
        msg = ('Arrêt détecté — déclarez la cause pour continuer' if mandatory
               else 'Sélectionnez la catégorie de l’arrêt')
        box.add_widget(Label(text=msg, font_size=15, color=(1, 0.75, 0.45, 1) if mandatory else self.C_MUTED,
                             size_hint_y=None, height=24))
        cats = list(self.STOP_CAUSES)
        popup = self._popup('DÉCLARER UN ARRÊT', box, (0.55, 0.97))
        self._arret_popup = popup

        def choose(btn):
            popup.dismiss()
            self._arret_popup = None
            if mandatory or self._decl_queue:
                self._declare_pending(btn.text)
            else:
                self.ids.Arrets.text = btn.text
                self.Btn()
            Clock.schedule_once(lambda dt: self._open_decl_popup(), 0.3)

        for c in cats:
            b = self._btn(c, self.C_PLANNED if c == self.PLANNED_CODE else self.C_AMBER, font_size=20)
            b.bind(on_release=choose)
            box.add_widget(b)
        if not mandatory:
            cancel = self._btn('ANNULER', self.C_GREY, font_size=18, size_hint_y=None, height=56)

            def _cancel(*a):
                popup.dismiss()
                self._arret_popup = None
                Clock.schedule_once(lambda dt: self._open_decl_popup(), 0.2)
            cancel.bind(on_release=_cancel)
            box.add_widget(cancel)
        popup.open()

    # --- Empreintes ---------------------------------------------------------------
    def open_empreintes_popup(self):
        box = BoxLayout(orientation='vertical', spacing=10, padding=10)
        box.add_widget(Label(text='Empreintes actives sur le moule', font_size=15, color=self.C_MUTED,
                             size_hint_y=None, height=24))
        val = Label(text=str(self.empreint), font_size=64, bold=True, color=(1, 1, 1, 1))
        row = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=76)
        minus = self._btn('–', self.C_RED, font_size=40)
        plus = self._btn('+', self.C_GREEN, font_size=40)
        row.add_widget(minus)
        row.add_widget(plus)
        box.add_widget(val)
        box.add_widget(row)
        actions, ok, cancel = self._actions()
        box.add_widget(actions)
        popup = self._popup('EMPREINTES', box, (0.42, 0.78))
        minus.bind(on_release=lambda *a: setattr(val, 'text', str(max(1, int(val.text) - 1))))
        plus.bind(on_release=lambda *a: setattr(val, 'text', str(int(val.text) + 1)))

        def validate(*a):
            self.empreint = int(val.text)
            self.ids.touls1.text = f"{self.touls}({self.empreint})"
            popup.dismiss()
        ok.bind(on_release=validate)
        cancel.bind(on_release=popup.dismiss)
        popup.open()

    # --- Extinction ---------------------------------------------------------------
    def popup_power(self):
        box = BoxLayout(orientation='vertical', spacing=12, padding=12)
        box.add_widget(Label(text='Éteindre le Raspberry Pi ?\nLes données en cours sont sauvegardées.',
                             font_size=17, color=(1, 1, 1, 1), halign='center'))
        actions, ok, cancel = self._actions(ok_text='ÉTEINDRE')
        ok.background_color = self.C_RED
        box.add_widget(actions)
        popup = self._popup('EXTINCTION', box, (0.5, 0.5))
        ok.bind(on_release=lambda *a: (self.update_data(), self.power_off()))
        cancel.bind(on_release=popup.dismiss)
        popup.open()

    def tick_chrono(self, dt):
        """Chrono du cycle en cours (temps écoulé depuis le dernier front).
        Blanc : dans la cible. Orange : cible dépassée. Rouge : arrêt imminent (> 80 % du timeout)."""
        try:
            if self.t1 and self.ids.cas.text == 'Production':
                elapsed = time.time() - self.t1
                if elapsed < 3600:
                    self.ids.chrono.text = f"{elapsed:.1f} s"
                    if elapsed > 0.8 * self._stop_timeout():
                        self.ids.chrono.color = (0.95, 0.35, 0.35, 1)
                    elif self.cycle_t and elapsed > float(self.cycle_t):
                        self.ids.chrono.color = (0.93, 0.63, 0.18, 1)
                    else:
                        self.ids.chrono.color = (1, 1, 1, 1)
                    return
            self.ids.chrono.text = "--.- s"
            self.ids.chrono.color = (0.72, 0.76, 0.82, 1)
        except Exception:
            pass

    def start_app(self,dt): 
        try: 
            
            self.shift = OEECalculator.get_shift(self.now)
            self.pilote = 'NONE'
            self.fin_arret_mach_off=datetime.now()
            self.stop_insert_extern(self.machine,self.debut_arret_mach_off.strftime("%e/%m/%G %H:%M:%S"),self.shopOrder,'Machine OFF',self.debut_arret.strftime("%e/%m/%G  %H:%M:%S"),self.debut_arret_mach_off.strftime("%e/%m/%G  %H:%M:%S"),self.pilote,self.shift)
            Clock.schedule_interval(self.time,1/80.)
            Clock.schedule_interval(self.auto_save, 15)   # persistance de l'état (press.db)
            Clock.schedule_once(self.start_comptage,5) 
            self.debut_arret=datetime.now()
            hostname = socket.gethostname()
            logger.info("Nom de la machine Raspberry Pi : %s", hostname)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 0))  # ne fait pas réellement de trafic (UDP), sert juste à connaître l'IP locale
            ipAddress = s.getsockname()[0]
            s.close()
            logger.info("Adresse IP locale détectée : %s", ipAddress)
            try:
                ext = self.db.external_conn(timeout=5)
                cursor = ext.cursor()
                cursor.execute(
                    "UPDATE IP_Address_Table_Machines_Mould SET IP_address_Mould_63 = %s", (ipAddress,)
                )
                ext.commit()
                ext.close()
            except Exception:
                logger.exception("Echec mise à jour de l'adresse IP sur MODICS")
            self.recent = 'Production'
            if getattr(self, 'of_active', False):
                Clock.schedule_interval(self.lecture_capteur, POLL_DT)
                if self.ids.Arrets.text != 'Signaler un Arrêt':
                    self.code=self.ids.Arrets.text
                else:
                    self.code=''
            else:
                self.code=''
        
        except Exception:
            logger.exception("Echec dans start_app")
        
    def send_problem_mail(self):
        email_sender = SETTINGS["email"]["sender"]
        email_receiver = self.email_receiver
        
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Machine 63 : STOP CASE !!'
        msg['From'] = email_sender
        msg['To'] = ", ".join(email_receiver)  # Join multiple recipients properly
        
            # Texte brut pour les clients email simples
        text = f"""\
        ALERTE - PROBLÈME DÉTECTÉ SUR MACHINE {str(self.machine)}
        
        Bonjour,
        
        Nous avons détecté un problème sur la machine {str(self.machine)}.
        
        Type de problème: Mauvaise utilisation/déclaration manquante
        Statut: Requiert une intervention immédiate
        
        Cet email est généré automatiquement - merci de ne pas répondre directement.
        """
        
        # HTML pour un rendu visuel amélioré
        html = f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #d9534f; color: white; padding: 15px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ padding: 20px; background-color: #f9f9f9; border-left: 1px solid #ddd; border-right: 1px solid #ddd; }}
                .footer {{ padding: 10px; text-align: center; font-size: 12px; color: #777; background-color: #eee; border-radius: 0 0 5px 5px; border-left: 1px solid #ddd; border-right: 1px solid #ddd; border-bottom: 1px solid #ddd; }}
                .alert-box {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 15px 0; }}
                .machine-info {{ background-color: #e7f5fe; padding: 10px; border-radius: 4px; margin-bottom: 15px; }}
                .btn {{ background-color: #d9534f; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px; display: inline-block; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>ALERTE - PROBLÈME {str(self.machine)}</h2>
            </div>
            
            <div class="content">
                <p>Bonjour,</p>
                
                <div class="alert-box">
                    <strong>Une anomalie a été détectée nécessitant votre attention immédiate.</strong>
                </div>
                
                <div class="machine-info">
                    <h3>Détails du problème :</h3>
                    <p><strong>Machine concernée :</strong> {str(self.machine)}</p>
                    <p><strong>Type de problème :</strong> {str(self.code)}</p>
                    <p><strong>Niveau d'urgence :</strong> <span style="color: #d9534f;">Élevé</span></p>
                </div>
                
                <p>Nous vous recommandons d'intervenir rapidement pour investiguer et résoudre ce problème afin d'éviter tout impact sur la production.</p>
                
                <p style="text-align: center;">
                    <a href="#" class="btn">Marquer comme traité</a>
                </p>
            </div>
            
            <div class="footer">
                <p>Cet email a été généré automatiquement - merci de ne pas y répondre directement.</p>
                <p>© 2025 Mould Operation Data Intelligente Collection System</p>
            </div>
        </body>
        </html>
        """
        
        # Record the MIME types of both parts
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        # Attach parts into message container
        msg.attach(part1)
        msg.attach(part2)

        Notifier.send_async(msg, email_receiver)
    def auto_save(self, dt):
        """Persistance périodique : l'heure ici sert aussi de 'dernier instant vivant'
        pour dater la période Machine OFF au prochain démarrage."""
        self.debut_arret_mach_off = datetime.now()
        self._save_period_shift()
        self.update_data()
            
    def bleu(self,dt):
        self.ids.Arrets.background_color=(0,0,1,1)
        Clock.unschedule(self.bleu)
        Clock.schedule_once(self.rouge,1)
    def rouge(self,dt):
        self.ids.Arrets.background_color=(1,0,0,1)
        Clock.unschedule(self.rouge)
        Clock.schedule_once(self.bleu,1)    
    def start_comptage(self,dt):
        Clock.schedule_interval(self.time_prod,1)  
    def daily_report(self, shift=None):
        shift = shift or self._period_shift
        try:
            
            self.run_hrs= round(self.run/60,2)
            self.stop_hrs= round(self.stop/60,2)
            if self.term!=0:
                cycle_mm= round(self.cycle_moy/self.term,2)
            else:
                cycle_mm = 0  
            mam= datetime.now()
            date = mam.strftime("%Y-%m-%d %H:%M:%S")
            if self.run_hrs != 0 and self.qtBon_r != 0:
                self.perfermance = round((self.cycle_t*self.term)/(self.run_hrs*60),2)
                self.avaibility = round(self.run_hrs /(self.run_hrs+self.stop_hrs),2)
                self.quality = round(self.qtBon_r/(self.qtBon_r+self.qtRejet_r),2)
                self.OEE =  round(self.perfermance * self.avaibility * self.quality,2)
                if self.ct_alerte:
                    logger.warning("Bilan %s : CT en alerte (saisi %s s) -> Performance/OEE non fiables, enregistrés à 0",
                                   self.shift, self.cycle_t)
                    self.perfermance = 0
                    self.OEE = 0
            else:
                self.perfermance = 0
                self.avaibility =0
                self.quality = 0
                self.OEE = 0    
            self.daily_insert(self.machine,date,self.run_hrs,self.stop_hrs,self.qtBon_r,self.qtRejet_r,cycle_mm,self.avaibility,self.perfermance,self.quality,self.OEE,shift,self.partNumber or self.ids.part1.text)          
            self._accumulate_current_window(shift)
            logger.info("Bilan %s : run %.1f min | arrêts non planifiés %.1f min | non planifié (hors TRS) %.1f min",
                        shift, self.run / 60.0, self.stop / 60.0, self.stop_planned / 60.0)
            self.stop_planned = 0
            self.run=0
            self.stop=0
            self.qtBon_r=0
            self.qtRejet_r=0
            self.cycle_moy=0
            self.term=0
        except Exception:
            logger.exception("Echec dans daily_report")
    def compteur(self,dt):
        try:              
            self.ss=self.ss+1
            if self.ss == 60:
                self.mm+=1
                self.ss=0
            elif self.mm == 60:
                self.mm=0
                self.hh+=1
            self.ids.horloge.text= 'Temps Arrêt = '+str(self.hh)+':'+str(self.mm)+':'+str(self.ss)                     
            
        except Exception:
            logger.exception("Echec dans compteur")
    def time_prod(self,dt):  
      
        state = self.ids.cas.text
        if state == self.STATE_RUN:
            self.run += 1
        elif state == self.STATE_NOT_SCHEDULED:
            self.stop_planned += 1      # hors TRS : n'entre pas dans Down
        else:
            self.stop += 1
     
    def time(self,dt):
        self.now=datetime.now()
        mama = self.now.strftime("%H:%M")
        
                          
        new_shift = OEECalculator.get_shift(self.now)
        if new_shift != self._period_shift:
            self._close_shift_period(new_shift)
         
             
       
            
           
        self.ids.qtProduite.text= str(self.qtProduite)
        self.ids.quantite1.text = str(self.quantitePalanifie) 
        self.ids.qtBon.text= str(self.qtBon)
        self.ids.qtRejet.text = str(self.qtRejet)
        self.ids.qtRestante.text = str(self.qtRestante)
          
        if time.time() - self.last_backend_send < self.backend_interval:
            return

        payload = {
                "machine": 'PRS 63',
                "temps":str(mama),
                "Etat": self.etat,
                "shopordre":self.shopOrder,
                "quantite_planifier": self.quantitePalanifie,
                "quantite_produite": self.qtProduite,
                "debut_shop":str(self.debut_arret),
                "quantite_rejet":self.qtRejet,
                "cycle_time":self.cycle,
                "TRS":self.TRS,
                "cycle_time_th":self.cycle_t,
                "temps_prod":self.run,
                "temps_arret":self.stop,
                "raison_arret": self.code
        }
        # try:
        #     response = requests.post(BACKEND_URL, json=payload, timeout=5)
        #     self.last_backend_send = time.time()
        #     print(f"Data sent successfully? Status Code: {response.status_code}")
        # except requests.exceptions.ConnectionError:
        #     print("Connection failed: Could not reach the backend listener.")
        # except requests.exceptions.RequestException as e:
        #     print(f"Data sending failed: {e}")

    def _window_run_to_stop(self, now):
        """[dernière impulsion -> now] : la presse était déjà à l'arrêt mais ce temps était
        compté en Run (cas = 'Production'). On le bascule en Arrêt pour que
        Down = somme des durées du Stop Log."""
        try:
            delta = int(round((now - self.debut_arret).total_seconds()))
        except Exception:
            return
        delta = max(0, min(delta, int(self.run)))
        self.run -= delta
        self.stop += delta

    def controle(self,dt):
        self.shift = OEECalculator.get_shift(self.now)
        # automationhat.relay.one.on()
        self.code = ''                       # cause inconnue : l'opérateur DOIT la déclarer
        self._auto_stop_code = None
        self._stop_origin = 'timeout'
        self._restart_code = ''
        Clock.schedule_once(self.bleu,1)
        now=datetime.now()
        # Pas d'insertion ici : une SEULE ligne [dernière impulsion -> reprise] est écrite par active().
        # debut_arret reste la date de la dernière impulsion (début réel de l'arrêt).
        self._window_run_to_stop(now)
        self.etat = '0'
        self.ids.cas.text='Arrêt'
        self.ids.start.text='Début = ' + str(now.strftime("%G/%m/%e  %H:%M:%S"))
        self.ids.Arrets.background_color= [1,0,0,1]
        self.ids.cas.color= [1,0,0,1]
        Clock.schedule_interval(self.compteur,1)
        self.CodeArret = ''
        self.brande = 'production'
        Clock.unschedule(self.controle)
        self.step = 1
        self._open_decl_popup()              # popup obligatoire : pas de passage sans déclaration
    ##################################################################
        # fonction de lire des entrés de donnés
    ###################################################################
   
    def popup_valid(self):
        box = BoxLayout(orientation = 'vertical', padding = (10))
        box.add_widget(Label(text ='Bonne journée !    '+self.pilote,font_size=25,color= [1,0,0,1]))
        btn11 = Button(text = "OK",size_hint=[1,0.2])
        box.add_widget(btn11)
        popup = Popup(title=self.Machine, title_size= (30), 
                    title_align = 'center', content = box,
                    size_hint=(None, None),size=(600,300),
                    auto_dismiss = False)
        btn11.bind(on_press = popup.dismiss) 
        popup.open()    
    def popup_1_FR(self):
        box = BoxLayout(orientation = 'vertical', padding = (10))
        box.add_widget(Label(text ='    Données invalide',font_size=25,color= [1,0,0,1]))
        btn11 = Button(text = "OK",size_hint=[1,0.2])
        box.add_widget(btn11)
        

        popup = Popup(title='Press Machine', title_size= (30), 
                    title_align = 'center', content = box,
                    size_hint=(None, None),background_color= [1,0,0,1],size=(600,300),
                    auto_dismiss = False)
        btn11.bind(on_press = popup.dismiss) 
        popup.open()    
    
        
    def popup_3_FR(self):
        box = BoxLayout(orientation = 'vertical', padding = (10))
        box.add_widget(Label(text = 'Vous êtes sure ??',font_size=20))
        btn1 = Button(text = "OUI",size_hint=[1,1])
        btn2 = Button(text = "NON",size_hint=[1,1])
        box.add_widget(btn1)
        box.add_widget(btn2)

        popup = Popup(title='Press Machine', title_size= (30), 
                      title_align = 'center', content = box,
                      size_hint=(None, None),size=(400,200),
                      auto_dismiss = False)
        btn1.bind(on_press = self.dismiss,on_release = popup.dismiss)
        btn2.bind(on_press = popup.dismiss)
        popup.open()
    def reglage_mode(self):
        box = BoxLayout(orientation = 'vertical', padding = (10))
        box.add_widget(Label(text ='STOP CODE : '+self.ids.Arrets.text,font_size=31,color= [1,0,0,1],bold=True))
        btn11 = Button(text = 'END STOP',font_size=30,size_hint=[1,0.2])
        box.add_widget(btn11)
        popup = Popup(title=self.machine, title_size= (30), 
                    title_align = 'center', content = box,
                    size_hint=(None, None),background_color= [1,0,0,1],size=(600,300),
                    auto_dismiss = False)
        btn11.bind(on_press = self.react ,on_release = popup.dismiss) 
        popup.open()
    def react(self,event):
        """Fin d'un arrêt déclaré (bouton END STOP)."""
        if self._idle_planned_stop():
            self._end_idle_planned_stop()
            return
        self.shift = OEECalculator.get_shift(self.now)
        Clock.unschedule(self.bleu)
        Clock.unschedule(self.rouge)
        now = datetime.now()
        if self.ids.cas.text in (self.STATE_STOP, self.STATE_NOT_SCHEDULED):
            self.fin_arret = now
            code = self._current_stop_code()
            if code:
                self.stop_insert_extern(self.machine, self._fmt(now), self.shopOrder, code,
                                        self._fmt(self.debut_arret), self._fmt(now), self.pilote, self.shift)
            self.debut_arret = now
            # la presse n'a pas encore redémarré : la même cause court jusqu'au prochain cycle
            self._restart_code = code
            self.code = code
            self._auto_stop_code = None
            planned = (code == self.PLANNED_CODE)
            self.ids.cas.text = self.STATE_NOT_SCHEDULED if planned else self.STATE_STOP
            self.ids.cas.color = list(self.C_PLANNED) if planned else [1, 0, 0, 1]
            self.ids.Arrets.background_color = list(self.C_PLANNED) if planned else [1, 0, 0, 1]
        self.ids.Arrets.text = 'Signaler un Arrêt'
        Clock.unschedule(self.lecture_capteur)
        Clock.schedule_interval(self.lecture_capteur, POLL_DT)

    def dismiss(self,event):
        self.shift = OEECalculator.get_shift(self.now)
        # Bilan de fin d'OF : DOIT être calculé maintenant, avec les valeurs encore en place
        # (cycle_t, part number, compteurs). L'ancien schedule_once(day_data, 5) s'exécutait
        # APRÈS initialisation_var() -> cycle_t valait 1 -> performance ~0 et Part_Number vide.
        self.daily_report()
        self.code=self._current_stop_code() or self._restart_code
        self._auto_stop_code = None
        self._restart_code = ''
        self.fin_arret=datetime.now()
        if self.code and self.ids.cas.text in (self.STATE_STOP, self.STATE_NOT_SCHEDULED):
            self.stop_insert_extern(self.machine,self.fin_arret.strftime("%e/%m/%G %H:%M:%S"),self.shopOrder,self.code,self.debut_arret.strftime("%e/%m/%G  %H:%M:%S"),self.fin_arret.strftime("%e/%m/%G  %H:%M:%S"),self.pilote,self.shift)
        self.statu='closed'
        self.of_active = False
        self.ids.managerScreen.current='Production'
        self.recent = 'Production'
        self.end = time.time()
        self.duree = (self.end - self.start)
        self.start = time.time()  
        self.step =0
        self.duree = 3600
        Clock.unschedule(self.controle)
        self.debut_arret = datetime.now()
        Clock.unschedule(self.lecture_capteur)
        Clock.unschedule(self.compteur)
        self.ids.start.text=''
        self.ids.horloge.text=''
        self.hh=self.mm=self.ss=0
        self.ids.cas.size_hint = [1,1]            
        self.ids.Arrets.background_color= [0,0,1,1]
        self.ids.cas.color=[0,0,1,1]
        self.ids.cas.text=''
        self.ids.Arrets.text= 'Signaler un Arrêt'
        self.etat = '0'
        self.initialisation_var()
        self.refresh_dashboard()
        self.update_data()
        Clock.schedule_once(lambda dt: self.open_next_of(mandatory=True), 0.3)
    def Btn_select_arret(self):
        self.open_arret_popup(mandatory=self._needs_declaration())
       
    
    def Btn(self):
        """Déclaration d'une cause d'arrêt par l'opérateur."""
        self.shift = OEECalculator.get_shift(self.now)
        value = self.ids.Arrets.text
        if value not in self.STOP_CAUSES:
            return
        planned = (value == self.PLANNED_CODE)
        was_running = (self.ids.cas.text == self.STATE_RUN)
        now = datetime.now()
        Clock.unschedule(self.bleu)
        Clock.unschedule(self.rouge)
        Clock.unschedule(self.controle)
        if was_running:
            self.debut_arret = now          # l'arrêt commence maintenant (plus de ligne parasite)
        elif planned:
            # arrêt déjà en cours (auto) puis déclaré planifié : toute la période depuis
            # le début de l'arrêt bascule de "Stop" vers "hors TRS"
            moved = int(round((now - self.debut_arret).total_seconds()))
            moved = max(0, min(moved, int(self.stop)))
            self.stop -= moved
            self.stop_planned += moved
        # sinon : on garde debut_arret -> l'arrêt entier est attribué à la cause déclarée
        self.code = self.CodeArret = value
        self._auto_stop_code = None
        self.email_receiver = self.STOP_MAIL.get(value, [])
        self.brande = 'matière' if value == 'Mécanique' else 'production'
        self.hh = self.mm = self.ss = 0
        Clock.unschedule(self.compteur)
        self.ids.horloge.text = ''
        self.ids.start.text = 'Début = ' + self._fmt(now)
        Clock.schedule_interval(self.compteur, 1)
        self.ids.cas.text = self.STATE_NOT_SCHEDULED if planned else self.STATE_STOP
        self.ids.cas.color = list(self.C_PLANNED) if planned else [1, 0, 0, 1]
        self.ids.Arrets.background_color = list(self.C_PLANNED) if planned else [1, 0, 0, 1]
        self.etat = '0'
        self.reglage_mode()
        self.ids.managerScreen.current = 'Production'
        if not planned:
            self.send_problem_mail()

    def active(self):
        self.shift = OEECalculator.get_shift(self.now)
        stopped = self.ids.cas.text in (self.STATE_STOP, self.STATE_NOT_SCHEDULED)
        auto_declared = False                # arrêt resté sans cause, déclaré automatiquement à la reprise
        if stopped or self.ids.Arrets.text not in ('Signaler un Arrêt', 'Signaler un arrêt'):
            self.code = self._current_stop_code() or self._restart_code   # cause déclarée > cause reportée
            if stopped:
                now = datetime.now()
                self.fin_arret = now
                if not self.code:
                    # redémarrage AVANT déclaration : la cause « Production » est déclarée automatiquement
                    # (début = vraie date d'arrêt), sans popup ni e-mail
                    self.code = self.AUTO_STOP_CAUSE
                    auto_declared = True
                    logger.info("Arrêt terminé sans déclaration : cause « %s » déclarée automatiquement (%s -> %s)",
                                self.AUTO_STOP_CAUSE, self._fmt(self.debut_arret), self._fmt(now))
                self.stop_insert_extern(self.machine, self._fmt(now), self.shopOrder, self.code,
                                        self._fmt(self.debut_arret), self._fmt(now), self.pilote, self.shift)
            self.ids.Arrets.text = 'Signaler un Arrêt'
            self.CodeArret = ''
            self._auto_stop_code = None
            self._restart_code = ''
            self.code = ''
        Clock.unschedule(self.controle)
        self.ids.start.text=''
        self.ids.cas.text='Production'
        self.ids.cas.color=[0,1,0,1]
        Clock.unschedule(self.compteur)
        self.ids.horloge.text=''
        self.hh=0
        self.mm=0
        self.ss=0
        self.ids.Arrets.background_color= [0,0,1,1]
        self.etat = '1'
        # segments restés sans cause (ex. arrêt coupé par un changement de shift) : même déclaration automatique
        if self._decl_queue:
            self._auto_declare_pending()
            auto_declared = True
        if auto_declared:
            self._close_decl_popup()     # la presse a repris : plus de popup, retour à l'écran de production

    # ------------------------------------------------------------------
    # États et causes d'arrêt
    #   Production   : machine en production
    #   Arrêt        : arrêt NON planifié -> compté dans le TRS (Down)
    #   Non planifié : arrêt planifié     -> HORS TRS (ni Run ni Down)
    # ------------------------------------------------------------------
    STATE_RUN = 'Production'
    STATE_STOP = 'Arrêt'
    STATE_NOT_SCHEDULED = 'Non planifié'
    PLANNED_CODE = 'Arrêt planifié'
    STOP_CAUSES = ('Maintenance', 'Mécanique', 'Qualité', 'Process', 'Production', PLANNED_CODE)
    C_PLANNED = (0.30, 0.52, 0.85, 1)
    STOP_MAIL = {
        'Maintenance': ['mohamed.aliayari@bulgin.com', 'marwen.rahal@bulgin.com', 'maroi.chikhaoui@bulgin.com'],
        'Mécanique':   ['mohamed.aliayari@bulgin.com', 'marwen.rahal@bulgin.com', 'makrem.benmansour@bulgin.com'],
        'Qualité':     ['mohamed.aliayari@bulgin.com', 'marwen.rahal@bulgin.com', 'ibrahim.layouni@bulgin.com'],
        'Process':     ['mohamed.aliayari@bulgin.com', 'marwen.rahal@bulgin.com', 'ibrahim.layouni@bulgin.com'],
        'Production':  ['mohamed.aliayari@bulgin.com', 'marwen.rahal@bulgin.com', 'ibrahim.layouni@bulgin.com'],
    }   # Arrêt planifié : aucun email (arrêt voulu)
    PERIOD_PATH = os.path.join(os.path.dirname(SETTINGS["local_db"]["path"]), "modics_period.json")

    @staticmethod
    def _fmt(dt):
        return dt.strftime("%d/%m/%Y %H:%M:%S")

    def _load_period_shift(self):
        """Shift auquel appartiennent les compteurs en cours (survit à un redémarrage du Pi)."""
        try:
            with open(self.PERIOD_PATH, encoding="utf-8") as f:
                sh = json.load(f).get("shift")
            if sh in self.SHIFTS:
                return sh
        except Exception:
            pass
        return OEECalculator.get_shift(datetime.now())

    def _save_period_shift(self):
        try:
            with open(self.PERIOD_PATH, "w", encoding="utf-8") as f:
                json.dump({"shift": self._period_shift}, f)
        except Exception:
            logger.exception("Sauvegarde du shift en cours")

    def _current_stop_code(self):
        """Code de l'arrêt en cours : cause déclarée > code automatique > texte du bouton > ''."""
        txt = self.ids.Arrets.text
        if txt in self.STOP_CAUSES:
            return txt
        if self._auto_stop_code:
            return self._auto_stop_code
        return '' if txt in ('Signaler un Arrêt', 'Signaler un arrêt') else txt

    def _close_shift_period(self, new_shift):
        """Changement de shift : bilan IMMEDIAT, étiqueté avec le shift qui SE TERMINE
        (et non avec l'heure courante, ni avec self.shift qui est réécrit à chaque cycle)."""
        closing = self._period_shift
        self._period_shift = new_shift
        self.shift = new_shift
        self._save_period_shift()
        self.daily_report(shift=closing)
        if self.ids.cas.text in (self.STATE_STOP, self.STATE_NOT_SCHEDULED):
            now = datetime.now()
            code = self._current_stop_code() or self._restart_code
            if code:
                self.stop_insert_extern(self.machine, self._fmt(now), self.shopOrder, code,
                                        self._fmt(self.debut_arret), self._fmt(now), self.pilote, closing)
            else:   # arrêt non encore déclaré : segment mis en attente, étiqueté avec le shift qui se termine
                self._decl_queue.append({'start': self.debut_arret, 'end': now, 'shift': closing})
            self.debut_arret = now
        logger.info("Changement de shift : %s -> %s", closing, new_shift)

    STOP_SIGNAL_CODE = 'Arrêt machine'

    def _stop_timeout(self):
        """Délai sans impulsion au-delà duquel on passe en Arrêt non déclaré."""
        ct = float(self.cycle_t or 0)
        return max(STOP_TIMEOUT_MIN, min(STOP_TIMEOUT_MAX, ct * STOP_TIMEOUT_FACTOR))

    def _enter_stop_from_signal(self):
        """Passage en mode Arrêt déclenché par l'entrée STOP_INPUT (même mécanique que controle())."""
        if self.ids.cas.text != 'Production':
            return  # pas en production (déjà en arrêt, ou aucun OF actif)
        self.shift = OEECalculator.get_shift(self.now)
        self.code = ''                       # cause à déclarer par l'opérateur
        self._auto_stop_code = None
        self._stop_origin = 'signal'
        self._restart_code = ''
        now = datetime.now()
        # une seule ligne [dernière impulsion -> reprise] sera écrite par active()
        self._window_run_to_stop(now)
        self.etat = '0'
        self.ids.cas.text = 'Arrêt'
        self.ids.cas.color = [1, 0, 0, 1]
        self.ids.start.text = 'Début = ' + now.strftime("%G/%m/%e  %H:%M:%S")
        self.ids.Arrets.background_color = [1, 0, 0, 1]
        Clock.unschedule(self.compteur)
        Clock.schedule_interval(self.compteur, 1)
        Clock.unschedule(self.controle)
        Clock.schedule_once(self.bleu, 1)
        self.CodeArret = ''
        logger.info("Arrêt déclenché par signal (entrée %d)", STOP_INPUT)
        self._open_decl_popup()

    def _show_reject_mode(self, active):
        try:
            self.ids.rejets_l.text = 'SIGNAL REBUT' if active else 'Rejets'
            self.ids.rejets_l.color = (0.82, 0.24, 0.24, 1) if active else (0.45, 0.48, 0.52, 1)
        except Exception:
            pass
        logger.info("Mode rebut %s (entrée %d)", "ACTIVÉ" if active else "désactivé", REJECT_INPUT)

    def lecture_capteur(self, dt):
        """
        Une seule lecture matérielle par tick (POLL_HZ). Le détecteur valide
        les fronts (anti-rebond) ; le front configuré (CYCLE_EDGE) déclenche
        _on_cycle() qui calcule toutes les sorties.
        """
        now = time.time()
        try:
            capteur_on = read_input(CYCLE_INPUT)
            stop_on = read_input(STOP_INPUT)
            rejet_on = read_input(REJECT_INPUT)
        except Exception:
            logger.exception("Lecture entrées Automation HAT")
            return

        # --- input arrêt : front montant -> mode Arrêt ; retour OFF -> fin d'arrêt
        if stop_on is not None:
            ev = self.detector_stop.feed(stop_on, now)
            if ev == 'rising':
                self._enter_stop_from_signal()
            elif (ev == 'falling' and self._stop_origin == 'signal'
                  and self.ids.cas.text == self.STATE_STOP and self.ids.Arrets.text not in self.STOP_CAUSES):
                self._stop_origin = None
                self.active()

        # --- input rebut : niveau -> les cycles comptent en Rejets
        ev_rej = None
        if rejet_on is not None:
            ev_rej = self.detector_rejet.feed(rejet_on, now)
            mode = bool(self.detector_rejet.state)
            if mode != self.reject_mode:
                self.reject_mode = mode
                self._show_reject_mode(mode)
            if ev_rej == 'falling':
                self._late_rej_used = False

        # --- input cycle
        event = self.detector.feed(capteur_on, now)
        if event == CYCLE_EDGE:
            self._on_cycle(now)

        # --- signal rebut arrivé APRÈS l'impulsion de cycle -> requalifie la dernière pièce
        #     (traité après le cycle : si les deux tombent dans le même tick, le cycle
        #      a déjà été compté en rejet directement et n'est plus requalifiable)
        if ev_rej == 'rising':
            self._reject_late(now)

        # rafraîchissement écran pendant l'impulsion (comportement historique)
        if capteur_on:
            self.ids.step.background_color = [0, 1, 0, 1]
            self.ids.qtProduite.text = str(self.qtProduite)
            self.ids.quantite1.text = str(self.quantitePalanifie)
            self.ids.qtBon.text = str(self.qtBon)
            self.ids.qtRejet.text = str(self.qtRejet)
            self.ids.qtRestante.text = str(self.qtRestante)
            self.ids.cycle1.text = str(self.cycle) + '/' + str(self.cycle_t)
            if self.qtProduite <= self.quantitePalanifie:
                self.ids.progression.value = self.qtProduite
                self.ids.progression.max = self.quantitePalanifie

    def _reject_late(self, now):
        """Signal rebut reçu après l'impulsion de cycle : la pièce du dernier cycle,
        déjà comptée en Bonnes, passe en Rejets (Bon + Rejet = Produite conservé)."""
        window = REJECT_LATE_WINDOW if REJECT_LATE_WINDOW > 0 else float(self.cycle_t or 0)
        if not self._last_cycle_good or self._last_cycle_qty <= 0:
            return
        if window <= 0 or (now - self._last_cycle_t) > window:
            return
        n = min(self._last_cycle_qty, self.qtBon)
        self.qtBon -= n
        self.qtBon_r = max(0, self.qtBon_r - n)
        self.qtRejet += n
        self.qtRejet_r += n
        self.qtRejet_ajout += n
        self._last_cycle_good = False      # un seul rattrapage par cycle
        self._late_rej_used = True         # le niveau rebut encore actif ne touchera pas le cycle suivant
        self.ids.qtBon.text = str(self.qtBon)
        self.ids.qtRejet.text = str(self.qtRejet)
        logger.info("Rebut tardif (%.2fs après le cycle) : %d pièce(s) Bonne -> Rejet", now - self._last_cycle_t, n)
        self.refresh_dashboard()

    def _on_cycle(self, now):
        """Calcul des sorties à chaque cycle validé (logique métier inchangée)."""
        Clock.unschedule(self.controle)
        was_stopped = (self.ids.cas.text != 'Production')
        self.active()

        # --- temps de cycle : front à front. Pas de référence valide au 1er cycle
        #     après (re)démarrage ou après un arrêt -> on prend la cible (plafonnement
        #     historique), et on n'envoie pas de point aberrant dans la courbe.
        raw = (now - self.t1) if (self.t1 and not was_stopped) else None
        self.t1 = now
        self.term += 1
        cycle = round(raw, 2) if raw is not None else float(self.cycle_t)
        self.cycle_raw = cycle                      # valeur réelle (courbe / diagnostic)
        if cycle > (self.cycle_t + 10):
            cycle = float(self.cycle_t)             # plafonnement historique (bilan MODICS)
        self.cycle = round(cycle, 2)
        self.cycle_moy += self.cycle
        self.cycle_status = 'OK' if abs(self.cycle_raw - self.cycle_t) <= 2 else 'NOK'
        logger.debug("Cycle #%d : %.2fs (%s) | ON %.2fs / OFF %.2fs", self.term, self.cycle_raw,
                     self.cycle_status, self.detector.on_duration, self.detector.off_duration)

        # --- compteurs (une impulsion = une injection = `empreint` pièces)
        #     signal rebut actif -> les pièces vont en Rejets, sinon en Bonnes
        self.qtProduite += self.empreint
        self._last_cycle_t = now
        self._last_cycle_qty = self.empreint
        if self.reject_mode and not self._late_rej_used:
            self.qtRejet += self.empreint
            self.qtRejet_r += self.empreint
            self.qtRejet_ajout += self.empreint
            self.ids.qtRejet.text = str(self.qtRejet)
            self._last_cycle_good = False
        else:
            self.qtBon += self.empreint
            self.qtBon_r += self.empreint
            self._last_cycle_good = True      # requalifiable si le signal rebut arrive juste après
        self.qtRestante = max(0, self.quantitePalanifie - self.qtProduite)

        # --- état machine / surveillance d'arrêt
        self.etat = '1'
        self.debut_arret = datetime.now()
        Clock.schedule_once(self.controle, self._stop_timeout())

        # --- TRS instantané (comme avant) + composantes live
        if self.cycle != 0 and self.qtBon != 0 and self.run != 0 and self.cycle_t != 0 and not self.ct_alerte:
            Tp = round((self.cycle_t / self.cycle), 2)
            Tq = round(self.qtBon / (self.qtBon + self.qtRejet), 2)
            Ta = round(self.run / (self.run + self.stop), 2)
            self.TRS = round((Tp * Ta * Tq) * 100, 2)
            self.Ta_live, self.Tp_live, self.Tq_live = Ta, Tp, Tq
        else:
            self.TRS = 0
            self.Ta_live = self.Tp_live = self.Tq_live = 0

        # --- dashboard : la courbe montre la valeur réelle, pas la valeur plafonnée
        if raw is not None:
            self.cycle_hist.append(round(self.cycle_raw, 2))
            self._ct_evaluate(self.cycle_raw)
        self.refresh_dashboard()
        self.update_data()

    ######################################################################
    #initialisation
    ######################################################################
    def initialisation_var(self): 
        self.cycle = 0
        self.cycle_t = 1
        self._ct_reset()
        self.t1=0
        self.t2=0
        self.qtRejet_ajout=0
        self.qtBon_ajout = 0
        self.ids.qtProduite.text ='0'
        self.ids.qtBon.text ='0'
        self.ids.qtRejet.text ='0'
        self.quantitePalanifie = 0  
        self.qtRestante=0
        self.qtProduite=0
        self.qtRejet=0
        self.qtBon=0
        self.shopOrder =''
        self.touls =''
        self.progression =0
        self.ids.ShopOrder1.text=''
        self.ids.part1.text=''
        self.ids.touls1.text=''
        self.ids.quantite1.text=''
        self.ids.qtRestante.text='0'
        self.ids.progression.value=0
       
    ###################################################################   
    # Acceuil Screen 
    ###################################################################
        
   
    def Btn_fin_shopOrder(self):
        # if self.ids.lang.text == 'ENG':
        #     self.popup_3_ENG()
        # else:
        self.popup_3_FR()    
                
    def Btn_ajout_rejet(self):
        self.open_number_popup('QUANTITÉ DE REJETS', 'Rejets à ajouter', self._apply_rejet)
    def Btn_ajout_purge(self):
        self.open_number_popup('QUANTITÉ PURGÉE (g)', 'Purge à ajouter (g)', self._apply_purge)
    def Btn_ferme_emp(self):
        self.open_empreintes_popup()

    def update_data(self):
        try:
            cur = conn.cursor()
            etat = (self.shopOrder,self.ids.part1.text,self.touls,self.quantitePalanifie,self.qtRestante,self.ids.progression.value,self.qtProduite,self.qtBon,self.qtRejet,self.cycle_t,self.qtBon_r,self.qtRejet_r,self.run,self.stop,self.ids.managerScreen.current,self.ids.Arrets.text, self.ids.start.text,self.ids.horloge.text,self.hh,self.mm,self.ss,self.debut_arret,self.ids.cas.text,self.code,self.cycle_moy,self.term,self.id_insert_d,self.id_insert_h,self.id_insert_s,self.debut_arret_mach_off,self.ids.matiere1.text,self.empreint,self.pilote ,1)
            
            cur.execute("update restore set shoporder=?,Part_Number=?, touls=?,quantitePalanifie=?,qtRestante=?,progression=?,qtProduite=?,qtBon=?,qtRejet=?,cycle_t=?,qtBon_r=?,qtRejet_r=?,run_hrs=?,stop_hrs=?,managerScreen=?,Arrets=?,start=?,horloge=? ,hh=?,mm=?,ss=?,start_arret=?,etat=?,code=?,cycle_moy=?,term=?,id_d=?,id_h=?,id_s=?,OFF_time=?,matiere=?,cavity=?,pilote=? where id=?", etat)
            
            conn.commit()
        except Exception:
            logger.exception("Echec update_data (sauvegarde état local press.db)")
    @staticmethod
    def _parse_dt(value, default=None):
        """
        Parse une date stockée dans press.db. Certaines lignes n'ont pas
        de microsecondes (format SQLite variable selon comment la valeur
        a été insérée) : l'ancien code plantait sur strptime si le format
        ne correspondait pas exactement. On essaie les deux formats.
        """
        for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(value, fmt)
            except (ValueError, TypeError):
                continue
        logger.warning("Date illisible en base ('%s'), valeur par défaut utilisée", value)
        return default or datetime.now()

    def resume(self):
        """Restaure l'état de la dernière session depuis press.db."""
        try:
            self._resume_from_db()
        except Exception:
            logger.exception("Echec resume() - état local illisible, redémarrage à zéro")
            self.initialisation_var()

    def _resume_from_db(self):
        cur = conn.cursor()
        cur.execute("SELECT * FROM restore WHERE id = 1")
        data = cur.fetchall()
        self.ids.ShopOrder1.text = self.shopOrder = data[0][1]
        self.ids.part1.text=data[0][2]
        self.partNumber = data[0][2]
        self.empreint = data[0][32]
        self.touls = data[0][3]
        self.ids.touls1.text =  str(self.touls )+'('+str(self.empreint)+')'
        self.quantitePalanifie = data[0][4]
        self.qtRestante = data[0][5]
        self.ids.progression.value = data[0][6]
        self.qtProduite = data[0][7]
        self.qtBon =  data[0][8]
        self.qtRejet = data[0][9]
        self.cycle_t = data[0][10]
        self.qtBon_r = data[0][11]
        self.qtRejet_r = data[0][12]
        self.run = data[0][13]
        self.stop = data[0][14]
        self.debut_arret = self._parse_dt(data[0][22])
        self.ids.cas.text=data[0][23]
        self.pilote=data[0][33]
        self.code=data[0][24]
        self.cycle_moy=data[0][25]
        self.term=data[0][26]
        self.id_insert_d=data[0][27]
        self.id_insert_h=data[0][28]
        self.id_insert_s=data[0][29]
        self.debut_arret_mach_off = self._parse_dt(data[0][30])
        self.ids.matiere1.text = data[0][31]
        self.of_active = (data[0][15] == 'Production') and bool(self.shopOrder)
        self.ids.managerScreen.current = 'Production'
        self.recent = 'Production'
        self.ids.Arrets.text = data[0][16]
        self.ids.quantite1.text = str(self.quantitePalanifie)
        self.ids.qtRestante.text = str(self.qtRestante)
        self.ids.qtProduite.text = str(self.qtProduite)
        self.ids.qtBon.text = str(self.qtBon)
        self.ids.qtRejet.text = str(self.qtRejet)
        self.ids.cycle1.text = str(self.cycle) + '/' + str(self.cycle_t)
        self.ids.progression.max = max(1, self.quantitePalanifie or 1)
        self.ids.progression.value = min(self.qtProduite, self.ids.progression.max)

        if not self.of_active:
            # aucun OF actif : rien à reprendre, l'écran reste neutre
            self.ids.cas.text = ''
            self.ids.Arrets.text = 'Signaler un Arrêt'
            self.etat = '0'
            return

        if self.ids.Arrets.text != 'Signaler un Arrêt':
            # on était en arrêt : reprise du chrono d'arrêt
            self.etat = '0'
            self.ids.Arrets.background_color = [1, 0, 0, 1]
            self.ids.start.text = data[0][17]
            self.ids.horloge.text = data[0][18]
            planned = (self.ids.Arrets.text == self.PLANNED_CODE)
            self.ids.cas.text = self.STATE_NOT_SCHEDULED if planned else self.STATE_STOP
            self.ids.cas.color = list(self.C_PLANNED) if planned else [1, 0, 0, 1]
            self.ids.Arrets.background_color = list(self.C_PLANNED) if planned else [1, 0, 0, 1]
            self.hh, self.mm, self.ss = data[0][19], data[0][20], data[0][21]
            Clock.unschedule(self.compteur)
            Clock.schedule_interval(self.compteur, 1)
            Clock.unschedule(self.controle)
        else:
            # on était en production : surveillance d'arrêt réarmée
            self.etat = '1'
            self.ids.cas.text = 'Production'
            self.ids.cas.color = [0, 1, 0, 1]
            self.ids.Arrets.background_color = [0, 0, 1, 1]
            Clock.unschedule(self.controle)
            Clock.schedule_once(self.controle, self._stop_timeout())
                             
    def cycle_insert(self, machine, date_d, part, cycle, status):
        """
        NOTE : fonction non utilisée ailleurs dans le code actuel (aucun
        appel trouvé). Conservée telle quelle au cas où elle serait
        rebranchée plus tard, mais elle n'insère que dans le buffer local
        et n'est jamais synchronisée vers MODICS - à vérifier avant usage.
        """
        self.db.insert_local(
            '''INSERT INTO Machine_Cycle_Mould
               (Machine_Name_Mould, Date_Insert_Mould, Part_Number, Cycle_Time, status)
               VALUES (%s, %s, %s, %s, %s)''',
            (machine, date_d, part, cycle, status),
            context="cycle_insert",
        )

    def daily_insert(self, machine, date_d, run_hrs_d, stop_hrs_d, qtBon_d, qtRejet_d,
                      cycle_mm_d, avaibility_d, perfermance_d, quality_d, OEE_d, shift, part):
        """
        Ecrit le bilan du shift dans le buffer local MySQL (rapide,
        synchrone : ne doit jamais échouer silencieusement) puis déclenche
        la synchro vers MODICS en tâche de fond (réseau = potentiellement
        lent, ne doit jamais bloquer la lecture du capteur).
        """
        ok = self.db.insert_local(
            '''INSERT INTO Machine_Daily_Table_Mould
               (Machine_Name_Mould, Date_Insert_Day_Mould, Run_Hours_Day_Mould, Down_Hours_Day_Mould,
                Good_QTY_Day_Mould, Rejects_QTY_Day_Mould, Cycle_Time_Day, Availability_Rate_Day_Mould,
                Performance_Rate_Day_Mould, Quality_Rate_Day_Mould, OEE_Day_Mould, Shift_Mould, Part_Number_Mould)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (machine, date_d, run_hrs_d, stop_hrs_d, qtBon_d, qtRejet_d, cycle_mm_d,
             avaibility_d, perfermance_d, quality_d, OEE_d, shift, part),
            context="daily_insert",
        )
        if ok:
            self.db.sync_daily_async()

    def stop_insert_extern(self, machine, date, shoporder, code, debut, fin, pilote, shift):
        """
        Ecrit un arrêt dans le buffer local (synchrone) puis synchronise
        vers MODICS en tâche de fond. Voir daily_insert() pour le principe.
        """
        ok = self.db.insert_local(
            '''INSERT INTO Machine_Stop_Table_Mould
               (Machine_Name_Mould, Date_Insert_Mould, Part_NO_Mould, Code_Stop_Mould,
                Debut_Stop_Mould, Fin_Stop_Time_Mould, Regleur_Prenom_Mould, Shift)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
            (machine, date, shoporder, code, debut, fin, pilote, shift),
            context="stop_insert_extern",
        )
        if ok:
            self.db.sync_stops_async()

    ##################################################################
    # Class Main
    ##################################################################            
class Mould(App):

    def build(self):
        application = Manager()
        return application
    def on_pause(self):
        return True

if __name__ == '__main__':
    Mould().run()