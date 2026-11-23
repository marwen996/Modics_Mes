@echo off
rem MODICS Flask backend (waitress) - launched by the "MODICS" scheduled task at boot
rem Copier ce fichier en start.cmd et remplacer les valeurs <...>. start.cmd n'est pas versionne (secrets).
rem Note: in .cmd files a literal %% must be doubled, so "%%40" = URL-encoded "@" in the password
cd /d C:\inetpub\modics\app
set MODICS_SQL_CONN=mssql+pyodbc://<user>:<password>@<sql-server>/MODICS?driver=ODBC+Driver+17+for+SQL+Server
rem Cle partagee avec IFS (en-tete X-API-Key sur /api/ifs/...)
set IFS_API_KEY=<ifs-api-key>
rem Cle par defaut des terminaux. La liste des presses, leurs IP et leurs cles propres sont dans app\machines.json
rem (les variables MODICS_PI_URL_<NN> / MODICS_PI_KEY_<NN> restent prioritaires si on les definit ici).
set MODICS_PI_KEY=<cle-terminal-par-defaut>
rem Acces depuis Internet (tunnel Cloudflare) : identifiants exiges par app\public_gate.py ; le reseau interne reste libre
set MODICS_PUBLIC_USER=<utilisateur>
set MODICS_PUBLIC_PASSWORD=<mot-de-passe>
"C:\Python314\python.exe" -m waitress --host=127.0.0.1 --port=5050 --threads=16 app:app >> C:\inetpub\modics\logs\server.log 2>&1
