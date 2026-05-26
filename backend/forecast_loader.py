"""Carga del CSV `predicciones_contaminantes.csv` generado por el equipo de modelado.

El CSV vive en `backend/data/` y contiene 168 horas × 10 estaciones × 3 contaminantes
(PM2.5, NO2, O3). Lo leemos en memoria al arrancar la API y cada vez que el archivo
cambia de mtime.

Si la variable de entorno `FORECAST_CSV_URL` está definida, antes de cada regeneración
del snapshot se descarga el CSV desde esa URL (artifact público en GitLab) y se
reemplaza el archivo local de forma atómica.
"""
import logging
import shutil
import threading
from datetime import datetime

import pandas as pd
import requests

from .config import BACKEND_DIR, POLLUTANTS, FORECAST_CSV_URL
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


def refresh_csv(url: str | None = None, timeout: int = 30) -> bool:
    """Descarga el CSV desde la URL configurada y lo escribe atómicamente sobre
    `CSV_PATH`. Si la descarga falla (timeout, 4xx/5xx, red caída), se hace log de
    warning pero NO se rompe nada — el archivo previo (si existe) sigue intacto y
    el resto del backend continúa funcionando con esos datos.

    Args:
        url: URL pública del CSV. Si es None, usa `FORECAST_CSV_URL` del config.
        timeout: segundos antes de abandonar la descarga.

    Returns:
        True si la descarga + escritura tuvo éxito (el archivo local quedó actualizado).
        False si no había URL configurada o si hubo cualquier error.
    """
    url = url or FORECAST_CSV_URL
    if not url:
        return False

    tmp = CSV_PATH.with_suffix(".csv.tmp")
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(resp.content)
        shutil.move(str(tmp), str(CSV_PATH))
        logger.info("CSV descargado desde %s (%d bytes)", url, len(resp.content))
        return True
    except Exception as e:  # noqa: BLE001 — log y degradación a archivo previo
        logger.warning("No se pudo descargar el CSV desde %s: %s", url, e)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


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
