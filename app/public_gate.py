"""
Barrière d'accès pour le trafic venant d'Internet (tunnel Cloudflare).

Une requête qui passe par Cloudflare porte toujours l'en-tête Cf-Ray / Cf-Connecting-Ip (le client ne peut pas les
retirer). Celles-là exigent un identifiant et un mot de passe (authentification HTTP Basic) ; l'accès depuis le
réseau de l'atelier (TV, postes internes) reste direct, sans mot de passe.

  MODICS_PUBLIC_USER, MODICS_PUBLIC_PASSWORD : identifiants (obligatoires). S'ils manquent, l'accès Internet est refusé (503).

Anti force brute : au-delà de MAX_FAILS échecs en WINDOW secondes pour une même IP, elle est bloquée (429).
"""
import hmac
import os
import time
from collections import defaultdict, deque

from flask import Response, request

MAX_FAILS, WINDOW = 8, 600
_fails = defaultdict(deque)


def _via_internet():
    return "Cf-Ray" in request.headers or "Cf-Connecting-Ip" in request.headers


def _same(a, b):
    return hmac.compare_digest((a or "").encode("utf-8"), b.encode("utf-8"))


def install(app):
    @app.before_request
    def _gate():
        if not _via_internet():
            return None
        user = os.environ.get("MODICS_PUBLIC_USER", "")
        password = os.environ.get("MODICS_PUBLIC_PASSWORD", "")
        if not user or not password:
            return Response("Accès public non configuré", 503)
        ip = request.headers.get("Cf-Connecting-Ip") or request.remote_addr
        now, fails = time.time(), _fails[ip]
        while fails and now - fails[0] > WINDOW:
            fails.popleft()
        if len(fails) >= MAX_FAILS:
            return Response("Trop de tentatives, réessayez plus tard", 429, {"Retry-After": str(WINDOW)})
        auth = request.authorization
        if auth and _same(auth.username, user) & _same(auth.password, password):
            _fails.pop(ip, None)
            return None
        if auth:
            fails.append(now)
        return Response("Authentification requise", 401, {"WWW-Authenticate": 'Basic realm="MODICS", charset="UTF-8"'})
