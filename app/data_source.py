"""
Couche d'accès aux données MODICS.

Deux sources possibles, même interface (deux DataFrames : `stops`, `daily`) :
  - Excel  : export MODICS_DATA_2026.xlsx (par défaut)
  - SQL Server : mettre MODICS_SQL_CONN dans l'environnement, ex.
        MODICS_SQL_CONN="mssql+pyodbc://user:pwd@SERVEUR/MODICS?driver=ODBC+Driver+17+for+SQL+Server"
    Azure SQL via Managed Identity : voir db.py (MODICS_SQL_AUTH=entra)
"""
import os
import pandas as pd

EXCEL_PATH = os.environ.get("MODICS_EXCEL", os.path.join("data", "MODICS_DATA_2026.xlsx"))
SQL_CONN = os.environ.get("MODICS_SQL_CONN")
# Machines affichées, séparées par des virgules (MODICS_MACHINES vide = toutes)
# Liste dans app/machines.json (voir machines_config.py) ; MODICS_MACHINES la remplace si définie
import machines_config
MACHINES = machines_config.names()
# Au-delà, une durée d'arrêt est une erreur d'horloge machine (les arrêts longs sont découpés par équipe)
MAX_STOP_MIN = 24 * 60

STOP_COLS = {
    "Machine_Name_Mould": "machine",
    "Date_Insert_Mould": "date_insert",
    "Part_NO_Mould": "part_no",
    "Code_Stop_Mould": "code",
    "Debut_Stop_Time_Mould": "start",
    "Fin_Stop_Time_Mould": "end",
    "Regleur_Prenom_Mould": "regleur",
    "Shift": "shift",
}
DAILY_COLS = {
    "Machine_Name_Mould": "machine",
    "Date_Insert_Day_Mould": "date",
    "Run_Hours_Day_Mould": "run_min",
    "Down_Hours_Day_Mould": "down_min",
    "Good_QTY_Day_Mould": "good_qty",
    "Rejects_QTY_Day_Mould": "reject_qty",
    "Cycle_Time_Day": "cycle_time",
    "Availability_Rate_Day_Mould": "availability",
    "Performance_Rate_Day_Mould": "performance",
    "Quality_Rate_Day_Mould": "quality",
    "OEE_Day_Mould": "oee",
    "Shift_Mould": "shift",
    "Part_Number_Mould": "part_no",
}


# Journée de production : Shift A → Shift B → Shift C. Le Shift C (nuit) se termine le
# lendemain matin, ses données appartiennent donc au jour J-1.
NIGHT_SHIFT = "Shift C"


def _production_day(ts: pd.Series, shift: pd.Series, after_midnight_only=False) -> pd.Series:
    """Jour de production. Pour le Shift C on recule d'un jour ; avec after_midnight_only,
    seulement pour les horodatages du matin (un arrêt à 23h est déjà sur le bon jour)."""
    night = shift == NIGHT_SHIFT
    if after_midnight_only:
        night &= ts.dt.hour < 12
    return ts.dt.normalize() - pd.to_timedelta(night.astype(int), unit="D")


def _read_raw():
    if SQL_CONN:
        import db
        eng = db.get_engine(SQL_CONN)
        stops = pd.read_sql("SELECT * FROM Machine_Stop_Table_Mould", eng)
        daily = pd.read_sql("SELECT * FROM Machine_Daily_Table_Mould", eng)
    else:
        stops = pd.read_excel(EXCEL_PATH, sheet_name="Machine_Stop_Table_Mould")
        daily = pd.read_excel(EXCEL_PATH, sheet_name="Machine_Daily_Table_Mould")
    return stops, daily


def _clean_stops(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=STOP_COLS)
    for c in ("start", "end"):
        df[c] = pd.to_datetime(df[c].astype(str).str.replace(r"\s+", " ", regex=True),
                               dayfirst=True, errors="coerce")
    df["duration_min"] = (df["end"] - df["start"]).dt.total_seconds() / 60
    # Fin avant début ou durée aberrante : horodatage faux, durée inconnue (exclue des totaux)
    bad = (df["duration_min"] < 0) | (df["duration_min"] > MAX_STOP_MIN)
    df.loc[bad, "duration_min"] = None
    df["duration_min"] = df["duration_min"].round(2)
    df["shift"] = df["shift"].str.strip()
    df["day"] = _production_day(df["start"], df["shift"], after_midnight_only=True)
    df["part_no"] = df["part_no"].apply(
        lambda v: "" if pd.isna(v) else str(int(v)) if isinstance(v, float) else str(v).strip())
    df["regleur"] = df["regleur"].fillna("").replace({"NONE": ""})
    df["machine"] = df["machine"].astype(str).str.strip()
    return df.dropna(subset=["start"]).sort_values("start").reset_index(drop=True)


def _clean_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=DAILY_COLS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    num = ["run_min", "down_min", "good_qty", "reject_qty", "cycle_time",
           "availability", "performance", "quality", "oee"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    # Certaines lignes (ex. pièce 13602 le 18/10) stockent les taux en pourcentage (82.04) au lieu
    # d'un ratio (0.82) : un taux ≥ 10 (= 1000 %) n'est pas un ratio, on le ramène à l'échelle 0-1.
    for c in ("availability", "performance", "quality", "oee"):
        df[c] = df[c].where(df[c] < 10, df[c] / 100)
    # OEE = 0 alors que run_min > 0 et les 3 composantes sont non nulles → recalculer
    recalc = (df["oee"] == 0) & (df["run_min"] > 0) & (df["availability"] > 0) & (df["performance"] > 0) & (df["quality"] > 0)
    df.loc[recalc, "oee"] = df.loc[recalc, "availability"] * df.loc[recalc, "performance"] * df.loc[recalc, "quality"]
    df["part_no"] = df["part_no"].apply(
        lambda v: "" if pd.isna(v) or v == "" else str(int(v)) if isinstance(v, float) else str(v))
    df["shift"] = df["shift"].str.strip()
    df["day"] = _production_day(df["date"], df["shift"])
    df["machine"] = df["machine"].astype(str).str.strip()
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def load():
    stops, daily = _read_raw()
    stops, daily = _clean_stops(stops), _clean_daily(daily)
    if MACHINES:
        stops = stops[stops["machine"].isin(MACHINES)].reset_index(drop=True)
        daily = daily[daily["machine"].isin(MACHINES)].reset_index(drop=True)
    return stops, daily
