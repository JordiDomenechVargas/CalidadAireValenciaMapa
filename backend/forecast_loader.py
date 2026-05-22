"""Carga del CSV `predicciones_contaminantes.csv` generado por el equipo de modelado.

El CSV vive en `backend/data/` y contiene 168 horas × 10 estaciones × 3 contaminantes
(PM2.5, NO2, O3). Lo leemos en memoria al arrancar la API y cada vez que el archivo
cambia de mtime (los compañeros lo regeneran diariamente, en breve cada hora).
"""
import logging
import threading
from datetime import datetime

import pandas as pd

from .config import BACKEND_DIR, POLLUTANTS
from .stations import MODEL_NAME_TO_CANONICAL, STATION_NAMES, PHYSICAL_COVERAGE

logger = logging.getLogger(__name__)

CSV_PATH = BACKEND_DIR / "data" / "predicciones_contaminantes.csv"

# Columna del CSV → clave interna
_COL_BY_POLLUTANT = {
    "PM25": "PM25_Previsto",
    "NO2":  "NO2_Previsto",
    "O3":   "O3_Previsto",
}

_cache: dict | None = None
_lock = threading.Lock()


def _load() -> dict:
    """Lee y parsea el CSV. Devuelve dict con forecasts + forecast_start_at + mtime."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No existe {CSV_PATH}. Pide a tus compañeros que lo regeneren.")

    df = pd.read_csv(CSV_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    forecast_start_at = df["timestamp"].min().to_pydatetime()

    # Filtrar "Puerto Valencia" (estación no existente) y mapear nombres → canónicos
    df = df[df["estacion"] != "Puerto Valencia"].copy()
    df["canonical"] = df["estacion"].map(MODEL_NAME_TO_CANONICAL)
    df = df.dropna(subset=["canonical"])

    forecasts: dict[str, dict[str, list[float]]] = {}
    for pollutant, col in _COL_BY_POLLUTANT.items():
        forecasts[pollutant] = {}
        allowed = set(PHYSICAL_COVERAGE[pollutant])
        for station, sub in df.groupby("canonical"):
            # Filtrar estaciones que no tienen sensor físico de este contaminante:
            # aunque el CSV trae valores, no son medidas fiables (extrapoladas).
            if station not in allowed:
                continue
            sub = sub.sort_values("timestamp")
            forecasts[pollutant][station] = [round(float(v), 2) for v in sub[col].tolist()]

    return {
        "forecasts": forecasts,
        "forecast_start_at": forecast_start_at,
        "mtime": CSV_PATH.stat().st_mtime,
    }


def get_forecasts() -> tuple[dict[str, dict[str, list[float]]], datetime]:
    """Devuelve (forecasts, forecast_start_at). Recarga si el mtime del CSV cambió."""
    global _cache
    with _lock:
        current_mtime = CSV_PATH.stat().st_mtime if CSV_PATH.exists() else None
        if _cache is None or _cache["mtime"] != current_mtime:
            logger.info("Releyendo %s (mtime=%s)", CSV_PATH, current_mtime)
            _cache = _load()
        return _cache["forecasts"], _cache["forecast_start_at"]


def supported_stations() -> dict[str, list[str]]:
    """Por contaminante, estaciones canónicas que el CSV cubre (ordenadas como STATIONS)."""
    forecasts, _ = get_forecasts()
    return {p: sorted(forecasts[p].keys(), key=STATION_NAMES.index) for p in POLLUTANTS}
