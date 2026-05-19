"""Configuración global del backend (variables de entorno + constantes)."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent
MODELS_DIR  = BACKEND_DIR / "models"

# Modelos del pipeline CBLA
S1_MODEL_PATH = MODELS_DIR / "cnn_bilstm_attention_h1.keras"
SCALER_PATH   = MODELS_DIR / "scaler_h1.pkl"
S2_MODEL_PATH = MODELS_DIR / "xgb_meta_model_h1.json"

# Scheduler
REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "60"))

# Auth simple para el endpoint POST /refresh
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")

# Parámetros de normalización min-max del entrenamiento (deben coincidir con el notebook)
NORM_TEMP_MIN    = float(os.getenv("NORM_TEMP_MIN",    "0"))
NORM_TEMP_MAX    = float(os.getenv("NORM_TEMP_MAX",    "40"))
NORM_VIENTO_MAX  = float(os.getenv("NORM_VIENTO_MAX",  "100"))
NORM_PRESION_MIN = float(os.getenv("NORM_PRESION_MIN", "980"))
NORM_PRESION_MAX = float(os.getenv("NORM_PRESION_MAX", "1040"))
NORM_PRECIP_MAX  = float(os.getenv("NORM_PRECIP_MAX",  "50"))

# Defaults para variables sin medición directa (mediana del set de entrenamiento)
SO2_DEFAULT = 0.028   # mg/m³
CO_DEFAULT  = 0.075   # mg/m³

# Features del pipeline CBLA (orden exacto del entrenamiento)
S1_FEATURES = [
    "Dia_semana", "Hora", "PM25", "NO2", "O3", "SO2", "CO",
    "Velocidad_viento", "Direccion_viento", "Temperatura",
    "Humedad_relativa", "Presion", "Precipitacion", "Hora_num",
    "hora_sin", "hora_cos",
]
S2_FEATURES = [
    "s1_pred", "Temperatura", "Humedad_relativa", "Velocidad_viento",
    "Direccion_viento", "Presion", "Precipitacion", "NO2", "O3", "SO2", "CO",
    "hora_sin", "hora_cos",
    "PM25_lag_1h", "PM25_lag_6h", "PM25_lag_24h", "PM25_lag_48h",
    "PM25_lag_72h", "PM25_lag_120h", "PM25_lag_168h",
    "PM25_ma_24h", "PM25_ma_72h", "PM25_ma_168h",
    "dow_sin", "dow_cos", "month_sin", "month_cos",
]
