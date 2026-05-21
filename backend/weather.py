"""Cliente Open-Meteo: meteo histórica + forecast hora a hora para Valencia.

Open-Meteo es gratuita, sin API key, y devuelve hasta 16 días hourly. La pedimos en
una sola llamada con ventana `past_days=2 & forecast_days=8` → 240 horas: ~48 h pasadas
para alimentar el lookback del modelo + 168 h futuras para el bucle recursivo.
"""
import logging
from datetime import datetime

import requests

from .config import WEATHER_LAT, WEATHER_LON, WEATHER_TZ
from .scrape import fetch_meteo_now

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Mapeo de campos Open-Meteo → nuestras claves internas
_FIELD_MAP = {
    "temperature_2m":       "Temperatura",
    "relative_humidity_2m": "Humedad_relativa",
    "pressure_msl":         "Presion",
    "wind_speed_10m":       "Velocidad_viento",
    "wind_direction_10m":   "Direccion_viento",
    "precipitation":        "Precipitacion",
}


def fetch_weather_window() -> dict[datetime, dict[str, float]]:
    """Devuelve dict[datetime → dict[col → float]] con ~240 h indexadas por hora local
    (Europe/Madrid). Cubre ~48 h pasadas + 168 h futuras.

    Si la API falla, replica `fetch_meteo_now()` en todas las horas del rango (no es
    ideal para el modelo pero no rompe el bucle recursivo).
    """
    params = {
        "latitude":  WEATHER_LAT,
        "longitude": WEATHER_LON,
        "hourly":    ",".join(_FIELD_MAP.keys()),
        "timezone":  WEATHER_TZ,
        "past_days": 2,
        "forecast_days": 8,
    }
    try:
        resp = requests.get(_OPEN_METEO_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        hourly = data["hourly"]
        times  = hourly["time"]

        result: dict[datetime, dict[str, float]] = {}
        for i, ts_str in enumerate(times):
            dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M")
            row = {}
            for src, dst in _FIELD_MAP.items():
                val = hourly[src][i]
                if val is None:
                    continue
                row[dst] = float(val)
            result[dt] = row
        logger.info("Open-Meteo OK · %d horas cargadas (%s → %s)",
                    len(result), times[0], times[-1])
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("Open-Meteo falló (%s) · usando meteo actual de Meteostat en todas las horas", e)
        fallback_meteo = fetch_meteo_now()
        # Si no podemos obtener forecasts, devolvemos un dict vacío y dejamos que el
        # caller use fallback_meteo. Aquí devolvemos un dict que ante cualquier key
        # devuelve el meteo "ahora" — pero un dict normal no hace esto, así que el
        # caller debe defender ante missing keys.
        return _ConstantMeteo(fallback_meteo)


class _ConstantMeteo(dict):
    """Dict-like que devuelve el mismo meteo independientemente de la clave datetime.

    Útil cuando Open-Meteo falla y queremos seguir teniendo previsiones (degradadas)
    sin que el bucle recursivo se rompa por KeyError."""
    def __init__(self, constant: dict[str, float]):
        super().__init__()
        self._constant = constant

    def __getitem__(self, _key):  # noqa: ARG002
        return self._constant

    def get(self, _key, default=None):  # noqa: ARG002
        return self._constant
