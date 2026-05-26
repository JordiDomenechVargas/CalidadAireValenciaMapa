"""Scraping de calidad del aire (RVVCCA Pentaho JSON) y meteo de fallback (Meteostat)."""
import re
import time
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from .stations import STATION_CODES, STATION_NAMES
from .config import LOOKBACK_HOURS, now_local, METEO_FALLBACK

logger = logging.getLogger(__name__)

# Endpoint JSON de la RVVCCA — devuelve mediciones horarias del intervalo [start, finish].
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

_AIR_FALLBACK = {"O3": 35.0, "NO2": 25.0, "PM25": 15.0, "SO2": 4.0, "CO": 0.3}
# Reexport para evitar romper imports antiguos
_METEO_FALLBACK = METEO_FALLBACK

_HTTP_RETRIES = 3
_HTTP_BACKOFF_S = 1.5
_MAX_PARALLEL = 2   # El backend Pentaho devuelve 500 si recibe muchas peticiones simultáneas


def _safe_float(v) -> float | None:
    """Convierte a float si es posible. Acepta None, string vacío y números."""
    if v is None or v == "" or v == "null":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_row(row: dict) -> dict | None:
    """Normaliza una fila del JSON a {date, PM25, NO2, O3, SO2, CO}. None si no hay nada útil."""
    pm25 = _safe_float(row.get("PM2.5"))
    no2  = _safe_float(row.get("NO2"))
    o3   = _safe_float(row.get("O3"))
    so2  = _safe_float(row.get("SO2"))
    co   = _safe_float(row.get("CO"))
    if pm25 is None and no2 is None and o3 is None:
        return None
    try:
        dt = datetime.strptime(row["date"], "%Y-%m-%d %H:%M")
    except (KeyError, ValueError):
        return None
    return {"date": dt, "PM25": pm25, "NO2": no2, "O3": o3, "SO2": so2, "CO": co}


def _fetch_station_history(name: str, code: str) -> tuple[str, list[dict]]:
    """Devuelve (nombre, lista de filas) con las últimas ~LOOKBACK_HOURS horas no nulas."""
    # Pedimos 3 días para tener margen: el endpoint Pentaho corta hasta el final del día
    # finish, así que para garantizar ≥48 h no nulas pedimos ventana amplia.
    _now = now_local()
    finish = _now.strftime("%Y-%m-%d")
    start  = (_now - timedelta(days=3)).strftime("%Y-%m-%d")
    url    = _RVVCCA_JSON_TPL.format(start=start, finish=finish, code=code)
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    for attempt in range(1, _HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=25)
            if resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.reason}", response=resp)
            resp.raise_for_status()
            rows = resp.json()
            if not isinstance(rows, list):
                return name, []

            parsed = [r for r in (_parse_row(row) for row in rows) if r is not None]
            parsed.sort(key=lambda r: r["date"])
            # Devolvemos hasta las últimas LOOKBACK_HOURS filas (el bucle del modelo necesita 48).
            return name, parsed[-LOOKBACK_HOURS:]

        except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as e:
            if attempt < _HTTP_RETRIES:
                wait = _HTTP_BACKOFF_S * (2 ** (attempt - 1))
                logger.info("fetch %s (intento %d/%d) → %s · reintentando en %.1fs",
                            name, attempt, _HTTP_RETRIES, e, wait)
                time.sleep(wait)
                continue
            logger.warning("fetch %s (%s) falló tras %d intentos: %s",
                           name, code, _HTTP_RETRIES, e)
            return name, []
        except Exception as e:  # noqa: BLE001
            logger.warning("fetch %s (%s) error inesperado: %s", name, code, e)
            return name, []
    return name, []


def fetch_air_quality() -> dict[str, list[dict]]:
    """Devuelve el historial reciente (hasta ~48 h) por estación.

    Cada entrada es `{date: datetime, PM25, NO2, O3, SO2, CO}` (los valores pueden ser
    None si la GVA no publicó esa hora para ese contaminante). Si la GVA falla para
    una estación, su lista quedará vacía → `last_real_reading` devolverá None para
    sus gases y el frontend mostrará "—". NUNCA se inventan valores fake.
    """
    data: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
        futures = [pool.submit(_fetch_station_history, name, code)
                   for name, code in STATION_CODES.items()]
        for f in as_completed(futures):
            name, rows = f.result()
            data[name] = rows

    # Estaciones sin datos: se quedan con lista vacía. NO sintetizamos valores
    # fake porque acabarían mostrándose en la card "Medida GVA" como si fueran
    # mediciones reales.
    for name in STATION_NAMES:
        if name not in data:
            data[name] = []
        if not data[name]:
            logger.warning("Sin datos GVA para %s — la card 'Medida GVA' mostrará '—'", name)

    return data


def last_real_reading(history: dict[str, list[dict]]) -> dict[str, dict]:
    """Última lectura real por estación y gas. Devuelve `None` para gases que la
    estación no publica (no rellena con fallback)."""
    out: dict[str, dict] = {}
    for station, rows in history.items():
        rec: dict[str, float | None] = {"O3": None, "NO2": None, "PM25": None}
        # Recorrer de más reciente a más antiguo; cada gas se rellena con su
        # último valor real disponible (independientemente de los demás).
        for row in reversed(rows):
            for gas in ("PM25", "NO2", "O3"):
                if rec[gas] is None and row.get(gas) is not None:
                    rec[gas] = float(row[gas])
            if all(rec[g] is not None for g in ("PM25", "NO2", "O3")):
                break
        out[station] = rec
    return out


# ── Fallback meteorológico (sólo para el "ahora", no para el forecast 168h) ──

def fetch_meteo_now(date_str: str | None = None) -> dict:
    """Obtiene los valores meteo actuales de Meteostat para Valencia. Usado sólo como
    fallback cuando Open-Meteo no responde, o para alimentar el campo `meteo` del
    Snapshot que representa el estado meteo a t=0."""
    if date_str is None:
        date_str = now_local().strftime("%Y-%m-%d")

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
        logger.warning("fetch_meteo_now failed, using fallback: %s", e)
        return _METEO_FALLBACK
