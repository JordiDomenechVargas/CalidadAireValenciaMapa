"""Generación + cache en memoria del snapshot completo (3 contaminantes × n estaciones)."""
import logging
import threading
from datetime import datetime, timedelta

from .scrape import fetch_air_quality, fetch_meteo_now, last_real_reading
from .weather import fetch_weather_window
from .predict import predict_all_pollutants, get_supported_stations
from .schemas import Snapshot, Station, Meteo, AirReading
from .stations import STATIONS

logger = logging.getLogger(__name__)

_snapshot: Snapshot | None = None
_lock = threading.Lock()


def _meteo_now_from_window(weather: dict, now_hour: datetime) -> dict:
    """Lee la meteo "ahora" del bloque Open-Meteo (la misma fuente que usa el modelo).

    Si el timestamp exacto no está, prueba con offsets pequeños. Como último
    recurso cae a Meteostat (que puede estar roto → fallback hardcoded)."""
    for offset in (0, -1, 1, -2, 2):
        m = weather.get(now_hour + timedelta(hours=offset))
        if m:
            return m
    logger.warning("Open-Meteo sin valor a %s · cayendo a Meteostat fallback", now_hour)
    return fetch_meteo_now()


def _build_snapshot() -> Snapshot:
    """Scrape (48 h) + Open-Meteo (240 h) + inferencia recursiva 168 h."""
    logger.info("Generando nuevo snapshot…")

    air_history = fetch_air_quality()
    weather     = fetch_weather_window()

    now_hour    = datetime.now().replace(minute=0, second=0, microsecond=0)
    meteo_now   = _meteo_now_from_window(weather, now_hour)

    forecasts, last_real_hour = predict_all_pollutants(air_history, weather)
    current = last_real_reading(air_history)

    stations_list = [Station(name=name, lat=lat, lon=lon) for name, (lat, lon) in STATIONS.items()]
    meteo_obj = Meteo(**meteo_now)
    current_obj = {name: AirReading(**vals) for name, vals in current.items()}
    supported = get_supported_stations()

    snap = Snapshot(
        generated_at=datetime.now(),
        last_real_data_at=last_real_hour,
        stations=stations_list,
        meteo=meteo_obj,
        current=current_obj,
        forecasts=forecasts,
        supported_stations=supported,
    )
    logger.info("Snapshot generado · %s · 3 contaminantes · last_real=%s",
                snap.generated_at.isoformat(), last_real_hour.isoformat())
    return snap


def regenerate_snapshot() -> Snapshot:
    """Regenera el snapshot global. Thread-safe."""
    global _snapshot
    with _lock:
        _snapshot = _build_snapshot()
        return _snapshot


def get_snapshot() -> Snapshot | None:
    return _snapshot
