# Partie carte — terminal Raspberry Pi d'une presse

Logiciel qui tourne **sur la carte Raspberry Pi** montée sur chaque presse (Arburg PRS 63, 67, …).
Il compte les cycles via l'Automation HAT, affiche l'écran opérateur (Kivy 800x480), enregistre
la production en local puis la synchronise vers la base MODICS, et expose une API HTTP
(port 8080) que l'ERP (IFS) et le serveur `app/` interrogent.

## Contenu

| Fichier | Rôle |
|---|---|
| `moul.py` | Application principale : capteurs, écran Kivy, API HTTP, synchro SQL, e-mails d'alerte |
| `screen.kv` | Interface Kivy (thème industriel Bulgin) |
| `modics-terminal.service` | Service systemd (démarrage automatique, redémarrage en cas de plantage) |
| `config_modics.ini.example` | Modèle de configuration (à copier en `config_modics.ini`) |
| `moul.sql` | Table `Machine_Live_State_Mould` + vue `v_Machine_Live_State` (état temps réel) |
| `CREATE_TABLE_Machine63_Daily_Report.sql` | Table du rapport journalier PRS 63 |
| `machine_group_m63.json` | Correspondance pièce → outil / empreintes / dévissage pour la PRS 63 |
| `MODICS_API.md` | Contrat d'interface ERP (IFS) → terminal |

Les scripts de déploiement et de correctif côté Pi sont dans `../terminal/`.

## Installation sur le Pi

```bash
# 1. Copier moul.py, screen.kv et machine_group_m63.json dans /home/pi/Downloads/
# 2. Configuration : copier le modèle puis remplacer tous les CHANGE_ME
cp config_modics.ini.example /home/pi/Downloads/config_modics.ini
nano /home/pi/Downloads/config_modics.ini
# 3. Service systemd
sudo cp modics-terminal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now modics-terminal
# Logs : journalctl -u modics-terminal -f
```

L'API reste **inactive** tant que `[api] api_key` vaut `CHANGE_ME`.
La clé de chaque presse est aussi déclarée côté serveur dans `app/machines.json`.

## Secrets — à ne jamais versionner

`config_modics.ini` (mots de passe SQL, mot de passe d'application Gmail, clé API), `press.db`
(base locale de production) et les fichiers d'état `modics_*.json` sont ignorés par git
(voir `.gitignore`). Si un secret a été publié par erreur, le **changer** : le supprimer
du dépôt ne suffit pas, il reste dans l'historique.
