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

# Endpoint Pentaho directo (bi.pica.gva.es). El proxy rvvcca.pica.gva.es/downloadformat
# que usábamos antes devuelve 500 de forma intermitente; llamamos directamente al backend.
_RVVCCA_JSON_TPL = (
    "https://bi.pica.gva.es/pentaho/plugin/cda/api/doQuery"
    "?_TRUST_USER_=opendata_gva"
    "&path=/public/gva/verticals/sql/hourlyAverage.cda"
    "&dataAccessId=HourlyAverage"
    "&paramstart={start}%2000%3A00%3A00"
    "&paramfinish={finish}%2023%3A59%3A59"
    "&paramidStation={code}"
)

# Mapeo mgabb (abreviatura Pentaho) → clave interna
_MGABB_TO_GAS: dict[str, str] = {
    "PM2.5": "PM25",
    "NO2":   "NO2",
    "O3":    "O3",
    "SO2":   "SO2",
    "CO":    "CO",
}

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


def _parse_pentaho(data: dict) -> list[dict]:
    """Convierte la respuesta JSON de Pentaho {metadata, resultset} a una lista de
    {date, PM25, NO2, O3, SO2, CO} agrupada por hora. Cada fila de resultset representa
    una medición de UN contaminante; aquí las agrupamos por timestamp."""
    meta_idx = {col["colName"]: col["colIndex"] for col in data.get("metadata", [])}
    i_abb  = meta_idx.get("mgabb", 3)
    i_val  = meta_idx.get("value", 7)
    i_date = meta_idx.get("date",  9)

    by_dt: dict[datetime, dict] = {}
    for row in data.get("resultset", []):
        gas = _MGABB_TO_GAS.get(row[i_abb])
        if gas is None:
            continue
        val = _safe_float(row[i_val])
        if val is None:
            continue
        # El timestamp de Pentaho puede ser "2026-05-27 18:00:00.0" → truncamos a minuto
        date_str = str(row[i_date])[:16]
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if dt not in by_dt:
            by_dt[dt] = {"date": dt, "PM25": None, "NO2": None, "O3": None, "SO2": None, "CO": None}
        by_dt[dt][gas] = val

    # Solo filas con al menos uno de los tres gases principales
    result = [r for r in by_dt.values() if any(r[g] is not None for g in ("PM25", "NO2", "O3"))]
    result.sort(key=lambda r: r["date"])
    return result


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
            data = resp.json()
            if not isinstance(data, dict) or "resultset" not in data:
                return name, []

            parsed = _parse_pentaho(data)
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
