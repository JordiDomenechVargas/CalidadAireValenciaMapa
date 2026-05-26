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

# Scheduler — regenera el snapshot completo (CSV + scrape GVA + meteo) cada N min
REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "60"))

# Scheduler — refresca SOLO el campo meteo del snapshot cada N min (mucho más
# frecuente que el snapshot completo). Útil para recuperarse rápido de caídas
# transitorias de Open-Meteo sin esperar al siguiente ciclo de 60 min.
METEO_REFRESH_INTERVAL_MINUTES = int(os.getenv("METEO_REFRESH_INTERVAL_MINUTES", "5"))

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


# Valores meteo por defecto cuando Open-Meteo y Meteostat fallan. Constantes
# expuestas aquí para que `snapshot.refresh_meteo()` pueda detectar si el meteo
# recibido es el fallback (en cuyo caso no se sobreescribe el último valor bueno).
METEO_FALLBACK: dict[str, float] = {
    "Velocidad_viento": 3.5,
    "Direccion_viento": 180.0,
    "Temperatura":      20.0,
    "Humedad_relativa": 60.0,
    "Presion":          1013.0,
    "Precipitacion":    0.0,
}

# URL pública del CSV de previsiones (artifact generado por el CI/CD del equipo de
# modelado en GitLab). Si está vacía, el backend usa solo el archivo local en
# backend/data/ y no descarga nada.
FORECAST_CSV_URL = os.getenv("FORECAST_CSV_URL", "")
