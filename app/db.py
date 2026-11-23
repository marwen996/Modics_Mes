"""
Connexions SQL partagées par data_source et ifs_api (un moteur SQLAlchemy par chaîne).

Azure SQL sans mot de passe : MODICS_SQL_AUTH=entra et une chaîne sans utilisateur, ex.
    MODICS_SQL_CONN="mssql+pyodbc://@SERVEUR.database.windows.net/MODICS?driver=ODBC+Driver+18+for+SQL+Server"
Le jeton Entra ID vient de DefaultAzureCredential : Managed Identity dans Azure, `az login` en local.
"""
import os
import struct

from sqlalchemy import create_engine, event

SQL_COPT_SS_ACCESS_TOKEN = 1256  # attribut pyodbc pour passer un jeton d'accès
_SCOPE = "https://database.windows.net/.default"
_engines = {}


def get_engine(conn: str):
    if conn not in _engines:
        entra = os.environ.get("MODICS_SQL_AUTH", "").lower() == "entra" and conn.startswith("mssql")
        _engines[conn] = _entra_engine(conn) if entra else create_engine(conn, pool_pre_ping=True)
    return _engines[conn]


def _entra_engine(conn: str):
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    # Le jeton n'est utilisé qu'à l'ouverture ; on recycle les connexions avant son expiration (~1 h)
    engine = create_engine(conn, pool_pre_ping=True, pool_recycle=1800)

    @event.listens_for(engine, "do_connect")
    def _inject_token(dialect, conn_rec, cargs, cparams):
        # Sans utilisateur, SQLAlchemy ajoute Trusted_Connection=Yes, incompatible avec un jeton
        cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")
        token = credential.get_token(_SCOPE).token.encode("utf-16-le")
        cparams["attrs_before"] = {SQL_COPT_SS_ACCESS_TOKEN: struct.pack(f"<I{len(token)}s", len(token), token)}

    return engine
