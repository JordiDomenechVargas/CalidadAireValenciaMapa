"""Gestión del snapshot completo de la red — generación + cache en memoria con lock."""
import logging
import threading
from datetime import datetime

from .scrape import fetch_air_quality, fetch_meteo
from .predict import predict_168h
from .schemas import Snapshot, Station, Meteo, AirReading
from .stations import STATIONS

logger = logging.getLogger(__name__)

_snapshot: Snapshot | None = None
_lock = threading.Lock()


def _build_snapshot() -> Snapshot:
    """Hace scraping + inferencia y construye un Snapshot completo. Operación pesada."""
    logger.info("Generando nuevo snapshot…")
    air_data = fetch_air_quality()
    meteo_data = fetch_meteo()
    forecasts = predict_168h(air_data, meteo_data)

    stations = [Station(name=name, lat=lat, lon=lon) for name, (lat, lon) in STATIONS.items()]
    meteo = Meteo(**meteo_data)
    current = {
        name: AirReading(**air_data.get(name, {"O3": 0.0, "NO2": 0.0, "PM25": 0.0}))
        for name in STATIONS
    }
    snap = Snapshot(
        generated_at=datetime.now(),
        stations=stations,
        meteo=meteo,
        forecasts=forecasts,
        current=current,
    )
    logger.info("Snapshot generado a las %s", snap.generated_at.isoformat())
    return snap


def regenerate_snapshot() -> Snapshot:
    """Regenera el snapshot global. Thread-safe: si ya hay otra regeneración en curso,
    espera a que termine y devuelve el resultado de esa."""
    global _snapshot
    with _lock:
        _snapshot = _build_snapshot()
        return _snapshot


def get_snapshot() -> Snapshot | None:
    """Devuelve el último snapshot generado (o None si aún no se ha ejecutado ninguno)."""
    return _snapshot
