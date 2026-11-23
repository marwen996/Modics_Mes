# -*- coding: utf-8 -*-
"""
Ajoute les routes d'action à l'API du terminal MODICS (moul.py, Raspberry Pi).

    python3 apply_actions_api.py /home/pi/Downloads/moul.py

L'app mobile MODICS envoie POST /api/v1/action/<nom> pour piloter la presse à distance :

    reject      {qty: N}             → ajoute N rejets à la production
    purge       {qty: N}             → ajoute N g de purge
    cycle-time  {cycle: N}          → corrige le temps de cycle cible (secondes)
    declare-stop {cause: "..."}     → déclare la cause d'un arrêt
    end-stop    {}                  → termine l'arrêt en cours
    finish      {}                  → termine l'OF (bilan + retour à la sélection)
    launch      {shop_order: "..."}→ lance un OF présent dans la file ERP

Toutes ces actions sont planifiées via Clock.schedule_once pour la thread-safety Kivy.
L'API renvoie 202 si l'action est acceptée, 400/404/409 en cas d'erreur de validation.

Sûr et idempotent : vérifie les ancres, compile avant d'écrire, crée une sauvegarde.
"""
import os
import shutil
import sys
import time

MARK = "# ---- ACTIONS_API_BEGIN"

# ---- Méthode api_action ajoutée au Manager ------------------------------------
NEW_API_ACTION = '''
    # ---- ACTIONS_API_BEGIN ----------------------------------------------------
    STOP_CAUSES = ['Maintenance', 'Mécanique', 'Qualité', 'Process', 'Production']

    def api_action(self, name, payload):
        """Actions à distance : POST /api/v1/action/<name>.
        Appelée depuis le thread HTTP ; toutes les opérations Kivy passent par
        Clock.schedule_once. Renvoie (dict_réponse, code_HTTP)."""
        if name == "reject":
            try:
                qty = int(payload.get("qty") or 0)
                if qty <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return {"error": "qty doit être un entier > 0"}, 400
            if not getattr(self, 'of_active', False):
                return {"error": "aucun OF actif"}, 409
            Clock.schedule_once(lambda dt: self._apply_rejet(qty))
            return {"accepted": True, "qty": qty}, 202

        if name == "purge":
            try:
                qty = int(payload.get("qty") or 0)
                if qty <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return {"error": "qty doit être un entier > 0"}, 400
            Clock.schedule_once(lambda dt: self._apply_purge(qty))
            return {"accepted": True, "qty": qty}, 202

        if name == "cycle-time":
            try:
                cycle = float(payload.get("cycle") or 0)
                if cycle <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return {"error": "cycle doit être un nombre > 0"}, 400
            def _update_ct(dt, _c=cycle):
                self.cycle_t = _c
                self.t_c_th = _c
                try:
                    self.ids.cycle1.text = str(_c)
                except Exception:
                    pass
                self.refresh_dashboard()
            Clock.schedule_once(_update_ct)
            return {"accepted": True, "cycle": cycle}, 202

        if name == "declare-stop":
            cause = str(payload.get("cause") or "").strip()
            if not cause:
                return {"error": "cause est requise"}, 400
            def _do_declare(dt, _cause=cause):
                self.shift = OEECalculator.get_shift(self.now)
                self.fin_arret = datetime.now()
                self.stop_insert_extern(
                    self.machine,
                    self.fin_arret.strftime("%e/%m/%G %H:%M:%S"),
                    self.shopOrder,
                    self.code,
                    self.debut_arret.strftime("%e/%m/%G  %H:%M:%S"),
                    self.fin_arret.strftime("%e/%m/%G  %H:%M:%S"),
                    self.pilote, self.shift)
                self.code = _cause
                self.CodeArret = _cause
                self.debut_arret = datetime.now()
                try:
                    self.ids.Arrets.text = _cause
                    self.ids.Arrets.background_color = [1, 0, 0, 1]
                    self.ids.cas.color = [1, 0, 0, 1]
                    self.ids.cas.text = 'Arrêt'
                except Exception:
                    pass
            Clock.schedule_once(_do_declare)
            return {"accepted": True, "cause": cause}, 202

        if name == "end-stop":
            Clock.schedule_once(lambda dt: self.react(None))
            return {"accepted": True}, 202

        if name == "finish":
            if not getattr(self, 'of_active', False):
                return {"error": "aucun OF actif"}, 409
            Clock.schedule_once(lambda dt: self.dismiss(None))
            return {"accepted": True}, 202

        if name == "launch":
            shop_order = str(payload.get("shop_order") or "").strip()
            if not shop_order:
                return {"error": "shop_order est requis"}, 400
            if getattr(self, 'of_active', False):
                return {"error": "un OF est déjà actif"}, 409
            of = next((o for o in list(self.of_queue) if o.get('so') == shop_order), None)
            if of is None:
                return {"error": f"OF {shop_order} non trouvé dans la file",
                        "queue": [o.get('so') for o in self.of_queue]}, 404
            Clock.schedule_once(lambda dt: self._apply_of_and_clear(of))
            return {"accepted": True, "shop_order": shop_order}, 202

        return {"error": f"action inconnue : {name}"}, 404
    # ---- ACTIONS_API_END -------------------------------------------------------

'''

EDITS = [
    # 1. Ajouter stop_code et stop_causes au retour de api_status()
    # Ancre sur "time": la dernière clé du dict — robuste même si apply_hors_planning.py a déjà
    # ajouté out_of_plan / out_of_plan_s entre next_shop_order et time.
    (
        '            "time": datetime.now().isoformat(timespec="seconds"),\n'
        '        }\n',
        '            "stop_code": self.code if self.ids.cas.text in (\'Arrêt\', \'Arret\') else None,\n'
        '            "stop_causes": [\'Maintenance\', \'Mécanique\', \'Qualité\', \'Process\', \'Production\'],\n'
        '            "time": datetime.now().isoformat(timespec="seconds"),\n'
        '        }\n',
    ),
    # 2. Ajouter la méthode api_action avant _toast
    (
        '    def _toast(self, text, seconds=5):\n',
        NEW_API_ACTION + '    def _toast(self, text, seconds=5):\n',
    ),
    # 3. Ajouter la route action dans do_POST avant la réponse 404 finale
    (
        '        self._send(404, {"error": "not found"})\n'
        '\n'
        '    # --- DELETE ----------------------------------------------------------------\n',
        '        from urllib.parse import unquote as _unq\n'
        '        _pfx = "/api/v1/action/"\n'
        '        if self.path.startswith(_pfx):\n'
        '            _res, _c = self.server.manager.api_action(_unq(self.path[len(_pfx):]), payload)\n'
        '            return self._send(_c, _res)\n'
        '        self._send(404, {"error": "not found"})\n'
        '\n'
        '    # --- DELETE ----------------------------------------------------------------\n',
    ),
]


def patch(text):
    for i, (anchor, _) in enumerate(EDITS, 1):
        n = text.count(anchor)
        if n != 1:
            raise SystemExit(
                f"Point d'ancrage n°{i} trouvé {n} fois (attendu 1) — "
                f"fichier différent de la version attendue, rien n'a été modifié.\n"
                f"--- ancre ---\n{anchor}"
            )
    for anchor, repl in EDITS:
        text = text.replace(anchor, repl, 1)
    return text


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage : python3 apply_actions_api.py /chemin/vers/moul.py")
    path = sys.argv[1]
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    bom = raw.startswith("﻿")
    crlf = "\r\n" in raw
    text = raw.lstrip("﻿").replace("\r\n", "\n")
    if MARK in text:
        print("Correctif déjà appliqué : aucune modification.")
        return
    new = patch(text)
    try:
        compile(new, path, "exec")
    except SyntaxError as e:
        raise SystemExit(f"Erreur de syntaxe après correctif, rien n'a été modifié : {e}")
    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(("﻿" if bom else "") + (new.replace("\n", "\r\n") if crlf else new))
    print(f"OK — {len(EDITS)} modifications appliquées. Sauvegarde : {backup}")
    print("Redémarrer moul.py sur le Pi pour activer les actions distantes.")


if __name__ == "__main__":
    main()
