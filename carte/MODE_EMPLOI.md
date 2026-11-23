# Mode d'emploi — Carte MODICS (terminal Raspberry Pi d'une presse)

Ce guide a deux publics : les **opérateurs et régleurs** (partie A : utiliser l'écran de la presse) et les
**administrateurs / électroniciens** (partie B : installer, configurer, dépanner). Pour les tableaux de bord
web, voir [`../app/MODE_EMPLOI.md`](../app/MODE_EMPLOI.md).

---

# Partie A — Opérateurs et régleurs

## 1. À quoi sert l'écran

L'écran tactile de la presse (800 × 480) **compte les cycles automatiquement** grâce au capteur du noyau et
vous demande seulement ce que la machine ne peut pas savoir : quel ordre de fabrication (OF) tourne, pourquoi la
presse s'est arrêtée, combien de pièces sont mauvaises. Ces informations alimentent le TRS et les tableaux de bord.

## 2. Lire l'écran de production

| Zone | Ce que vous voyez |
|---|---|
| **Bandeau du haut** | État (**Production** en vert ou **Arrêt**), heure de début, **chrono du cycle en cours**, bouton **OFF** |
| **Bande d'informations** | Shop Order · Part Number · Outil (empreintes) · Référence matière · Cycle cible |
| **Jauge TRS** (à gauche) | TRS global de l'OF, et le TRS de chaque équipe (Shift A, B, C) |
| **Compteurs** | **Produite** · **Bonnes** (vert) · **Rejets** (rouge) · **Purge (g)** |
| **Courbe** | Temps de cycle des 30 derniers cycles ; la cible est en pointillés |
| **Avancement** | Quantité **restante**, quantité **planifiée** et barre de progression |
| **Boutons du bas** | `+ Rejet` · `+ Purge` · `Empreintes` · `Signaler un Arrêt` · `Fin de production` |

**Couleur du chrono** : blanc = le cycle est dans la cible · **orange** = la cible est dépassée ·
**rouge** = un arrêt va être détecté (plus de 80 % du délai d'arrêt).

**Équipes** : Shift A 06:00–14:00 · Shift B 14:00–22:00 · Shift C 22:00–06:00. Le changement se fait tout seul.

## 3. Lancer un ordre de fabrication

Une fenêtre **NOUVEL ORDRE DE FABRICATION** s'ouvre quand la presse n'a pas d'OF.

**Cas 1 — L'OF vient de l'ERP (le plus courant).**
1. Une liste **ORDRES DE FABRICATION EN ATTENTE** s'affiche (triée par séquence). Si une production est en cours,
   les OF reçus sont mis de côté et la liste apparaît à la fin de la production.
2. Touchez l'OF à lancer. Le formulaire s'ouvre **pré-rempli** (titre « OF ERP — … — vérifier puis valider »).
3. **Vérifiez** chaque champ, puis validez.

**Cas 2 — Saisie manuelle.** Remplissez : Shop Order · Part Number · Numéro outil · Temps de cycle ·
Nombre d'empreintes · Référence matière · Quantité demandée.

- Si la presse a un fichier **Machine Group**, tapez le début du Part Number : des **suggestions** apparaissent
  (« pièce · outil · empreintes »). L'outil et le nombre d'empreintes se remplissent seuls et ne sont plus
  modifiables. Un Part Number absent du fichier est refusé : demandez aux méthodes de le déclarer.
- Le **temps de cycle** doit être compris entre **1 et 70 s** (réglable) ; sinon la saisie est bloquée.

## 4. Pendant la production

- **Les cycles et les pièces bonnes se comptent seuls.** Ne touchez à rien.
- **Rejets** : les pièces mauvaises sont normalement comptées par l'entrée « rebut » de la presse.
  `+ Rejet` permet d'ajouter une quantité à la main (saisie d'un nombre) ; selon l'état de l'écran, ce bouton peut être grisé.
- **Purge** : `+ Purge`, saisir la quantité purgée **en grammes**.
- **Empreintes** : si une empreinte du moule est fermée, `Empreintes` puis `–` / `+` pour indiquer le nombre
  d'empreintes **actives**, puis valider. Le TRS en tient compte.

## 5. Quand la presse s'arrête

La presse détecte l'arrêt toute seule : aucune pièce pendant environ **2 × le temps de cycle**
(au minimum 30 s, au maximum 300 s). L'état passe à **Arrêt** et une fenêtre **DÉCLARER UN ARRÊT** s'ouvre :
*« Arrêt détecté — déclarez la cause pour continuer »*.

**Choisissez la cause** — c'est obligatoire :

| Cause | E-mail envoyé |
|---|---|
| **Maintenance** | oui |
| **Mécanique** | oui |
| **Qualité** | oui |
| **Process** | oui |
| **Production** | oui |
| **Arrêt planifié** | non — arrêt voulu, **exclu du TRS** |

Le sens exact de chaque catégorie (ce qui relève de « Process » plutôt que de « Production », par exemple)
est une règle d'atelier : la faire valider par les méthodes et l'afficher près de la presse.

Les causes autres que « Arrêt planifié » **envoient un e-mail** aux responsables concernés (maintenance,
méthodes, qualité…).

Vous pouvez aussi **déclarer un arrêt à l'avance** avec `Signaler un Arrêt`.

**Fin de l'arrêt** : quand la presse repart, validez **END STOP** dans la fenêtre d'arrêt ; l'état repasse à
**Production** et la durée de l'arrêt est enregistrée avec sa cause.

**Arrêt sans OF** : sur l'écran de saisie d'OF, le bouton **ARRÊT PLANIFIÉ** met la presse en arrêt planifié sans
ordre de fabrication (par exemple pendant un changement d'outil). Un OF reçu de l'ERP pendant cet arrêt est mis en
file et vous est proposé à la fin.

## 5 bis. Alerte « CT » (temps de cycle)

Si le temps de cycle **saisi** est incohérent avec le temps **réellement mesuré** (écart de plus de 10 s pendant
3 cycles de suite, ou valeur hors plage), l'écran passe en **rouge** avec le message :
`ALERTE CT : réel xx s / saisi yy s`.

Touchez **CORRIGER LE CT**, saisissez le bon temps de cycle puis validez. La correction est refusée si elle
s'écarte de plus de 10 s du temps réel mesuré. L'alerte disparaît d'elle-même une fois le CT correct.

## 6. Terminer la production

1. Touchez **Fin de production**, puis confirmez avec **OUI** (**NON** annule).
2. L'OF est clôturé et la fenêtre de **nouvel OF** (ou la liste ERP) s'affiche.
3. Si la presse ne doit pas tourner après cet OF, utilisez **HORS PLANNING** (confirmation demandée) : un écran
   « MACHINE HORS PLANNING » s'affiche et le temps n'est compté ni en marche ni en arrêt. Touchez
   **REMETTRE EN PLANNING / NOUVEL OF** pour reprendre. Un OF envoyé par l'ERP remet la presse en planning
   automatiquement. *(Fonction disponible si le correctif « hors planning » est installé, voir partie B § 8.)*

## 7. Éteindre la carte

Bouton **OFF** (en haut à droite) → **ÉTEINDRE**. Les données en cours sont sauvegardées avant l'extinction.
Évitez de couper l'alimentation directement. Une période d'extinction est enregistrée comme arrêt
« **Machine OFF** » au redémarrage.

## 8. En cas de problème (opérateur)

| Situation | Que faire |
|---|---|
| La presse tourne mais le compteur ne bouge pas | Prévenir la maintenance : capteur noyau ou câblage à vérifier |
| Le TRS paraît trop bas | Vérifier le **temps de cycle saisi** (alerte CT) et le nombre d'**empreintes** |
| Un Part Number est refusé | Il n'est pas dans le fichier Machine Group : prévenir les méthodes |
| L'écran est rouge | Alerte CT : touchez **CORRIGER LE CT** |
| Écran figé ou noir | Prévenir un administrateur ; ne pas couper l'alimentation sans nécessité |

---

# Partie B — Administrateurs

## 1. Ce qui compose la carte

| Fichier | Rôle |
|---|---|
| `moul.py` | Programme principal : lecture des capteurs, écran, API HTTP, synchro SQL, e-mails |
| `screen.kv` | Interface Kivy (thème Bulgin) |
| `modics-terminal.service` | Service systemd |
| `config_modics.ini` | Configuration de la presse (créée à partir de `config_modics.ini.example`, **jamais versionnée**) |
| `moul.sql` | Table `Machine_Live_State_Mould` et vue `v_Machine_Live_State` |
| `CREATE_TABLE_Machine63_Daily_Report.sql` | Table du rapport journalier de la PRS 63 |
| `machine_group_m63.json` | Copie JSON de secours du fichier Machine Group (régénérée automatiquement) |
| `MODICS_API.md` | Contrat d'interface ERP → carte |

## 2. Matériel et câblage

- Raspberry Pi avec **Automation HAT**, écran tactile 800 × 480 (Kivy, clavier AZERTY).
- Entrées utilisées (numéros de l'Automation HAT, réglables dans `[capteur]`) :

| Entrée | Signal | Paramètre |
|---|---|---|
| 2 | Cycle (noyau) | `cycle_input = 2` |
| 1 | Arrêt machine | `stop_input = 1` |
| 3 | Rebut | `reject_input = 3` |

Mettre `0` désactive une entrée. `edge` choisit le front qui compte un cycle (`rising` = début d'impulsion ;
`falling` = fin d'impulsion). Lecture à `poll_hz` (50 Hz) avec anti-rebond `stable_samples` (3 lectures identiques = 60 ms).

## 3. Installation sur un Pi neuf

Dépendances Python utilisées par `moul.py` : `kivy` (2.3), `automationhat`, `mysql-connector-python`, `pymssql`
(le reste vient de la bibliothèque standard). Un serveur **MySQL local** avec la base `internal_machine_db` est
nécessaire, ainsi qu'un accès réseau au SQL Server MODICS.

```bash
# 1. Copier dans /home/pi/Downloads/ : moul.py, screen.kv (et le fichier Machine Group si utilisé)
# 2. Créer la configuration
cp config_modics.ini.example /home/pi/Downloads/config_modics.ini
nano /home/pi/Downloads/config_modics.ini      # remplacer tous les CHANGE_ME et le nom de la presse
# 3. Installer le service
sudo cp modics-terminal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now modics-terminal
```

Si le terminal est déjà lancé par un autre mécanisme (`rc.local`, `~/.config/autostart`, `crontab @reboot`),
**le retirer** pour éviter deux instances. Adapter `WorkingDirectory` et `ExecStart` du service au dossier réel de `moul.py`.

**Journaux** : `journalctl -u modics-terminal -f` et `/home/pi/Downloads/modics.log`.

Au premier lancement sans `config_modics.ini`, `moul.py` crée un **gabarit** avec des `CHANGE_ME` : le compléter,
l'API restant inactive tant que `api_key` vaut `CHANGE_ME`.

## 4. Configuration — `config_modics.ini`

| Section | Clés | Remarque |
|---|---|---|
| `[machine]` | `name` | **Doit être identique** au nom dans `app/machines.json` et en base (ex. `PRS 63`) |
| `[local_db]` | `path` | Base locale `press.db` (SQLite) : sauvegarde de l'état de la presse toutes les 15 s, restaurée après une coupure |
| `[internal_db]` | `host`, `database`, `user`, `password` | Base **MySQL locale** du Pi : tampon avant envoi vers MODICS |
| `[external_db]` | `server`, `user`, `password`, `database` | SQL Server MODICS |
| `[email]` | `sender`, `app_password`, `receivers_default` | Compte Gmail avec **mot de passe d'application** |
| `[capteur]` | voir § 2, plus `stop_timeout_factor` (2.0), `stop_timeout_min` (30), `stop_timeout_max` (300), `ct_min_s` (1), `ct_max_s` (70), `ct_tolerance_s` (10), `ct_confirm_cycles` (3) | Détection d'arrêt et contrôle du CT |
| `[api]` | `enabled`, `host`, `port` (8080), `api_key` | Une **clé différente par presse** ; la même clé doit figurer dans `machines.json` côté serveur |
| `[machine_group]` | `xlsx`, `sheet` | Optionnel : restreint les Part Number acceptés |

Générer une clé : `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
`MODICS_CONFIG` permet de placer le fichier ailleurs.

> Les adresses des destinataires des e-mails d'arrêt par cause (Maintenance, Mécanique, Qualité, Process, Production)
> sont aujourd'hui **codées dans `moul.py`** (dictionnaire `STOP_MAIL`) ; `receivers_default` sert de liste par défaut.

## 5. Base de données

Principe : la carte écrit d'abord dans la **base MySQL locale** (`internal_machine_db`), copie vers le SQL Server MODICS,
et **ne vide le local que si la copie est confirmée** : une coupure réseau ne fait donc pas perdre de données.

Tables du SQL Server MODICS alimentées par la carte :

| Table | Contenu |
|---|---|
| `Machine_Daily_Table_Mould` | Production, marche, arrêt, TRS par équipe |
| `Machine_Stop_Table_Mould` | Journal des arrêts (code, début, fin, régleur, shop order) |
| `Machine_Live_State_Mould` | **1 ligne par presse**, mise à jour dès qu'un arrêt est déclaré (< 1 s) + battement toutes les 10 s |

Exécuter `moul.sql` crée la table d'état live (elle est aussi créée automatiquement au premier envoi) et la vue
`v_Machine_Live_State` : une carte par ligne, avec l'état affiché et une couleur déjà calculée — **« Machine OFF » si
aucun battement depuis plus de 45 s**. Test : `SELECT * FROM dbo.v_Machine_Live_State;`.

Couleurs de la vue : production `#22C55E` · sans OF `#334155` · Maintenance `#EAB308` · Mécanique `#F97316` ·
Qualité `#A855F7` · Process `#06B6D4` · Production `#EC4899` · Arrêt planifié `#6B8FD6` · hors ligne `#64748B` ·
arrêt non déclaré `#DC2626`.

## 6. Fichiers d'état locaux (à côté de `press.db`)

| Fichier | Contenu | À versionner ? |
|---|---|---|
| `press.db` | Base locale de production | non |
| `modics_of_queue.json` | File des OF reçus de l'ERP (persistée au redémarrage) | non |
| `modics_of_stats.json` | Marche / arrêt / bonnes / rebuts par équipe de l'OF en cours | non |
| `modics_ct_alert.json` | État de l'alerte CT | non |
| `modics_period.json` | Équipe en cours (pour dater « Machine OFF ») | non |
| `modics_out_of_plan.json` | État hors planning (si le correctif est installé) | non |
| `machine_group_m63.json` | Copie JSON du fichier Machine Group | optionnel |

Pour **repartir de zéro** sur une presse, arrêter le service puis supprimer ces fichiers (en gardant `press.db`
si l'historique non synchronisé doit être conservé).

## 7. API HTTP de la carte (port 8080)

Authentification : en-tête `X-Api-Key: <clé>` sur tout sauf `/health`. Contrat complet :
[`MODICS_API.md`](MODICS_API.md).

| Méthode | Route | Usage |
|---|---|---|
| GET | `/api/v1/health` | Supervision (sans clé) |
| GET | `/api/v1/status` | État de production courant |
| GET | `/api/v1/queue` | OF en attente |
| POST | `/api/v1/shop-orders` | Remplace la file complète des OF (recommandé) |
| POST | `/api/v1/shop-order` | Ajoute ou met à jour un OF |
| DELETE | `/api/v1/shop-orders/{shop_order}` | Retire un OF (encoder `/` en `%2F`) |

Validation d'un OF : `shop_order`, `part_number`, `tool_number`, `material_ref` (texte non vide),
`cycle_time` (nombre, 1 à 70 s), `cavities` et `quantity` (entiers > 0). Réponses : `202` accepté, `207` partiel,
`400` invalide ou mauvaise machine, `401` clé invalide, `413` corps > 64 Ko.
L'OF **en cours n'est jamais modifié** par l'API.

Test rapide depuis le serveur :

```bash
curl -s http://<ip-de-la-carte>:8080/api/v1/health
curl -s -H "X-Api-Key: <clé>" http://<ip-de-la-carte>:8080/api/v1/status
```

## 8. Correctifs et déploiement (`../terminal/`)

Le fichier `moul.py` versionné ici est la **base** ; deux fonctions s'ajoutent par correctif :

| Script | Ajoute |
|---|---|
| `apply_actions_api.py` | Routes `POST /api/v1/action/<nom>` utilisées par l'app mobile : `reject`, `purge`, `cycle-time`, `declare-stop`, `end-stop`, `finish`, `launch` (réponse `202` si acceptée, `400/404/409` sinon) |
| `apply_hors_planning.py` | Fonction **HORS PLANNING** et champs `out_of_plan` / `out_of_plan_s` dans `/api/v1/status` |

Application sur un Pi :

```bash
python3 apply_actions_api.py /home/pi/Downloads/moul.py
python3 apply_hors_planning.py /home/pi/Downloads/moul.py
sudo systemctl restart modics-terminal
```

Chaque script est **sûr et idempotent** : il vérifie les points d'ancrage, compile le résultat avant d'écrire
(sinon rien n'est modifié), crée une sauvegarde `moul.py.bak-AAAAMMJJ-HHMMSS` et ne fait rien si le correctif est déjà présent.

**Déploiement sur toutes les cartes (depuis le serveur, en administrateur Windows)** :

1. `install_ssh_key.ps1` — installe la clé SSH du serveur sur chaque Pi (mot de passe du compte `pi` demandé une fois par carte ; relançable sans risque).
2. `deploy_actions_api.ps1` — envoie et exécute le correctif d'actions sur toutes les presses de la liste.

Ces scripts contiennent la liste des IP des Pi : la tenir synchronisée avec `app/machines.json`.

## 9. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Le serveur voit la carte « hors ligne » | Service arrêté, IP changée, pare-feu | `systemctl status modics-terminal` ; `curl …/health` depuis le serveur |
| Erreur `401` | Clé API différente entre carte et `machines.json` | Aligner les deux, redémarrer |
| `API OF désactivée` dans les logs | `api_key` vaut `CHANGE_ME` | Renseigner une clé |
| Deux instances / écran qui clignote | Ancien autostart toujours actif | Retirer `rc.local` / autostart / crontab |
| Le compteur ne bouge pas, état « Production » | Capteur noyau, câblage ou `edge` incorrect | Tester l'entrée ; essayer l'autre valeur de `edge` |
| Arrêts détectés trop tôt / trop tard | Paramètres `stop_timeout_*` | Ajuster `stop_timeout_factor`, `_min`, `_max` |
| Aucun e-mail d'arrêt | `app_password` Gmail invalide, réseau sortant bloqué (SMTP SSL port 465) | Régénérer le mot de passe d'application ; tester la sortie 465 |
| Pas de données dans SQL | `[external_db]` incorrect ou réseau coupé | Vérifier les identifiants ; les données restent dans la base MySQL locale en attendant la prochaine synchro |
| Heure décalée (« clock skew » côté web) | Horloge du Pi fausse | Activer la synchronisation NTP |
| Part Number refusé | Absent du Machine Group | Mettre à jour le fichier `.xlsx` (relu automatiquement quand il change) |
| Changer de presse sur une carte | Mauvais `name` | Modifier `[machine] name` + `api_key`, redémarrer |
