# Mode d'emploi — Serveur web MODICS (`app/`)

Ce guide a deux publics : les **utilisateurs** (§ 1 à 5 : consulter les écrans) et les **administrateurs**
(§ 6 à 10 : installer, configurer, dépanner). Pour la carte installée sur chaque presse, voir
[`../carte/MODE_EMPLOI.md`](../carte/MODE_EMPLOI.md). Pour la référence technique des routes, voir [`README.md`](README.md).

---

# Partie A — Utilisateurs

## 1. Accéder à MODICS

| Où vous êtes | Adresse | Mot de passe |
|---|---|---|
| Réseau de l'atelier / bureau | l'adresse interne du serveur MODICS | non |
| Hors de l'usine (Internet) | l'adresse publique (tunnel Cloudflare) | oui : identifiant et mot de passe fournis par l'administrateur |
| Téléphone | même adresse + `/mobile` | selon l'endroit, comme ci-dessus |

Le menu de gauche donne accès à quatre écrans : **Atelier**, **Parc**, **Analyse**, **Live**. Le bouton de thème
bascule entre clair et sombre ; la langue (français / anglais) se change depuis l'interface.

## 2. Les écrans

### Atelier — la page d'accueil
L'état de l'atelier en langage simple : un titre qui résume la situation, la liste des actions à traiter
et des indicateurs de synthèse. Elle se rafraîchit seule ; la pastille « live » indique si les données arrivent.
À consulter en début d'équipe.

### Parc — toutes les presses d'un coup d'œil (`/fleet`)
Une tuile par presse : état (production, arrêt, sans OF, hors planning, hors ligne, maintenance), OF en cours,
quantité produite, TRS et alertes. Pour un arrêt, la **cause** et la **durée** sont affichées.

- **Rechercher** : par presse, pièce ou ordre de fabrication.
- **Filtrer / trier** : par état ou par priorité (les presses à problème en premier).
- **Mode TV** (`?tv=1` ou bouton « Mode TV ») : tout le parc sur un seul écran, sans défilement, pour l'écran d'atelier.
  Les tuiles ne changent jamais de place (tri par numéro de presse). « Quitter le mode TV » pour revenir.
- Cliquer sur une tuile ouvre le détail Live de la presse.

### Live — le détail d'une presse (`/live`)
Choisir la presse en haut de page. Vous y trouvez :

- **Alertes** de la presse, de la plus grave à la moins grave (voir § 3).
- **Jauges** TRS de l'OF, performance (cadence réelle / cadence théorique) et qualité.
- **OF en cours** : shop order, pièce, outil, temps de cycle cible, quantités bonnes / rebuts / restantes et fin théorique.
- **TRS** du jour de production, des 24 dernières heures et de la semaine.
- **Chronologie** de la journée (06:00 → 06:00) : bandes colorées Production / Arrêt / Sans OF / Hors planning / Hors ligne.
- **Cadence** : pièces par tranche de 10 minutes, avec la cible.
- **MTBF / MTTR** : durée moyenne de marche entre deux arrêts / durée moyenne d'un arrêt.
- **File des OF** reçus de l'ERP.

Mode TV d'une presse précise : `/live?machine=PRS 68&tv=1`.

> Les mesures « live » (chronologie, cadence, MTBF/MTTR) ne couvrent que les 24 dernières heures et
> repartent de zéro quand le serveur redémarre. Le TRS et l'analyse, eux, viennent de la base.

### Analyse — l'historique (`/analyse`)
Filtres : presse, équipe (A/B/C), période. Vous obtenez :

- **Indicateurs** : TRS, disponibilité, performance, qualité, pièces bonnes, rebuts, minutes de marche et d'arrêt,
  avec la **variation** par rapport à la période précédente de même durée (si vous choisissez une période) et une mini-courbe par jour.
- **Tendance du TRS** par équipe, **Pareto des arrêts** par cause, arrêts par jour, marche/arrêt par presse.
- **Journal des arrêts** et **production par équipe** (données brutes).
- **Analyse IA** (si activée par l'administrateur) : bouton « Analyser » → résumé, alertes, prévisions des
  prochains jours et actions prioritaires, plus une zone pour poser une question libre sur les données filtrées.
  Chaque analyse est facturée par Anthropic (quelques centimes) : elle ne démarre qu'au clic et le résultat est
  réutilisé 15 minutes pour les mêmes filtres.

## 3. Comprendre les alertes

| Alerte | Se déclenche quand… | Gravité |
|---|---|---|
| Presse hors ligne | la carte ne répond plus (câble, alimentation, réseau, clé) | critique |
| Arrêt en cours | la presse est en arrêt ; **critique à partir de 10 min** | avertissement → critique |
| Rebuts élevés | taux de rebut ≥ 2 % (**critique ≥ 5 %**), à partir de 50 pièces | avertissement → critique |
| TRS bas | TRS de l'OF < 75 % (**critique < 60 %**) | avertissement → critique |
| Cadence basse | cadence réelle < 85 % de la théorique sur 30 min | avertissement |
| Production sans pièce | état « Production » mais aucune pièce comptée depuis 5 min (ou 3 cycles) : vérifier le capteur noyau | avertissement |
| Surproduction | quantité produite > quantité de l'OF | avertissement |
| Horloge décalée | l'horloge de la carte diffère de plus de 2 min de celle du serveur | avertissement |
| Pas d'OF suivant | la file ERP est vide et l'OF actuel se termine dans moins d'1 h | information |

## 4. L'application mobile (`/mobile`)

Page web conçue pour le téléphone (format PWA) pour **piloter une presse à distance**. Le navigateur peut proposer
« Ajouter à l'écran d'accueil » ; l'installation complète dépend d'un fichier `/manifest.json` que la page
référence mais qui n'est pas fourni dans le dépôt (voir README racine, § 7).

1. **Ajouter une presse** : bouton **+**, saisir le nom (ex. PRS 63) et sa clé. La liste est mémorisée sur le téléphone.
2. Toucher une presse pour ouvrir sa fiche : état, OF, compteurs.
3. Actions disponibles : **Signaler un arrêt** (choix de la cause) et **Fin d'arrêt**, **Ajouter des rejets**,
   **Ajouter une purge (g)**, **Corriger le temps de cycle**, **Terminer l'OF**, **Saisir un nouvel OF**
   (avec suggestions issues de la table Machine Group) et **Lancer** un OF de la file ERP.
4. Le bouton « Réessayer » apparaît si la presse est injoignable.

Les actions de pilotage nécessitent que la carte de la presse ait reçu le correctif « actions API »
(voir le guide de la carte, partie B § 8) ; sans lui, la lecture fonctionne mais pas les actions.

## 5. Questions fréquentes

| Question | Réponse |
|---|---|
| Une presse apparaît « hors ligne » | Vérifier que la carte est alimentée et sur le réseau ; l'écran de la presse doit être allumé. Voir § 10. |
| Une presse apparaît « maintenance » | Elle est marquée ainsi par l'administrateur (`maintenance: true`) ; elle n'est pas interrogée. |
| Le TRS d'une équipe semble faux | Seules les équipes avec du temps de marche comptent dans la moyenne ; les arrêts planifiés sont exclus. |
| Pourquoi la nuit est-elle rattachée à la veille ? | La journée de production va de 06:00 à 06:00 : le Shift C de la nuit du lundi au mardi appartient à lundi. |
| Les données ne bougent plus | Le bandeau d'erreur signale une base injoignable : les dernières données connues restent affichées. Prévenir l'administrateur. |

---

# Partie B — Administrateurs

## 6. Installation du serveur

```bash
cd app
pip install -r requirements.txt        # flask, pandas, sqlalchemy, pyodbc, waitress, azure-identity, anthropic
python app.py                          # test local → http://127.0.0.1:5000
```

Sans configuration, l'application lit l'export Excel `data/MODICS_DATA_2026.xlsx` (mode démonstration).
Pour la production, brancher SQL Server (§ 7).

**Production (Windows)** : copier `start.example.cmd` (à la racine) en `start.cmd`, remplacer les valeurs `<...>`,
et le lancer par une **tâche planifiée « MODICS »** au démarrage. Le script exécute waitress sur `127.0.0.1:5050`
(16 threads) et écrit les journaux dans `C:\inetpub\modics\logs\server.log`. IIS (ARR) sert de reverse proxy grâce à
`site/web.config`, qui redirige tout vers `http://127.0.0.1:5050`.

> Dans un `.cmd`, un `%` littéral s'écrit `%%` : un mot de passe contenant `@` s'encode `%%40` dans la chaîne de connexion.

## 7. Configuration

### 7.1 Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `MODICS_SQL_CONN` | Chaîne SQLAlchemy vers la base MODICS | Excel |
| `MODICS_SQL_AUTH` | `entra` : Azure SQL sans mot de passe (Managed Identity / `az login`) | — |
| `MODICS_EXCEL` | Chemin de l'export Excel (si pas de SQL) | `data/MODICS_DATA_2026.xlsx` |
| `MODICS_REFRESH` | Relecture des tables, en secondes | 30 |
| `MODICS_MACHINES` | Liste de presses séparées par des virgules (remplace `machines.json`) | `machines.json` |
| `MODICS_MACHINES_FILE` | Autre chemin pour `machines.json` | `app/machines.json` |
| `MODICS_PI_KEY` | Clé API par défaut des cartes | — |
| `MODICS_PI_KEY_<NN>` / `MODICS_PI_URL_<NN>` | Clé / URL propre à la presse PRS `<NN>` (prioritaires sur `machines.json`) | — |
| `MODICS_PI_PORT` | Port des cartes quand l'IP vient de la base | 8080 |
| `MODICS_PI_POLL` | Période de sonde des cartes (s) | 5 |
| `MODICS_PI_OFFLINE_POLL` | Période de sonde d'une carte injoignable (s) | 30 |
| `MODICS_PI_WORKERS` | Cartes interrogées en parallèle | 16 |
| `IFS_API_KEY` | Clé partagée avec IFS pour `/api/ifs/...` (sans elle : erreur 503) | — |
| `IFS_DB_CONN` | Base de stockage des OF IFS | `MODICS_SQL_CONN`, sinon SQLite `data/ifs_inbox.db` |
| `MODICS_PUBLIC_USER` / `MODICS_PUBLIC_PASSWORD` | Identifiants exigés pour l'accès Internet (sans eux : accès Internet refusé, 503) | — |
| `ANTHROPIC_API_KEY` | Active le panneau « Analyse IA » | — |
| `MODICS_AI_MODEL` | Modèle utilisé | `claude-opus-5-5` |
| `MODICS_AI_EFFORT` | `low` · `medium` · `high` · `xhigh` · `max` | `medium` |
| `MODICS_AI_CACHE` | Réutilisation d'une analyse (s) | 900 |

Priorité pour chaque presse : variable d'environnement > `machines.json` > clé par défaut ; l'IP, si elle n'est pas
renseignée, est lue dans `IP_Address_Table_Machines_Mould.IP_address_Mould_<NN>`.

### 7.2 Déclarer les presses — `app/machines.json`

Créer le fichier à partir de `machines.example.json`. **Il n'est pas versionné** (il contient les clés).

```json
{
  "port": 8080,
  "machines": [
    {"name": "PRS 63", "url": "http://192.168.81.56:8080", "key": "<cle-de-la-presse>"},
    {"name": "PRS 67", "key": "<cle>"},
    {"name": "PRS 7",  "maintenance": true}
  ]
}
```

- Une entrée par presse. Sans `url`, l'IP est lue en base ; sans `key`, `MODICS_PI_KEY` est utilisée.
- `"maintenance": true` : la presse n'est plus interrogée et apparaît « Maintenance ».
- Après modification, **redémarrer le serveur** (la liste est lue au démarrage).

### 7.3 Tables utilisées

| Table | Écrite par | Contenu |
|---|---|---|
| `Machine_Daily_Table_Mould` | cartes | Production par équipe : marche, arrêt, bonnes, rebuts, TRS |
| `Machine_Stop_Table_Mould` | cartes | Journal des arrêts (code, début, fin, régleur) |
| `Machine_Live_State_Mould` | cartes | État en direct, 1 ligne par presse (créée par `carte/moul.sql`) |
| `Machine_Timeline_Mould` | serveur (auto) | Chronologie des états, sauvegardée chaque minute |
| `IFS_Shop_Orders` | serveur (auto) | OF reçus d'IFS par `POST /api/ifs/shop-orders` |

## 8. Intégrations

### 8.1 Recevoir les OF d'IFS — `POST /api/ifs/shop-orders`

En-tête obligatoire `X-API-Key: <IFS_API_KEY>`. Corps : un objet, une liste, ou `{"items": [...]}` (1000 lignes max).
Une ligne par `shop_order` + `component` + `tool_group` ; une ligne déjà reçue est mise à jour. Si **une seule**
ligne est invalide, **tout le lot est rejeté** (400 + détail) : IFS renvoie après correction.

Champs obligatoires : `part_no`, `shop_order`, `lot_size` (> 0). Optionnels : `production_line`, `tool_group`,
`component`, `tool_quantity` (≥ 0). Les libellés (`"Shop Order"`) et noms IFS (`OrderNo`, `PartNo`, `LotSize`) sont acceptés.
Vérification : `GET /api/ifs/shop-orders?shop_order=…&limit=…`.

### 8.2 Accès Internet

Le trafic qui passe par Cloudflare est reconnu à l'en-tête `Cf-Ray` : il exige identifiant et mot de passe
(HTTP Basic). Le réseau interne reste libre. Après 8 échecs en 10 minutes, l'adresse est bloquée (429) ; sans
`MODICS_PUBLIC_USER/PASSWORD` configurés, l'accès Internet est refusé (503).

### 8.3 Relais vers les cartes (app mobile)

`/proxy/<presse>/api/v1/<chemin>` relaie la requête vers la carte (ex. `/proxy/prs63/api/v1/status`), de sorte que
le téléphone n'a jamais besoin des adresses internes. Le nom est la presse sans espace ni majuscule.

### 8.4 Recharger les données sans redémarrer
`POST /api/reload` force la relecture des tables.

## 9. Exploitation courante

| Tâche | Comment |
|---|---|
| Ajouter une presse | Ajouter l'entrée dans `machines.json`, installer la carte, redémarrer le serveur |
| Mettre une presse en maintenance | `"maintenance": true` dans `machines.json`, redémarrer |
| Changer une clé de carte | Modifier `[api] api_key` sur la carte **et** la clé dans `machines.json`, redémarrer le service de la carte puis le serveur |
| Voir les erreurs | `C:\inetpub\modics\logs\server.log` |
| Mettre à jour le serveur | Remplacer les fichiers de `app/`, redémarrer la tâche planifiée « MODICS » |
| Coût de l'IA | Surveiller la consommation Anthropic ; `MODICS_AI_CACHE` limite les appels répétés |

## 10. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Une presse est « hors ligne » | Carte éteinte, IP changée, mauvaise clé | `curl http://<ip>:8080/api/v1/health` depuis le serveur ; vérifier la clé (erreur « auth ») et l'IP |
| Toutes les presses sont hors ligne | Réseau / pare-feu entre serveur et VLAN | Tester depuis le serveur le port 8080 d'une carte |
| Message « Machine unreachable » sur mobile | La carte ne répond pas au relais | Idem ci-dessus |
| Page blanche, erreur 503 sur `/api/ai/*` | `ANTHROPIC_API_KEY` absente | La définir dans `start.cmd` |
| Erreur 503 sur `/api/ifs/*` | `IFS_API_KEY` absente | La définir dans `start.cmd` |
| Impossible de se connecter depuis Internet | Identifiants publics absents ou IP bloquée (429) | Vérifier `MODICS_PUBLIC_*` ; attendre 10 min |
| Le serveur démarre mais pas les données SQL | Chaîne `MODICS_SQL_CONN` incorrecte, driver ODBC absent | Tester la connexion ; vérifier le nom du driver |
| Les chronologies sont vides après un redémarrage | L'historique live est en mémoire | Normal ; la chronologie enregistrée est consultable via `/api/live/timeline?machine=&day=` |
| Heure décalée sur une presse | Horloge de la carte fausse | Régler l'heure de la carte (NTP) |
