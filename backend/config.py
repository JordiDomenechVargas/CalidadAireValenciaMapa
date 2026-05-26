"""Configuración global del backend (variables de entorno + constantes)."""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent

# Contaminantes que la app maneja (claves internas; el frontend los muestra como
# "PM2.5", "NO₂", "O₃")
POLLUTANTS: tuple[str, ...] = ("PM25", "NO2", "O3")

# Cuántas horas atrás scrape de lecturas reales para la card "Medida GVA"
LOOKBACK_HOURS = 48

# Scheduler — regenera el snapshot cada N min (relee el CSV si cambió)
REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "60"))

# Auth simple para el endpoint POST /refresh
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")

# Open-Meteo (gratis, sin API key) — Valencia
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "39.4697"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "-0.3774"))
WEATHER_TZ  = os.getenv("WEATHER_TZ", "Europe/Madrid")


# Zona horaria local de la app. Hugging Face Spaces ejecuta los contenedores en UTC;
# usar Europe/Madrid asegura que `datetime.now()` y comparaciones temporales coincidan
# con los timestamps "naive" que generan los scrapes (RVVCCA, CSV) y la UI espera.
LOCAL_TZ = ZoneInfo(os.getenv("APP_TZ", "Europe/Madrid"))


def now_local() -> datetime:
    """Hora actual en LOCAL_TZ, devuelta como datetime *naive* (sin tzinfo).
    Usar en lugar de `datetime.now()` en todo el backend para evitar desfases entre
    UTC del servidor y la hora local que ven los usuarios."""
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)

# URL pública del CSV de previsiones (artifact generado por el CI/CD del equipo de
# modelado en GitLab). Si está vacía, el backend usa solo el archivo local en
# backend/data/ y no descarga nada.
FORECAST_CSV_URL = os.getenv("FORECAST_CSV_URL", "")
