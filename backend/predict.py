"""Pipeline de predicción CBLA: CNN-BiLSTM (S1) + XGBoost meta-model (S2), 168 h recursivo."""
import os
import logging
from datetime import datetime, timedelta
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from .config import (
    S1_MODEL_PATH, S2_MODEL_PATH, SCALER_PATH,
    NORM_TEMP_MIN, NORM_TEMP_MAX, NORM_VIENTO_MAX,
    NORM_PRESION_MIN, NORM_PRESION_MAX, NORM_PRECIP_MAX,
    SO2_DEFAULT, CO_DEFAULT, S2_FEATURES,
)
from .stations import STATION_NAMES

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_models():
    """Carga los modelos S1 (Keras), S2 (XGBoost) y el scaler. Cacheado en memoria."""
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    from tensorflow import keras  # import perezoso para evitar coste al arrancar
    import xgboost as xgb

    logger.info("Cargando modelos CBLA desde %s", S1_MODEL_PATH.parent)
    s1 = keras.models.load_model(str(S1_MODEL_PATH))
    scaler = joblib.load(str(SCALER_PATH))
    s2 = xgb.XGBRegressor()
    s2.load_model(str(S2_MODEL_PATH))
    logger.info("Modelos CBLA cargados")
    return s1, scaler, s2


def _norm(val: float, min_val: float, max_val: float) -> float:
    return float(np.clip((val - min_val) / (max_val - min_val), 0.0, 1.0))


def _s1_row(dt: datetime, pm25: float, no2: float, o3: float, meteo: dict) -> list:
    h = dt.hour
    return [
        float(dt.weekday()),
        float(h),
        float(pm25),
        float(no2),
        float(o3),
        SO2_DEFAULT,
        CO_DEFAULT,
        _norm(meteo["Velocidad_viento"], 0,                NORM_VIENTO_MAX),
        float(meteo["Direccion_viento"]),
        _norm(meteo["Temperatura"],      NORM_TEMP_MIN,    NORM_TEMP_MAX),
        float(meteo["Humedad_relativa"]),
        _norm(meteo["Presion"],          NORM_PRESION_MIN, NORM_PRESION_MAX),
        _norm(meteo["Precipitacion"],    0,                NORM_PRECIP_MAX),
        (h - 11.5) / 6.922,
        np.sin(2 * np.pi * h / 24),
        np.cos(2 * np.pi * h / 24),
    ]


def _s2_row(s1_pred: float, dt: datetime, meteo: dict, air: dict, hist: list) -> dict:
    h = dt.hour

    def lag(n):
        return float(hist[-n]) if len(hist) >= n else float(hist[0] if hist else 15.0)

    def ma(n):
        w = hist[-n:] if len(hist) >= n else hist
        return float(np.mean(w)) if w else 15.0

    return {
        "s1_pred":          s1_pred,
        "Temperatura":      _norm(meteo["Temperatura"],      NORM_TEMP_MIN,    NORM_TEMP_MAX),
        "Humedad_relativa": meteo["Humedad_relativa"],
        "Velocidad_viento": _norm(meteo["Velocidad_viento"], 0,                NORM_VIENTO_MAX),
        "Direccion_viento": meteo["Direccion_viento"],
        "Presion":          _norm(meteo["Presion"],          NORM_PRESION_MIN, NORM_PRESION_MAX),
        "Precipitacion":    _norm(meteo["Precipitacion"],    0,                NORM_PRECIP_MAX),
        "NO2":              air.get("NO2", 25.0),
        "O3":               air.get("O3",  35.0),
        "SO2":              SO2_DEFAULT,
        "CO":               CO_DEFAULT,
        "hora_sin":         np.sin(2 * np.pi * h / 24),
        "hora_cos":         np.cos(2 * np.pi * h / 24),
        "PM25_lag_1h":      lag(1),
        "PM25_lag_6h":      lag(6),
        "PM25_lag_24h":     lag(24),
        "PM25_lag_48h":     lag(48),
        "PM25_lag_72h":     lag(72),
        "PM25_lag_120h":    lag(120),
        "PM25_lag_168h":    lag(168),
        "PM25_ma_24h":      ma(24),
        "PM25_ma_72h":      ma(72),
        "PM25_ma_168h":     ma(168),
        "dow_sin":          np.sin(2 * np.pi * dt.weekday() / 7),
        "dow_cos":          np.cos(2 * np.pi * dt.weekday() / 7),
        "month_sin":        np.sin(2 * np.pi * dt.month / 12),
        "month_cos":        np.cos(2 * np.pi * dt.month / 12),
    }


def predict_168h(air_data: dict, meteo: dict) -> dict[str, list[float]]:
    """Genera 169 valores horarios (t=0 incluido) de PM2.5 por estación.

    Devuelve un dict {station → list[float] de longitud 169}.
    """
    s1_model, scaler, s2_model = load_models()

    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    n = len(STATION_NAMES)

    # Inicializar historial 169h por estación (168h simulados + t=0)
    state: dict[str, dict] = {}
    for station in STATION_NAMES:
        air = air_data.get(station, {"O3": 35.0, "NO2": 25.0, "PM25": 15.0})
        pm25_now = air.get("PM25", 15.0)
        rng = np.random.default_rng(hash(station) % 100_000)
        hist: list[float] = []
        val = pm25_now
        for _ in range(168):
            val = max(0.0, val + rng.normal(0, 0.3))
            hist.append(val)
        hist = list(reversed(hist)) + [pm25_now]  # oldest → newest
        state[station] = {"air": air, "hist": hist}

    forecasts: dict[str, list[float]] = {
        s: [state[s]["air"].get("PM25", 15.0)] for s in STATION_NAMES
    }

    for h in range(1, 169):
        dt_h = now + timedelta(hours=h)

        # ── Stage 1: batch (n_stations, 48, 16) ──
        batch = []
        for station in STATION_NAMES:
            st = state[station]
            hist = st["hist"]
            air  = st["air"]
            win_pm25 = hist[-48:] if len(hist) >= 48 else [hist[0]] * (48 - len(hist)) + hist
            rows = [
                _s1_row(
                    dt_h - timedelta(hours=48 - i),
                    win_pm25[i],
                    air.get("NO2", 25.0),
                    air.get("O3",  35.0),
                    meteo,
                )
                for i in range(48)
            ]
            batch.append(rows)

        win_arr = np.array(batch, dtype="float32")
        win_sc  = scaler.transform(win_arr.reshape(-1, 16)).reshape(n, 48, 16)
        s1_preds = s1_model.predict(win_sc, verbose=0).ravel()

        # ── Stage 2: batch (n_stations, 27) ──
        s2_rows = [
            _s2_row(float(s1_preds[i]), dt_h, meteo, state[s]["air"], state[s]["hist"])
            for i, s in enumerate(STATION_NAMES)
        ]
        s2_df    = pd.DataFrame(s2_rows)[S2_FEATURES]
        s2_preds = np.clip(s2_model.predict(s2_df), 0, None)

        for i, station in enumerate(STATION_NAMES):
            fp = round(float(s2_preds[i]), 2)
            forecasts[station].append(fp)
            state[station]["hist"].append(fp)

    return forecasts
