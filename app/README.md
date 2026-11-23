# MODICS — Tableau de bord des presses

Application Flask qui visualise les tables `Machine_Daily_Table_Mould` (TRS/OEE par équipe)
et `Machine_Stop_Table_Mould` (journal des arrêts).

## Lancer

```bash
pip install -r requirements.txt
python app.py
# → http://127.0.0.1:5000
```

Par défaut les données viennent de `data/MODICS_DATA_2026.xlsx`.
Autre fichier : `MODICS_EXCEL=/chemin/export.xlsx python app.py`

## Brancher directement sur SQL Server

```bash
pip install sqlalchemy pyodbc
export MODICS_SQL_CONN="mssql+pyodbc://user:mdp@SERVEUR/MODICS?driver=ODBC+Driver+17+for+SQL+Server"
python app.py
```

Les requêtes sont dans `data_source.py` (`SELECT * FROM Machine_Stop_Table_Mould` / `..._Daily_...`) ;
ajustez-y le schéma ou un filtre de dates si les tables sont volumineuses.
`POST /api/reload` recharge les données sans redémarrer.

## API JSON

Tous les endpoints acceptent `?machine=&shift=&start=YYYY-MM-DD&end=YYYY-MM-DD`.

- `/api/summary` — KPIs, tendance TRS, arrêts par code / jour, marche-arrêt par machine
- `/api/stops` — journal des arrêts (durée calculée en minutes)
- `/api/daily` — enregistrements de production par équipe

## Supervision temps réel (`pi_live.py`, page `/live`)

Relais vers l'API HTTP du terminal Raspberry Pi de la presse (`moul.py`, port 8080) :
état (production / arrêt / attente d'OF), OF en cours, avancement et fin théorique, compteurs,
TRS de l'OF, file des OF reçus de l'ERP, arrêts du jour. Rafraîchissement toutes les 3 s.
Le navigateur n'appelle que MODICS : la clé du terminal reste côté serveur.

Plusieurs machines : `MODICS_MACHINES` (défaut `PRS 63,PRS 68,PRS 78,PRS 80,PRS 81`) pilote à la fois le tableau de bord
et la supervision. Chaque machine a son terminal et son fil d'échantillonnage (une machine injoignable
ne ralentit pas les autres) ; la page `/live` affiche une carte par machine, cliquable pour le détail.

```bash
export MODICS_MACHINES="PRS 63,PRS 68,PRS 78,PRS 80,PRS 81"
export MODICS_PI_KEY="..."                     # [api] api_key de config_modics.ini sur le Pi (clé par défaut, obligatoire)
export MODICS_PI_KEY_68="..."                  # optionnel : clé propre à PRS 68 si elle diffère (idem _78, _80, _81…)
# optionnel : sinon l'IP est lue dans IP_Address_Table_Machines_Mould.IP_address_Mould_<NN>
export MODICS_PI_URL_68="http://192.168.x.y:8080"
```

- `GET /live?machine=PRS 68` — page de supervision (`&tv=1` : mode TV d'une machine précise)
- `GET /api/live?machine=PRS 68` — `{"online", "status", "queue", "alerts", "metrics", …}` (1re machine par défaut ; 404 si inconnue)
- `GET /api/live/fleet` — résumé de toutes les machines (état, OF, TRS, alertes)
- `GET /api/live/oee?machine=` — TRS jour / 24 h / semaine (toutes machines sans paramètre)

## Analyse IA avec Claude (`ai_insights.py`)

Panneau « Analyse IA » du tableau de bord : résumé, alertes, prévisions et actions sur les
données filtrées, plus une zone de questions libres. Les indicateurs et la prévision de référence
(régression linéaire du TRS) sont calculés avec pandas ; Claude les interprète.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."     # obligatoire, sinon /api/ai/* répond 503
# optionnel
export MODICS_AI_MODEL="claude-opus-5-5"   # modèle
export MODICS_AI_EFFORT="medium"           # low | medium | high | xhigh | max
export MODICS_AI_CACHE=900                 # une analyse est réutilisée 15 min pour les mêmes filtres
```

- `POST /api/ai/insights` — `{"machine", "shift", "start", "end", "force"}` → analyse structurée (JSON)
- `POST /api/ai/ask` — `{"question", "machine", "shift", "start", "end"}` → réponse texte

Chaque appel est facturé par Anthropic (quelques centimes) : l'analyse n'est lancée qu'au clic.
Les données envoyées sont des agrégats et les 60 derniers arrêts (aucune donnée personnelle hormis
les prénoms des régleurs).

## API de réception IFS (`ifs_api.py`)

IFS envoie ses ordres de fabrication à MODICS. Chaque appel doit porter l'en-tête
`X-API-Key: <IFS_API_KEY>` ; sans `IFS_API_KEY` côté serveur, l'API répond 503.

```bash
export IFS_API_KEY="une-longue-cle-aleatoire"
# optionnel : base de stockage (défaut : MODICS_SQL_CONN, sinon data/ifs_inbox.db en SQLite)
export IFS_DB_CONN="mssql+pyodbc://user:mdp@SERVEUR/MODICS?driver=ODBC+Driver+17+for+SQL+Server"
```

- `POST /api/ifs/shop-orders` — un objet, une liste, ou `{"items": [...]}` (max 1000).
  Une ligne par `shop_order` + `component` + `tool_group` dans la table `IFS_Shop_Orders`
  (créée automatiquement) : un OF à plusieurs composants est envoyé en plusieurs lignes.
  Une ligne déjà reçue est mise à jour. Si une ligne est invalide, tout le lot est rejeté (400 + détail).
- `GET /api/ifs/shop-orders?shop_order=&part_no=&production_line=&tool_group=&component=&limit=` — vérification.

| Champ | Obligatoire | Exemple |
|---|---|---|
| `production_line` | non | `"PRS 63"` |
| `part_no` | oui | `"14000012"` |
| `shop_order` | oui | `"SO-1001"` |
| `tool_group` | non | `"TG-01"` |
| `component` | non | `"PA66-BK"` |
| `lot_size` | oui, > 0 | `5000` |
| `tool_quantity` | non, >= 0 | `2` |

Les libellés (`"Production Line"`, `"Part Number"`, `"Shop Order"`…) et les noms IFS
(`PRODUCTION_LINE`, `PartNo`, `OrderNo`, `LotSize`…) sont aussi acceptés.

```bash
curl -X POST http://SERVEUR:5000/api/ifs/shop-orders \
  -H "X-API-Key: $IFS_API_KEY" -H "Content-Type: application/json" \
  -d '[{"production_line":"PRS 63","part_no":"14000012","shop_order":"SO-1001",
        "tool_group":"TG-01","component":"PA66-BK","lot_size":5000,"tool_quantity":2}]'
# → {"received": 1, "inserted": 1, "updated": 0}
```

