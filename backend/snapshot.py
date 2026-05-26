"""Snapshot completo de la red.

Composición:
  - Forecasts (PM2.5/NO2/O3 × 9 estaciones × 168 h): leídos del CSV pre-generado.
  - Meteo "ahora": de Open-Meteo (la misma fuente que se podría usar para forecasts si
    quisiéramos reactivar el pipeline ML; aquí sólo sirve para la card del sidebar).
  - Current air (PM2.5/NO2/O3 reales actuales): scrape directo al endpoint RVVCCA.
"""
import logging
import threading
from datetime import datetime, timedelta

from .scrape import fetch_air_quality, fetch_meteo_now, last_real_reading
from .weather import fetch_weather_window
from .forecast_loader import get_forecasts, refresh_csv, supported_stations
from .schemas import Snapshot, Station, Meteo, AirReading
from .stations import STATIONS
from .config import now_local, METEO_FALLBACK

logger = logging.getLogger(__name__)

_snapshot: Snapshot | None = None
_lock = threading.Lock()


def _meteo_now_from_window(weather: dict, now_hour: datetime) -> dict:
    """Lee la meteo "ahora" del bloque Open-Meteo. Si el timestamp exacto no está,
    prueba con offsets pequeños. Como último recurso cae a Meteostat fallback."""
    for offset in (0, -1, 1, -2, 2):
        m = weather.get(now_hour + timedelta(hours=offset))
        if m:
            return m
    logger.warning("Open-Meteo sin valor a %s · usando Meteostat fallback", now_hour)
    return fetch_meteo_now()


def _build_snapshot() -> Snapshot:
    """Combina lecturas reales + meteo actual + previsiones del CSV."""
    logger.info("Generando snapshot…")

    # Descarga el CSV nuevo si hay URL configurada (FORECAST_CSV_URL).
    # Si falla, el backend sigue funcionando con el CSV anterior en disco.
    refresh_csv()

    air_history = fetch_air_quality()
    weather     = fetch_weather_window()

    now_hour    = now_local().replace(minute=0, second=0, microsecond=0)
    meteo_now   = _meteo_now_from_window(weather, now_hour)

    forecasts, forecast_start_at = get_forecasts()
    current = last_real_reading(air_history)

    all_dates = [r["date"] for rows in air_history.values() for r in rows if r.get("date")]
    last_real_hour = max(all_dates) if all_dates else now_hour

    snap = Snapshot(
        generated_at=now_local(),
        forecast_start_at=forecast_start_at,
        last_real_data_at=last_real_hour,
        stations=[Station(name=name, lat=lat, lon=lon) for name, (lat, lon) in STATIONS.items()],
        meteo=Meteo(**meteo_now),
        current={n: AirReading(**v) for n, v in current.items()},
        forecasts=forecasts,
        supported_stations=supported_stations(),
    )
    logger.info("Snapshot generado · forecast_start=%s · last_real=%s",
                forecast_start_at.isoformat(), last_real_hour.isoformat())
    return snap


def regenerate_snapshot() -> Snapshot:
    """Regenera el snapshot global. Thread-safe."""
    global _snapshot
    with _lock:
        _snapshot = _build_snapshot()
    return _snapshot


def _is_fallback_meteo(m: dict) -> bool:
    """Detecta si un dict meteo coincide exactamente con METEO_FALLBACK (Open-Meteo y
    Meteostat caídos). En ese caso preferimos NO sobreescribir el último meteo bueno
    que ya hubiera en el snapshot."""
    return all(m.get(k) == v for k, v in METEO_FALLBACK.items())


def refresh_meteo() -> bool:
    """Refresca SOLO el campo `meteo` del snapshot global. Diseñado para correr
    cada pocos minutos: hace una llamada ligera a Open-Meteo y, si recibe un valor
    distinto del fallback, sustituye `_snapshot.meteo` en sitio.

    Returns:
        True si el meteo se actualizó con datos frescos.
        False si Open-Meteo seguía caído o todavía no hay snapshot inicial.
    """
    global _snapshot
    if _snapshot is None:
        return False  # Esperar a que `regenerate_snapshot()` haya construido el primero

    weather = fetch_weather_window()
    now_hour = now_local().replace(minute=0, second=0, microsecond=0)
    meteo_now = _meteo_now_from_window(weather, now_hour)

    if _is_fallback_meteo(meteo_now):
        logger.info("refresh_meteo: Open-Meteo+Meteostat siguen caídos, no se actualiza")
        return False

    with _lock:
        _snapshot.meteo = Meteo(**meteo_now)
    logger.info("refresh_meteo: meteo actualizado a %s", now_hour)
    return True


def get_snapshot() -> Snapshot | None:
    return _snapshot
