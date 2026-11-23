# -*- coding: utf-8 -*-
"""
Ajoute la fonction « HORS PLANNING » au terminal MODICS (moul.py, Raspberry Pi).

    python3 apply_hors_planning.py /home/pi/Downloads/moul.py

- Après la fin d'une production (fenêtre « nouvel OF » ou liste des OF ERP), un bouton HORS PLANNING
  (avec confirmation) met la presse hors planning. Un écran plein format « MACHINE HORS PLANNING »
  reste affiché avec le bouton « REMETTRE EN PLANNING / NOUVEL OF ». L'état survit à un redémarrage
  (modics_out_of_plan.json, à côté de press.db).
- L'API /api/v1/status publie out_of_plan (bool) et out_of_plan_s (secondes) : le serveur web affiche
  alors une carte spéciale « Hors planning ».
- Un OF poussé par l'ERP remet automatiquement la presse en planning.
- Hors planning, le temps n'est compté ni en Run ni en Arrêt (time_prod).

Sûr : vérifie que chaque point d'ancrage existe UNE fois et que le résultat compile (sinon rien n'est écrit),
puis écrit après avoir sauvegardé moul.py.bak-AAAAMMJJ-HHMMSS.
Idempotent : sans effet si le correctif est déjà appliqué.
"""
import os
import shutil
import sys
import time

MARK = "# ---- HORS_PLANNING_BEGIN"

NEW_METHODS = '''    # ---- HORS_PLANNING_BEGIN -------------------------------------------------
    # Presse hors planning : plus aucun OF prévu après la fin de production. Persistant (survit à un redémarrage),
    # publié par l'API (/api/v1/status) pour l'affichage web, levé par l'opérateur ou par un OF poussé par l'ERP.
    OUT_OF_PLAN_PATH = os.path.join(os.path.dirname(SETTINGS["local_db"]["path"]), "modics_out_of_plan.json")

    def _load_out_of_plan(self):
        self.out_of_plan = False
        self.out_of_plan_since = None
        self._oop_popup = None
        try:
            if os.path.exists(self.OUT_OF_PLAN_PATH):
                with open(self.OUT_OF_PLAN_PATH, encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("active") and not getattr(self, 'of_active', False):
                    self.out_of_plan = True
                    self.out_of_plan_since = float(d.get("since") or time.time())
                    logger.info("Presse hors planning (état restauré)")
        except Exception:
            logger.exception("Chargement état hors planning")

    def _save_out_of_plan(self):
        try:
            with open(self.OUT_OF_PLAN_PATH, "w", encoding="utf-8") as f:
                json.dump({"active": bool(self.out_of_plan), "since": self.out_of_plan_since}, f)
        except Exception:
            logger.exception("Sauvegarde état hors planning")

    def confirm_out_of_plan(self):
        """Confirmation avant de mettre la presse hors planning (évite un appui accidentel)."""
        box = BoxLayout(orientation='vertical', spacing=12, padding=14)
        box.add_widget(Label(text=f"Mettre {self.machine} HORS PLANNING ?\\n\\nAucun OF n'est prévu : la presse sera signalée\\n"
                                  "« Hors planning » sur l'affichage web.",
                             font_size=18, color=(1, 1, 1, 1), halign='center'))
        actions, ok, cancel = self._actions(ok_text='OUI, HORS PLANNING')
        box.add_widget(actions)
        popup = self._popup('HORS PLANNING', box, (0.7, 0.62))
        ok.bind(on_release=lambda *a: (popup.dismiss(), self.enter_out_of_plan()))
        # annuler = retour à la saisie de l'OF (la fenêtre obligatoire avait été fermée pour afficher la confirmation)
        cancel.bind(on_release=lambda *a: (popup.dismiss(), self.open_next_of(mandatory=True)))
        popup.open()

    def enter_out_of_plan(self):
        if getattr(self, 'of_active', False):
            return                                  # jamais pendant une production
        self._close_of_popups()
        self.out_of_plan = True
        self.out_of_plan_since = time.time()
        self._save_out_of_plan()
        logger.info("Presse mise HORS PLANNING par l'opérateur")
        Clock.schedule_once(lambda dt: self.open_out_of_plan_popup(), 0.2)

    def leave_out_of_plan(self, reason):
        if not getattr(self, 'out_of_plan', False):
            return
        self.out_of_plan = False
        self.out_of_plan_since = None
        self._save_out_of_plan()
        p = self._oop_popup
        self._oop_popup = None
        if p is not None:
            try:
                p.dismiss()
            except Exception:
                pass
        logger.info("Presse remise en planning (%s)", reason)

    def open_out_of_plan_popup(self):
        """Écran plein format tant que la presse est hors planning."""
        p = self._oop_popup
        if p is not None and getattr(p, '_window', None) is not None:
            return                                  # déjà affiché
        since = datetime.fromtimestamp(self.out_of_plan_since or time.time()).strftime("%d/%m %H:%M")
        box = BoxLayout(orientation='vertical', spacing=14, padding=18)
        box.add_widget(Label(text='MACHINE HORS PLANNING', font_size=38, bold=True, color=self.C_AMBER))
        box.add_widget(Label(text=f"Aucun ordre de fabrication prévu — depuis {since}\\n"
                                  "Signalée « Hors planning » sur l'affichage web.",
                             font_size=18, color=(1, 1, 1, 1), halign='center'))
        resume = self._btn('REMETTRE EN PLANNING / NOUVEL OF', self.C_GREEN, font_size=22, size_hint_y=None, height=84)
        resume.bind(on_release=lambda *a: self._resume_from_out_of_plan())
        box.add_widget(resume)
        off = self._btn('ÉTEINDRE LE RASPBERRY PI', self.C_GREY, font_size=15, size_hint_y=None, height=44)
        off.bind(on_release=lambda *a: self.popup_power())
        box.add_widget(off)
        popup = self._popup(f"{self.machine} — HORS PLANNING", box, (0.9, 0.82))
        self._oop_popup = popup
        popup.open()

    def _resume_from_out_of_plan(self):
        self.leave_out_of_plan("opérateur")
        Clock.schedule_once(lambda dt: self.open_next_of(mandatory=True), 0.2)
    # ---- HORS_PLANNING_END ---------------------------------------------------

'''

# (ancre, remplacement) : chaque ancre doit exister exactement une fois
EDITS = [
    # 1. chargement de l'état au démarrage (avant la planification de la fenêtre obligatoire à 1 s)
    ('''        self._queue_popup = None
        self._queue_load()
''',
     '''        self._queue_popup = None
        self._queue_load()
        self._load_out_of_plan()
'''),
    # 2. nouvelles méthodes + garde dans open_next_of
    ('''    def open_next_of(self, mandatory=True):
        """Point d'entrée unique quand il faut un nouvel OF : liste ERP si elle existe, sinon saisie."""
        if self.of_queue:
''',
     NEW_METHODS + '''    def open_next_of(self, mandatory=True):
        """Point d'entrée unique quand il faut un nouvel OF : liste ERP si elle existe, sinon saisie."""
        if getattr(self, 'out_of_plan', False) and not getattr(self, 'of_active', False):
            self.open_out_of_plan_popup()           # hors planning : écran dédié au lieu de la saisie obligatoire
            return
        if self.of_queue:
'''),
    # 3. bouton dans la liste des OF ERP
    ('''        actions.add_widget(manual)
        if not mandatory:
''',
     '''        actions.add_widget(manual)
        if mandatory:
            oop = self._btn('HORS PLANNING', self.C_AMBER, font_size=18)
            oop.bind(on_release=lambda *a: (popup.dismiss(), setattr(self, '_queue_popup', None), self.confirm_out_of_plan()))
            actions.add_widget(oop)
        if not mandatory:
'''),
    # 4. bouton dans la fenêtre de saisie de l'OF
    ('''    def _form_popup(self, title, fields, on_valid, mandatory=False, letters=True, check=None,
                    suggest=None, on_edit=None):
''',
     '''    def _form_popup(self, title, fields, on_valid, mandatory=False, letters=True, check=None,
                    suggest=None, on_edit=None, out_of_plan=False):
'''),
    ('''        actions, ok, cancel = self._actions(cancel=not mandatory)
        right.add_widget(actions)
''',
     '''        actions, ok, cancel = self._actions(cancel=not mandatory)
        if out_of_plan:
            oop = self._btn('HORS PLANNING', self.C_AMBER, font_size=16)
            oop.bind(on_release=lambda *a: (popup.dismiss(), self.confirm_out_of_plan()))
            actions.add_widget(oop)
        right.add_widget(actions)
'''),
    ('''        self._of_popup = self._form_popup(title, fields, self._apply_of_and_clear,
                                          mandatory=mandatory, letters=True,
                                          check=self._check_of_values, **suggest_args)
''',
     '''        self._of_popup = self._form_popup(title, fields, self._apply_of_and_clear,
                                          mandatory=mandatory, letters=True,
                                          check=self._check_of_values,
                                          out_of_plan=(mandatory and not prefill), **suggest_args)
'''),
    # 5. un OF poussé par l'ERP remet la presse en planning (sur le thread Kivy)
    ('''        self._queue_upsert(values)
        if getattr(self, 'of_active', False):
''',
     '''        self._queue_upsert(values)
        if getattr(self, 'out_of_plan', False):
            Clock.schedule_once(lambda dt: self.leave_out_of_plan("OF reçu de l'ERP"))
        if getattr(self, 'of_active', False):
'''),
    ('''        logger.info("File OF remplacée par l'ERP : %d ordre(s) (%d nouveaux)", len(self.of_queue),
''',
     '''        if self.of_queue and getattr(self, 'out_of_plan', False):
            Clock.schedule_once(lambda dt: self.leave_out_of_plan("file reçue de l'ERP"))
        logger.info("File OF remplacée par l'ERP : %d ordre(s) (%d nouveaux)", len(self.of_queue),
'''),
    # 6. publié par l'API : l'affichage web en déduit l'état « Hors planning »
    ('''            "next_shop_order": self.api_queue()[0]["shop_order"] if self.of_queue else None,
''',
     '''            "next_shop_order": self.api_queue()[0]["shop_order"] if self.of_queue else None,
            "out_of_plan": bool(getattr(self, 'out_of_plan', False)),
            "out_of_plan_s": (int(time.time() - self.out_of_plan_since)
                              if getattr(self, 'out_of_plan', False) and self.out_of_plan_since else None),
'''),
    # 7. hors planning : ni Run ni Arrêt
    ('''        state = self.ids.cas.text
        if state == self.STATE_RUN:
            self.run += 1
''',
     '''        if getattr(self, 'out_of_plan', False):
            return                                  # hors planning : temps compté ni en Run ni en Arrêt
        state = self.ids.cas.text
        if state == self.STATE_RUN:
            self.run += 1
'''),
]


def patch(text):
    for i, (anchor, _) in enumerate(EDITS, 1):
        n = text.count(anchor)
        if n != 1:
            raise SystemExit(f"Point d'ancrage n°{i} trouvé {n} fois (attendu 1) — fichier différent de la version attendue, "
                             f"rien n'a été modifié.\n--- ancre ---\n{anchor}")
    for anchor, repl in EDITS:
        text = text.replace(anchor, repl, 1)
    return text


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage : python3 apply_hors_planning.py /chemin/vers/moul.py")
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
        compile(new, path, "exec")      # syntaxe vérifiée AVANT d'écrire : en cas d'erreur le fichier reste intact
    except SyntaxError as e:
        raise SystemExit(f"Erreur de syntaxe après correctif, rien n'a été modifié : {e}")
    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(("﻿" if bom else "") + (new.replace("\n", "\r\n") if crlf else new))
    print(f"OK — {len(EDITS)} modifications appliquées. Sauvegarde : {backup}")
    print("Redémarrer le terminal (moul.py) pour activer la fonction.")


if __name__ == "__main__":
    main()
