"""Configuración global del backend (variables de entorno + constantes)."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent
MODELS_DIR  = BACKEND_DIR / "models"

# Rutas a los 4 archivos × 3 contaminantes del nuevo pipeline multi-estación.
MODEL_FILES: dict[str, dict[str, Path]] = {
    "PM25": {
        "s1":     MODELS_DIR / "cnn_bilstm_attention_pm25_multi_h1.keras",
        "scaler": MODELS_DIR / "scaler_pm25_multi_h1.pkl",
        "s2":     MODELS_DIR / "xgb_meta_model_pm25_multi_h1.json",
        "meta":   MODELS_DIR / "pm25_multi_meta_h1.pkl",
    },
    "NO2": {
        "s1":     MODELS_DIR / "cnn_bilstm_attention_no2_multi_h1.keras",
        "scaler": MODELS_DIR / "scaler_no2_multi_h1.pkl",
        "s2":     MODELS_DIR / "xgb_meta_model_no2_multi_h1.json",
        "meta":   MODELS_DIR / "no2_multi_meta_h1.pkl",
    },
    "O3": {
        "s1":     MODELS_DIR / "cnn_bilstm_attention_o3_multi_h1.keras",
        "scaler": MODELS_DIR / "scaler_o3_multi_h1.pkl",
        "s2":     MODELS_DIR / "xgb_meta_model_o3_multi_h1.json",
        "meta":   MODELS_DIR / "o3_multi_meta_h1.pkl",
    },
}

POLLUTANTS: tuple[str, ...] = ("PM25", "NO2", "O3")

# Bucle del modelo
LOOKBACK_HOURS = 48
HORIZON_HOURS  = 168

# Scheduler
REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "60"))

# Auth simple para el endpoint POST /refresh
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")

# Open-Meteo (gratis, sin API key) — Valencia
WEATHER_LAT  = float(os.getenv("WEATHER_LAT",  "39.4697"))
WEATHER_LON  = float(os.getenv("WEATHER_LON",  "-0.3774"))
WEATHER_TZ   = os.getenv("WEATHER_TZ", "Europe/Madrid")

# Defaults para variables sin medición directa (mediana del set de entrenamiento)
SO2_DEFAULT = 0.028   # mg/m³
CO_DEFAULT  = 0.075   # mg/m³
