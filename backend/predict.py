"""Pipeline de predicción multi-estación · 3 contaminantes (PM2.5, NO2, O3).

Cada contaminante tiene su propio CNN-BiLSTM (S1, 48 h lookback) + XGBoost (S2, meta-
model con OHE de estación). El bucle es recursivo: arranca con las últimas 48 h reales
(scrape) y avanza hora a hora retroalimentándose con sus propias predicciones, usando
el forecast meteorológico de Open-Meteo para las horas futuras.

Las 3 predicciones (PM2.5, NO2, O3) se hacen simultáneamente en cada paso porque son
inputs unos de otros (el modelo PM2.5 usa NO2, O3 como features, etc.).
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from .config import (
    MODEL_FILES, POLLUTANTS, LOOKBACK_HOURS, HORIZON_HOURS,
    SO2_DEFAULT, CO_DEFAULT,
)
from .stations import (
    STATION_NAMES, MODEL_NAME_TO_CANONICAL, CANONICAL_TO_MODEL_NAME,
)

logger = logging.getLogger(__name__)

# Claves de contaminantes manejadas en el state recursivo
_GAS_KEYS = ("PM25", "NO2", "O3", "SO2", "CO")
_METEO_COLS = ("Temperatura", "Humedad_relativa", "Velocidad_viento",
               "Direccion_viento", "Presion", "Precipitacion")


# ── Carga de modelos (cacheado en memoria) ────────────────────────────────────

@lru_cache(maxsize=1)
def load_models() -> dict[str, dict]:
    """Devuelve {pollutant → {s1, scaler, s2, meta, supported_stations}}.

    `supported_stations` es la lista de estaciones canónicas (nombre nuestro) que el
    modelo puede predecir — intersección entre el catálogo del meta y nuestro STATIONS.
    """
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    from tensorflow import keras
    import xgboost as xgb

    out: dict[str, dict] = {}
    for pollutant in POLLUTANTS:
        files = MODEL_FILES[pollutant]
        logger.info("Cargando modelo %s …", pollutant)

        s1 = keras.models.load_model(str(files["s1"]))
        scaler = joblib.load(str(files["scaler"]))
        s2 = xgb.XGBRegressor()
        s2.load_model(str(files["s2"]))
        meta = joblib.load(str(files["meta"]))

        # Lista de estaciones del modelo (en sus propios nombres) → canónicas nuestras
        model_stations = meta.get("stations_pm25") or meta.get("stations") or []
        supported_canon: list[str] = []
        for model_name in model_stations:
            canon = MODEL_NAME_TO_CANONICAL.get(model_name)
            if canon and canon in STATION_NAMES:
                supported_canon.append(canon)
        # Mantener el orden del meta (importante para la indexación OHE)

        out[pollutant] = {
            "s1": s1,
            "scaler": scaler,
            "s2": s2,
            "meta": meta,
            "supported": supported_canon,
        }
        logger.info("  · %s: %d estaciones soportadas, %d s1 features, %d s2 features",
                    pollutant, len(supported_canon),
                    len(meta["s1_feature_cols"]),
                    len(meta["stage2_extra_cols"]) + 1 + len(meta["station_ohe_cols"]))
    return out


def get_supported_stations() -> dict[str, list[str]]:
    """Devuelve {pollutant → list of canonical station names supported}."""
    return {p: load_models()[p]["supported"] for p in POLLUTANTS}


# ── Construcción de features ──────────────────────────────────────────────────

def _hour_sin(h: int) -> float:  return float(np.sin(2 * np.pi * h / 24))
def _hour_cos(h: int) -> float:  return float(np.cos(2 * np.pi * h / 24))
def _dow_sin(d: int)  -> float:  return float(np.sin(2 * np.pi * d / 7))
def _dow_cos(d: int)  -> float:  return float(np.cos(2 * np.pi * d / 7))
def _mon_sin(m: int)  -> float:  return float(np.sin(2 * np.pi * m / 12))
def _mon_cos(m: int)  -> float:  return float(np.cos(2 * np.pi * m / 12))


def _s1_feature_value(col: str, ti: datetime, state_t: dict[str, float],
                      meteo_t: dict[str, float]) -> float:
    """Devuelve el valor de una feature S1 en el instante `ti`.

    `state_t` son los valores de los gases (PM25/NO2/O3/SO2/CO) en ese instante.
    `meteo_t` son los meteo en ese instante.
    """
    if col == "Dia_semana": return float(ti.weekday())
    if col == "Hora":       return float(ti.hour)
    if col == "Hora_num":   return (ti.hour - 11.5) / 6.922
    if col == "hora_sin":   return _hour_sin(ti.hour)
    if col == "hora_cos":   return _hour_cos(ti.hour)
    if col in _GAS_KEYS:    return float(state_t.get(col, 0.0))
    if col in _METEO_COLS:  return float(meteo_t.get(col, 0.0))
    # Por si el meta tiene una feature que no hemos mapeado
    logger.debug("Feature S1 desconocida '%s' · usando 0.0", col)
    return 0.0


def _s2_feature_value(col: str, t: datetime, state: dict[str, list[float]],
                      meteo_t: dict[str, float], target: str) -> float:
    """Devuelve el valor de una feature S2 (stage2_extra_cols) en t.

    `state[gas]` son las series completas hasta `t-1` (las más recientes están al final).
    El último elemento `state[gas][-1]` es el valor del gas a `t-1` (lag 1).
    """
    # Meteo y gases actuales (a t-1, la última observación/predicción disponible)
    if col in _METEO_COLS:        return float(meteo_t.get(col, 0.0))
    if col in _GAS_KEYS:          return float(state[col][-1])
    if col == "hora_sin":         return _hour_sin(t.hour)
    if col == "hora_cos":         return _hour_cos(t.hour)
    if col == "dow_sin":          return _dow_sin(t.weekday())
    if col == "dow_cos":          return _dow_cos(t.weekday())
    if col == "month_sin":        return _mon_sin(t.month)
    if col == "month_cos":        return _mon_cos(t.month)

    # Features específicas de O3
    if col == "hour_sin_gas":     return _hour_sin(t.hour)
    if col == "hour_cos_gas":     return _hour_cos(t.hour)
    if col == "is_morning_drop":  return 1.0 if 6 <= t.hour <= 10 else 0.0
    if col == "no2_minus_o3_lag1":
        return float(state["NO2"][-1] - state["O3"][-1])
    if col == "o3_to_no2_ratio":
        return float(state["O3"][-1] / max(state["NO2"][-1], 1e-6))

    # Patrones: <TARGET>_lag_<N>h, <TARGET>_ma_<N>h, <TARGET>_delta_<N>h
    if "_lag_" in col and col.endswith("h"):
        gas, _, lag_part = col.partition("_lag_")
        if gas.upper() in _GAS_KEYS:
            n = int(lag_part[:-1])
            series = state[gas.upper()]
            return float(series[-n]) if len(series) >= n else float(series[0])

    if "_ma_" in col and col.endswith("h"):
        gas, _, win_part = col.partition("_ma_")
        if gas.upper() in _GAS_KEYS:
            n = int(win_part[:-1])
            series = state[gas.upper()][-n:]
            return float(np.mean(series)) if series else 0.0

    if "_delta_" in col and col.endswith("h"):
        gas, _, n_part = col.partition("_delta_")
        if gas.upper() in _GAS_KEYS:
            n = int(n_part[:-1])
            series = state[gas.upper()]
            if len(series) >= n + 1:
                return float(series[-1] - series[-1 - n])
            return 0.0

    logger.debug("Feature S2 desconocida '%s' · usando 0.0", col)
    return 0.0


# ── Bucle recursivo ───────────────────────────────────────────────────────────

def predict_all_pollutants(
    air_history: dict[str, list[dict]],
    weather: dict[datetime, dict[str, float]],
) -> tuple[dict[str, dict[str, list[float]]], datetime]:
    """Bucle recursivo de 168 h.

    Args:
      air_history: 48 h por estación, ordenadas cronológicamente, con PM25/NO2/O3/SO2/CO.
      weather: dict[datetime → meteo cols] que cubre las últimas 48 h pasadas + 168 h futuro.

    Returns:
      (forecasts, last_real_hour) donde:
        forecasts[pollutant][station] = list de 169 valores (idx 0 = now, idx 168 = +7d).
        last_real_hour = timestamp de la última fila real (referencia para el frontend).
    """
    models = load_models()
    supported = {p: models[p]["supported"] for p in POLLUTANTS}

    # Última hora real: la más reciente de cualquier fila no nula del scrape.
    all_dates = [r["date"] for rows in air_history.values() for r in rows if r.get("date")]
    last_real_hour = max(all_dates) if all_dates else datetime.now().replace(minute=0, second=0, microsecond=0)
    last_real_hour = last_real_hour.replace(minute=0, second=0, microsecond=0)

    now_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    gap_hours = max(0, int((now_hour - last_real_hour).total_seconds() / 3600))

    # Total de pasos: catch-up del lag + horizonte de 168 h
    total_steps = gap_hours + HORIZON_HOURS

    logger.info("Bucle recursivo · last_real=%s · now=%s · gap=%dh · total_steps=%d",
                last_real_hour, now_hour, gap_hours, total_steps)

    # ── Inicializar state ─────
    # state[station][gas] = list[float] con LOOKBACK_HOURS valores (extremo derecho = más reciente)
    state: dict[str, dict[str, list[float]]] = {}
    for station in STATION_NAMES:
        rows = air_history.get(station, [])
        # Tomar los últimos LOOKBACK_HOURS, rellenando huecos con el último valor visto
        last_seen = {"PM25": 15.0, "NO2": 25.0, "O3": 35.0, "SO2": float(SO2_DEFAULT), "CO": float(CO_DEFAULT)}
        series = {g: [] for g in _GAS_KEYS}
        for r in rows[-LOOKBACK_HOURS:]:
            for g in _GAS_KEYS:
                v = r.get(g)
                if v is not None:
                    last_seen[g] = float(v)
                series[g].append(last_seen[g])
        # Asegurar exactamente LOOKBACK_HOURS valores (pad por delante con el primero si falta)
        for g in _GAS_KEYS:
            if not series[g]:
                series[g] = [last_seen[g]] * LOOKBACK_HOURS
            elif len(series[g]) < LOOKBACK_HOURS:
                pad = LOOKBACK_HOURS - len(series[g])
                series[g] = [series[g][0]] * pad + series[g]
        state[station] = series

    # ── Resultados crudos ─────
    # raw[pollutant][station] = list[total_steps]
    raw: dict[str, dict[str, list[float]]] = {p: {s: [] for s in supported[p]} for p in POLLUTANTS}

    # ── Bucle ─────
    for step in range(total_steps):
        t = last_real_hour + timedelta(hours=step + 1)

        for pollutant in POLLUTANTS:
            mdl = models[pollutant]
            meta = mdl["meta"]
            s1_cols = meta["s1_feature_cols"]
            station_to_idx = meta["station_to_idx"]
            station_ohe_cols = meta["station_ohe_cols"]
            stage2_extra_cols = meta["stage2_extra_cols"]
            n_s1_feats = len(s1_cols)
            n_ohe = len(station_ohe_cols)

            sup = supported[pollutant]
            if not sup:
                continue

            # ── S1: construir batch (n_stations, 48, n_s1_feats) ──
            batch = np.zeros((len(sup), LOOKBACK_HOURS, n_s1_feats), dtype=np.float32)
            for s_idx, station in enumerate(sup):
                series = state[station]
                for i in range(LOOKBACK_HOURS):
                    ti = t - timedelta(hours=LOOKBACK_HOURS - i)
                    # Estado del gas en ti: el valor está en series[-(LOOKBACK_HOURS - i)]
                    # (i=0 → -48 → más antiguo; i=47 → -1 → más reciente, t-1)
                    state_ti = {g: series[g][-(LOOKBACK_HOURS - i)] for g in _GAS_KEYS}
                    meteo_ti = weather.get(ti, {})
                    for j, col in enumerate(s1_cols):
                        batch[s_idx, i, j] = _s1_feature_value(col, ti, state_ti, meteo_ti)

            # Escalar (n*48, n_feats) y reshapear
            batch_sc = mdl["scaler"].transform(batch.reshape(-1, n_s1_feats)).reshape(len(sup), LOOKBACK_HOURS, n_s1_feats)
            s1_preds = mdl["s1"].predict(batch_sc, verbose=0).ravel()  # (n_stations,)

            # ── S2: construir DataFrame (n_stations, 1 + len(extra) + n_ohe) ──
            meteo_t = weather.get(t, {})
            rows_s2 = []
            for s_idx, station in enumerate(sup):
                row = {"s1_pred": float(s1_preds[s_idx])}
                for col in stage2_extra_cols:
                    row[col] = _s2_feature_value(col, t, state[station], meteo_t, target=pollutant)
                # OHE de estación
                model_name = CANONICAL_TO_MODEL_NAME[station]
                st_idx = station_to_idx[model_name]
                for ohe_col in station_ohe_cols:
                    row[ohe_col] = 0.0
                row[station_ohe_cols[st_idx]] = 1.0
                rows_s2.append(row)

            s2_df = pd.DataFrame(rows_s2)
            # Orden de columnas: el XGBoost necesita el mismo orden que en training.
            # Asumimos: s1_pred → stage2_extra → station_ohe_cols (el orden estándar).
            col_order = ["s1_pred"] + stage2_extra_cols + station_ohe_cols
            s2_df = s2_df[col_order]
            s2_preds = np.clip(mdl["s2"].predict(s2_df), 0, None)

            for s_idx, station in enumerate(sup):
                raw[pollutant][station].append(float(s2_preds[s_idx]))

        # ── Anexar predicciones a state (para alimentar el siguiente paso) ──
        for station in STATION_NAMES:
            for pollutant in POLLUTANTS:
                if station in raw[pollutant]:
                    new_val = raw[pollutant][station][-1]
                else:
                    # Estación no soportada por este modelo: propagar el último valor real
                    new_val = state[station][pollutant][-1]
                state[station][pollutant].append(new_val)
            # SO2 y CO no se predicen — mantener constantes
            state[station]["SO2"].append(state[station]["SO2"][-1])
            state[station]["CO"].append(state[station]["CO"][-1])

    # ── Recortar y devolver 169 valores ─────
    # results[pollutant][station][i] = predicción a now_hour + i (i=0..168).
    # Step k del bucle predice a t = last_real + k+1. Para t = now+i:
    #   last_real + k+1 = now + i = last_real + gap + i ⟹ k = gap + i - 1.
    # Por tanto results[i] = raw[gap-1 + i] para i=0..168 ⟹ slice raw[gap-1 : gap-1+169].
    # Caso gap=0: no existe raw[-1], así que results[0] = última lectura real (state[-(168+1)] o el valor que estaba en el estado al inicio).
    results: dict[str, dict[str, list[float]]] = {}
    for pollutant in POLLUTANTS:
        results[pollutant] = {}
        for station, values in raw[pollutant].items():
            if gap_hours >= 1:
                sliced = values[gap_hours - 1 : gap_hours - 1 + HORIZON_HOURS + 1]
            else:
                # gap == 0: anteponer el valor real "ahora" (el último del state inicial,
                # que es state[station][pollutant] en su posición LOOKBACK-1 antes del bucle).
                real_now = state[station][pollutant][LOOKBACK_HOURS - 1]
                sliced = [real_now] + values[: HORIZON_HOURS]
            if len(sliced) < HORIZON_HOURS + 1:
                last = sliced[-1] if sliced else 0.0
                sliced = sliced + [last] * (HORIZON_HOURS + 1 - len(sliced))
            results[pollutant][station] = [round(v, 2) for v in sliced]

    return results, last_real_hour
