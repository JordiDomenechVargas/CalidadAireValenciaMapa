"""Configuración global del backend (variables de entorno + constantes)."""
import os
from pathlib import Path
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
