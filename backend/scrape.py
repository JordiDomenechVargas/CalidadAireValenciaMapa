"""Scraping de calidad del aire (RVVCCA Pentaho JSON) y meteorología (Meteostat)."""
import re
import time
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from .stations import STATION_CODES, STATION_NAMES

logger = logging.getLogger(__name__)

# Endpoint JSON de la RVVCCA — devuelve mediciones horarias del intervalo [start, finish].
# Se descubrió desde /es/getmeasurementsbystation/{drupal_id} (página "Histórico de mediciones").
_RVVCCA_JSON_TPL = (
    "https://rvvcca.pica.gva.es/downloadformat/hourly/cda/json?file="
    "https://bi.pica.gva.es/pentaho/plugin/cda/api/doQuery?_TRUST_USER_=opendata_gva"
    "&path=/public/gva/verticals/sql/hourlyAverage.cda"
    "&dataAccessId=HourlyAverage"
    "&paramstart={start}%2000%3A00%3A00"
    "&paramfinish={finish}%2023%3A59%3A59"
    "&paramidStation={code}"
)

_METEO_URL_TPL = "https://meteostat.net/es/station/08284?t={date}/{date}"

_AIR_FALLBACK = {"O3": 35.0, "NO2": 25.0, "PM25": 15.0}
_METEO_FALLBACK = {
    "Velocidad_viento": 3.5,
    "Direccion_viento": 180.0,
    "Temperatura": 20.0,
    "Humedad_relativa": 60.0,
    "Presion": 1013.0,
    "Precipitacion": 0.0,
}


_HTTP_RETRIES = 3
_HTTP_BACKOFF_S = 1.5
_MAX_PARALLEL = 2   # El backend Pentaho devuelve 500 si recibe muchas peticiones simultáneas


def _fetch_station_latest(name: str, code: str) -> tuple[str, dict | None]:
    """Devuelve (nombre, dict con las últimas mediciones no nulas) o (nombre, None).

    Reintenta hasta `_HTTP_RETRIES` veces con backoff exponencial si el endpoint
    responde 500 (Pentaho a veces se satura) o hay un timeout transitorio.
    """
    today   = datetime.now().strftime("%Y-%m-%d")
    start   = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url     = _RVVCCA_JSON_TPL.format(start=start, finish=today, code=code)
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    for attempt in range(1, _HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.reason}", response=resp)
            resp.raise_for_status()
            rows = resp.json()
            if not isinstance(rows, list) or not rows:
                return name, None

            # De la última hora hacia atrás, devolver la primera con alguna lectura útil.
            for row in reversed(rows):
                pm25 = row.get("PM2.5")
                no2  = row.get("NO2")
                o3   = row.get("O3")
                if pm25 is None and no2 is None and o3 is None:
                    continue
                record = {}
                if pm25 is not None: record["PM25"] = float(pm25)
                if no2  is not None: record["NO2"]  = float(no2)
                if o3   is not None: record["O3"]   = float(o3)
                return name, {**_AIR_FALLBACK, **record}
            return name, None
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as e:
            if attempt < _HTTP_RETRIES:
                wait = _HTTP_BACKOFF_S * (2 ** (attempt - 1))
                logger.info("fetch %s (intento %d/%d) → %s · reintentando en %.1fs",
                            name, attempt, _HTTP_RETRIES, e, wait)
                time.sleep(wait)
                continue
            logger.warning("fetch %s (%s) falló tras %d intentos: %s",
                           name, code, _HTTP_RETRIES, e)
            return name, None
        except Exception as e:  # noqa: BLE001
            logger.warning("fetch %s (%s) error inesperado: %s", name, code, e)
            return name, None


def fetch_air_quality() -> dict[str, dict]:
    """Extrae O3, NO2 y PM2.5 de la red RVVCCA para cada estación.

    Usa el endpoint JSON oficial de la GVA (`HourlyAverage.cda` via Pentaho), con
    paralelismo limitado a 2 hilos para no saturar el backend (que devuelve 500 con
    >3 peticiones simultáneas). Cada estación tiene reintentos con backoff.
    Si una estación falla definitivamente, se usa el fallback fijo (no aleatorio)
    para que las predicciones sean estables entre refrescos.
    """
    data: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
        futures = [pool.submit(_fetch_station_latest, name, code)
                   for name, code in STATION_CODES.items()]
        for f in as_completed(futures):
            name, record = f.result()
            if record is not None:
                data[name] = record

    for name in STATION_NAMES:
        if name not in data:
            logger.warning("Sin datos para %s — usando fallback fijo", name)
            data[name] = _AIR_FALLBACK.copy()

    return data


def fetch_meteo(date_str: str | None = None) -> dict:
    """Obtiene datos meteorológicos de Meteostat para Valencia (estación 08284)."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(_METEO_URL_TPL.format(date=date_str), headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        patterns = {
            "Temperatura":      r"Temperatura[\s:]+(-?\d+[\.,]\d+|\d+)\s*°C",
            "Humedad_relativa": r"Humedad[\s:]+(\d+[\.,]?\d*)\s*%",
            "Presion":          r"Presi[oó]n[\s:]+(\d+[\.,]?\d*)\s*hPa",
            "Velocidad_viento": r"Viento[\s:]+(\d+[\.,]?\d*)\s*km/h",
            "Precipitacion":    r"Precipitaci[oó]n[\s:]+(\d+[\.,]?\d*)\s*mm",
        }
        meteo: dict = {}
        for key, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                meteo[key] = float(m.group(1).replace(",", "."))

        meteo.setdefault("Direccion_viento", 180.0)
        return {**_METEO_FALLBACK, **meteo}
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_meteo failed, using fallback values: %s", e)
        return _METEO_FALLBACK
