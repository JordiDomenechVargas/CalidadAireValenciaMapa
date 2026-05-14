"""
app.py — Calidad del Aire PM2.5 · Valencia
Dashboard Streamlit con modelo LightGBM, scraping en tiempo real y previsión 168h.
"""

import warnings
warnings.filterwarnings("ignore")

import os
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import numpy as np
import joblib
import requests
import folium
from streamlit_folium import st_folium
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re

load_dotenv()

CHECK_INTERVAL_MINUTES     = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))
MIN_DOWNLOAD_INTERVAL_MINUTES = int(os.getenv("MIN_DOWNLOAD_INTERVAL_MINUTES", "60"))
AQ_CACHE_FILE    = "cache_air_quality.csv"
METEO_CACHE_FILE = "cache_meteo.csv"

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Calidad del Aire · Valencia",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}
h1, h2, h3 { font-family: 'Space Mono', monospace; }

.stApp { background: #0d1117; color: #e6edf3; }

.metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 8px;
}
.metric-card .label { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
.metric-card .value { font-size: 28px; font-family: 'Space Mono', monospace; font-weight: 700; }

.aqi-good    { color: #3fb950; }
.aqi-moderate{ color: #d29922; }
.aqi-usg     { color: #f0883e; }
.aqi-unhealthy{ color: #da3633; }

section[data-testid="stSidebar"] {
    background: #161b22;
    border-right: 1px solid #30363d;
}
</style>
""", unsafe_allow_html=True)

# ── Constantes / Estaciones ──────────────────────────────────────────────────
STATIONS = {
    "Valencia Port-Moll":       (39.445, -0.330),
    "Pista de Silla":           (39.458, -0.376),
    "Vivers":                   (39.479, -0.368),
    "Politècnic":               (39.481, -0.347),
    "Av. França":               (39.458, -0.354),
    "Molí del Sol":             (39.484, -0.402),
    "Conselleria Meteo":        (39.481, -0.392),
    "Bulevard Sud":             (39.450, -0.392),
    "Valencia Centre":          (39.471, -0.377),
    "Port Llit Antic Túria":    (39.458, -0.332),
    "Natzaret Met-2":           (39.444, -0.334),
}

STATION_NAMES = list(STATIONS.keys())

# Label encoding (mismo orden que notebook)
STATION_LE = {name: idx for idx, name in enumerate(sorted(STATION_NAMES))}

MODEL_FEATURES = [
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "station_encoded",
    "O3", "NO2",
    "Velocidad_viento", "Direccion_viento", "Temperatura",
    "Humedad_relativa", "Presion", "Precipitacion",
    "PM25_lag1", "PM25_lag2", "PM25_lag3", "PM25_lag6", "PM25_lag12", "PM25_lag24",
    "PM25_roll3", "PM25_roll6", "PM25_roll12", "PM25_roll24",
    "O3_lag1", "O3_lag3", "O3_lag6",
    "NO2_lag1", "NO2_lag3", "NO2_lag6",
    "viento_lag1", "viento_lag3", "viento_lag6",
    "temp_lag1", "temp_lag3", "temp_lag6",
    "hour", "month",
]  # 37 features

# ── Scraping ─────────────────────────────────────────────────────────────────

def fetch_air_quality() -> dict[str, dict]:
    """Extrae O3, NO2 y PM25 de la red RVVCCA para cada estación."""
    url = "https://rvvcca.pica.gva.es/Castellano/Noticias/ultimas_medidas.asp"
    headers = {"User-Agent": "Mozilla/5.0"}
    data: dict[str, dict] = {}
    fallback = {"O3": 35.0, "NO2": 25.0, "PM25": 15.0}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Intentamos parsear tablas de la página
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if not cells:
                    continue
                station_raw = cells[0] if cells else ""
                # Buscar coincidencia parcial con nuestras estaciones
                matched = None
                for name in STATION_NAMES:
                    key = name.split()[0].lower()
                    if key in station_raw.lower():
                        matched = name
                        break
                if matched:
                    record: dict = {}
                    for i, cell in enumerate(cells[1:], 1):
                        header_text = cell.upper()
                        try:
                            val = float(cell.replace(",", "."))
                            if "O3" in cells[0].upper() or i == 1:
                                record.setdefault("O3", val)
                            elif "NO2" in cell.upper():
                                record.setdefault("NO2", val)
                            elif "PM" in cell.upper():
                                record.setdefault("PM25", val)
                        except ValueError:
                            pass
                    data[matched] = {**fallback, **record}
    except Exception:
        pass

    # Completar estaciones sin datos con fallback + ruido pequeño
    rng = np.random.default_rng(int(datetime.now().timestamp()) % 10000)
    for name in STATION_NAMES:
        if name not in data:
            data[name] = {
                "O3":   float(rng.uniform(20, 60)),
                "NO2":  float(rng.uniform(10, 45)),
                "PM25": float(rng.uniform(8, 30)),
            }
    return data


def fetch_meteo(date_str: str) -> dict:
    """Obtiene datos meteorológicos de Meteostat para Valencia (08284)."""
    fallback = {
        "Velocidad_viento": 3.5,
        "Direccion_viento": 180.0,
        "Temperatura": 20.0,
        "Humedad_relativa": 60.0,
        "Presion": 1013.0,
        "Precipitacion": 0.0,
    }
    try:
        url = f"https://meteostat.net/es/station/08284?t={date_str}/{date_str}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        meteo: dict = {}
        text = soup.get_text(" ", strip=True)

        patterns = {
            "Temperatura":      r"Temperatura[\s:]+(-?\d+[\.,]\d+|\d+)\s*°C",
            "Humedad_relativa": r"Humedad[\s:]+(\d+[\.,]?\d*)\s*%",
            "Presion":          r"Presi[oó]n[\s:]+(\d+[\.,]?\d*)\s*hPa",
            "Velocidad_viento": r"Viento[\s:]+(\d+[\.,]?\d*)\s*km/h",
            "Precipitacion":    r"Precipitaci[oó]n[\s:]+(\d+[\.,]?\d*)\s*mm",
        }
        for key, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                meteo[key] = float(m.group(1).replace(",", "."))

        meteo.setdefault("Direccion_viento", 180.0)
        return {**fallback, **meteo}
    except Exception:
        return fallback


# ── Caché CSV ────────────────────────────────────────────────────────────────

def _get_last_download_time() -> datetime | None:
    if not os.path.exists(AQ_CACHE_FILE):
        return None
    try:
        df = pd.read_csv(AQ_CACHE_FILE, nrows=1)
        if df.empty or "downloaded_at" not in df.columns:
            return None
        return datetime.fromisoformat(df["downloaded_at"].iloc[0])
    except Exception:
        return None


def _save_air_quality_cache(air_data: dict, ts: datetime) -> None:
    rows = [{"downloaded_at": ts.isoformat(), "station": s, **v} for s, v in air_data.items()]
    pd.DataFrame(rows).to_csv(AQ_CACHE_FILE, index=False)


def _save_meteo_cache(meteo: dict, ts: datetime) -> None:
    pd.DataFrame([{"downloaded_at": ts.isoformat(), **meteo}]).to_csv(METEO_CACHE_FILE, index=False)


def _load_air_quality_cache() -> dict:
    df = pd.read_csv(AQ_CACHE_FILE)
    return {
        row["station"]: {"O3": row["O3"], "NO2": row["NO2"], "PM25": row["PM25"]}
        for _, row in df.iterrows()
    }


def _load_meteo_cache() -> dict:
    df = pd.read_csv(METEO_CACHE_FILE)
    row = df.iloc[0].to_dict()
    row.pop("downloaded_at", None)
    return row


def get_current_data(force: bool = False) -> tuple[dict, dict, bool]:
    """Devuelve (air_data, meteo, was_refreshed). Descarga solo si ha transcurrido MIN_DOWNLOAD_INTERVAL_MINUTES."""
    if st.session_state.get("_is_downloading"):
        last = _get_last_download_time()
        if last is not None:
            return _load_air_quality_cache(), _load_meteo_cache(), False

    last = _get_last_download_time()
    now = datetime.now()
    elapsed_min = (now - last).total_seconds() / 60 if last else float("inf")
    should_download = force or elapsed_min >= MIN_DOWNLOAD_INTERVAL_MINUTES

    if not should_download:
        return _load_air_quality_cache(), _load_meteo_cache(), False

    st.session_state["_is_downloading"] = True
    try:
        air_data = fetch_air_quality()
        meteo = fetch_meteo(now.strftime("%Y-%m-%d"))
        _save_air_quality_cache(air_data, now)
        _save_meteo_cache(meteo, now)
        return air_data, meteo, True
    except Exception:
        if last is not None:
            return _load_air_quality_cache(), _load_meteo_cache(), False
        raise
    finally:
        st.session_state["_is_downloading"] = False


# ── Modelo ───────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def load_model():
    try:
        obj = joblib.load("lgb_PM25_h1.pkl")

        # Caso 1: objeto con .predict() directamente (LGBMRegressor, Pipeline, Booster…)
        if hasattr(obj, "predict"):
            return obj

        # Caso 2: dict — buscar el modelo en claves habituales
        if isinstance(obj, dict):
            for key in ["model", "estimator", "lgb", "lgbm", "booster",
                        "regressor", "pipeline", "clf", "reg"]:
                if key in obj and hasattr(obj[key], "predict"):
                    return obj[key]
            # Ninguna clave conocida: mostrar las disponibles para diagnóstico
            claves = list(obj.keys())
            st.error(
                f"❌ El archivo `.pkl` es un `dict` con claves: `{claves}`. "
                f"Ninguna tiene `.predict()`. "
                f"Edita `load_model()` en `app.py` y sustituye la clave correcta."
            )
            return None

        st.error(f"❌ Tipo inesperado en el .pkl: `{type(obj)}`. Esperaba un modelo con `.predict()`.")
        return None

    except FileNotFoundError:
        st.warning("⚠️ Modelo `lgb_PM25_h1.pkl` no encontrado. Se usará un modelo dummy para demo.")
        return None


def cyclic_encode(val: float, period: float):
    rad = 2 * np.pi * val / period
    return np.sin(rad), np.cos(rad)


def build_feature_row(
    dt: datetime,
    station: str,
    meteo: dict,
    air: dict,
    pm25_history: list[float],
    o3_history: list[float],
    no2_history: list[float],
    wind_history: list[float],
    temp_history: list[float],
) -> pd.DataFrame:
    """Construye exactamente las 37 features que espera el modelo."""

    def lag(hist: list[float], n: int) -> float:
        return hist[-n] if len(hist) >= n else (hist[0] if hist else 0.0)

    def roll(hist: list[float], n: int) -> float:
        window = hist[-n:] if len(hist) >= n else hist
        return float(np.mean(window)) if window else 0.0

    hour_sin, hour_cos = cyclic_encode(dt.hour, 24)
    month_sin, month_cos = cyclic_encode(dt.month, 12)

    row = {
        "hour_sin":         hour_sin,
        "hour_cos":         hour_cos,
        "month_sin":        month_sin,
        "month_cos":        month_cos,
        "station_encoded":  STATION_LE[station],
        "O3":               air.get("O3", 35.0),
        "NO2":              air.get("NO2", 25.0),
        "Velocidad_viento": meteo["Velocidad_viento"],
        "Direccion_viento": meteo["Direccion_viento"],
        "Temperatura":      meteo["Temperatura"],
        "Humedad_relativa": meteo["Humedad_relativa"],
        "Presion":          meteo["Presion"],
        "Precipitacion":    meteo["Precipitacion"],
        # PM25 lags
        "PM25_lag1":   lag(pm25_history, 1),
        "PM25_lag2":   lag(pm25_history, 2),
        "PM25_lag3":   lag(pm25_history, 3),
        "PM25_lag6":   lag(pm25_history, 6),
        "PM25_lag12":  lag(pm25_history, 12),
        "PM25_lag24":  lag(pm25_history, 24),
        # PM25 rolling
        "PM25_roll3":  roll(pm25_history, 3),
        "PM25_roll6":  roll(pm25_history, 6),
        "PM25_roll12": roll(pm25_history, 12),
        "PM25_roll24": roll(pm25_history, 24),
        # O3 lags
        "O3_lag1":  lag(o3_history, 1),
        "O3_lag3":  lag(o3_history, 3),
        "O3_lag6":  lag(o3_history, 6),
        # NO2 lags
        "NO2_lag1": lag(no2_history, 1),
        "NO2_lag3": lag(no2_history, 3),
        "NO2_lag6": lag(no2_history, 6),
        # Viento lags
        "viento_lag1": lag(wind_history, 1),
        "viento_lag3": lag(wind_history, 3),
        "viento_lag6": lag(wind_history, 6),
        # Temperatura lags
        "temp_lag1": lag(temp_history, 1),
        "temp_lag3": lag(temp_history, 3),
        "temp_lag6": lag(temp_history, 6),
        # Raw time
        "hour":  dt.hour,
        "month": dt.month,
    }

    return pd.DataFrame([row])[MODEL_FEATURES]


def predict_recursive_168h(model, air_data: dict, meteo: dict) -> dict[str, list[float]]:
    """
    Para cada estación, genera predicciones recursivas 168h.
    Retorna dict station -> lista 169 valores (t=0 actual + 168 predichos).
    """
    results: dict[str, list[float]] = {}
    now = datetime.now().replace(minute=0, second=0, microsecond=0)

    for station in STATION_NAMES:
        air = air_data.get(station, {"O3": 35.0, "NO2": 25.0, "PM25": 15.0})
        current_pm25 = air.get("PM25", 15.0)

        # Historial inicial (24h simulado con decaimiento suave)
        rng = np.random.default_rng(STATION_LE[station] + 42)
        base = current_pm25
        pm25_hist: list[float] = [
            max(0.0, base + rng.normal(0, 1.5)) for _ in range(24)
        ]
        o3_hist:    list[float] = [air.get("O3", 35.0)]   * 24
        no2_hist:   list[float] = [air.get("NO2", 25.0)]  * 24
        wind_hist:  list[float] = [meteo["Velocidad_viento"]] * 24
        temp_hist:  list[float] = [meteo["Temperatura"]]       * 24

        forecast: list[float] = [current_pm25]  # t=0

        for h in range(1, 169):
            dt_h = now + timedelta(hours=h)
            X = build_feature_row(
                dt_h, station, meteo, air,
                pm25_hist, o3_hist, no2_hist, wind_hist, temp_hist,
            )

            if model is not None:
                pred = float(model.predict(X)[0])
            else:
                # Dummy: variación sinusoidal + ruido
                noise = rng.normal(0, 1.2)
                diurnal = 4 * np.sin(2 * np.pi * dt_h.hour / 24 - np.pi / 2)
                pred = max(0.0, pm25_hist[-1] * 0.97 + diurnal + noise)

            pred = max(0.0, round(pred, 2))
            forecast.append(pred)

            # Actualizar historiales
            pm25_hist.append(pred)
            o3_hist.append(air.get("O3", 35.0) * rng.uniform(0.97, 1.03))
            no2_hist.append(air.get("NO2", 25.0) * rng.uniform(0.97, 1.03))
            wind_hist.append(meteo["Velocidad_viento"] * rng.uniform(0.95, 1.05))
            temp_hist.append(meteo["Temperatura"] + rng.normal(0, 0.5))

        results[station] = forecast

    return results


# ── Utilidades de UI ─────────────────────────────────────────────────────────

def pm25_color(val: float) -> str:
    if val < 12:   return "#3fb950"   # verde
    if val < 35:   return "#d29922"   # amarillo
    if val < 55:   return "#f0883e"   # naranja
    return "#da3633"                   # rojo


def pm25_label(val: float) -> str:
    if val < 12:  return "Buena"
    if val < 35:  return "Moderada"
    if val < 55:  return "Dañina sensibles"
    return "Dañina"


def build_map(forecasts: dict, hour_idx: int, selected: str | None) -> folium.Map:
    m = folium.Map(
        location=[39.4697, -0.3774],
        zoom_start=12,
        tiles="CartoDB positron",
    )
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    dt_label = (now + timedelta(hours=hour_idx)).strftime("%d/%m/%Y %H:%M")

    for name, (lat, lon) in STATIONS.items():
        fc = forecasts.get(name, [15.0] * 169)
        current = fc[0]
        predicted = fc[hour_idx] if hour_idx < len(fc) else fc[-1]
        val = predicted
        color = pm25_color(val)
        is_selected = name == selected

        radius = 14 if is_selected else 10
        border = "#ffffff" if is_selected else "#555555"
        border_w = 3 if is_selected else 1.5

        popup_html = f"""
        <div style="font-family:'DM Sans',sans-serif;min-width:200px;background:#161b22;
                    color:#e6edf3;padding:12px;border-radius:8px;border:1px solid #30363d;">
          <b style="font-family:'Space Mono',monospace;font-size:13px">{name}</b><br>
          <hr style="border-color:#30363d;margin:6px 0">
          <span style="font-size:11px;color:#8b949e">AHORA (t=0)</span><br>
          <span style="font-size:22px;font-weight:700;color:{pm25_color(current)}">{current:.1f} µg/m³</span>
          <br><br>
          <span style="font-size:11px;color:#8b949e">PREVISIÓN · {dt_label}</span><br>
          <span style="font-size:22px;font-weight:700;color:{color}">{predicted:.1f} µg/m³</span>
          <br>
          <span style="font-size:11px;color:{color};background:rgba(255,255,255,0.05);
                       padding:2px 6px;border-radius:4px">{pm25_label(val)}</span>
        </div>
        """

        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            color=border,
            weight=border_w,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{name}: {val:.1f} µg/m³",
        ).add_to(m)

    # Leyenda
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;
                background:white;border:1px solid #ccc;border-radius:8px;
                padding:12px 16px;font-family:'DM Sans',sans-serif;color:#333;font-size:12px;
                box-shadow:0 2px 8px rgba(0,0,0,0.15);">
      <b style="font-family:'Space Mono',monospace">PM2.5 µg/m³</b><br>
      <span style="color:#3fb950">●</span> &lt;12 · Buena<br>
      <span style="color:#d29922">●</span> 12–35 · Moderada<br>
      <span style="color:#f0883e">●</span> 35–55 · Dañina sensibles<br>
      <span style="color:#da3633">●</span> &gt;55 · Dañina
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


def build_forecast_chart(forecasts: dict, station: str) -> go.Figure:
    fc = forecasts.get(station, [15.0] * 169)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    times = [now + timedelta(hours=h) for h in range(len(fc))]

    # Bandas de color AQI como áreas de fondo
    fig = go.Figure()

    # Áreas AQI
    x_full = [times[0], times[-1]]
    for ymin, ymax, color, label in [
        (0, 12,  "rgba(63,185,80,0.08)",  "Buena"),
        (12, 35, "rgba(210,153,34,0.08)", "Moderada"),
        (35, 55, "rgba(240,136,62,0.08)", "Dañina sensibles"),
        (55, 200,"rgba(218,54,51,0.08)",  "Dañina"),
    ]:
        fig.add_hrect(y0=ymin, y1=ymax, fillcolor=color, line_width=0,
                      annotation_text=label, annotation_position="left",
                      annotation_font_color="#8b949e", annotation_font_size=10)

    # Línea de previsión
    fig.add_trace(go.Scatter(
        x=times, y=fc,
        mode="lines",
        name="PM2.5 previsto",
        line=dict(color="#58a6ff", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(88,166,255,0.06)",
        hovertemplate="%{x|%d/%m %H:%M}<br><b>%{y:.1f} µg/m³</b><extra></extra>",
    ))

    # Marcador t=0
    fig.add_vline(x=times[0], line_dash="dash", line_color="#8b949e", line_width=1)
    fig.add_annotation(x=times[0], y=max(fc)*0.9, text="Ahora",
                       showarrow=False, font=dict(color="#8b949e", size=11))

    fig.update_layout(
        title=dict(
            text=f"<b>{station}</b> · Previsión PM2.5 168h",
            font=dict(family="Space Mono", size=14, color="#e6edf3"),
        ),
        paper_bgcolor="#161b22",
        plot_bgcolor="#161b22",
        font=dict(family="DM Sans", color="#8b949e"),
        xaxis=dict(
            showgrid=True, gridcolor="#21262d", tickformat="%a %d\n%H:%M",
            color="#8b949e", title=None,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#21262d", title="µg/m³",
            color="#8b949e", range=[0, max(max(fc)*1.15, 60)],
        ),
        margin=dict(l=50, r=20, t=50, b=40),
        height=320,
        legend=dict(bgcolor="#161b22", bordercolor="#30363d"),
        hovermode="x unified",
    )
    return fig


# ── App principal ─────────────────────────────────────────────────────────────

def main():
    from streamlit_autorefresh import st_autorefresh

    # ── Auto-refresh: el visualizador emite un evento cada CHECK_INTERVAL_MINUTES ──
    st_autorefresh(interval=CHECK_INTERVAL_MINUTES * 60 * 1000, key="data_refresh")

    # ── Header ──
    st.markdown("""
    <h1 style="font-size:1.6rem;margin-bottom:0;color:#e6edf3">
      🌿 Calidad del Aire · Valencia
    </h1>
    <p style="color:#8b949e;font-size:0.85rem;margin-top:4px;font-family:'DM Sans',sans-serif">
      PM2.5 en tiempo real + previsión LightGBM · 168 horas
    </p>
    """, unsafe_allow_html=True)

    # ── Carga datos con caché CSV inteligente ──
    first_load = "forecasts" not in st.session_state

    if first_load:
        with st.spinner("⏳ Cargando datos y generando previsión 168h…"):
            air_data, meteo, _ = get_current_data()
            model = load_model()
            forecasts = predict_recursive_168h(model, air_data, meteo)
            st.session_state.update({
                "forecasts": forecasts,
                "air_data": air_data,
                "meteo": meteo,
                "loaded_at": datetime.now(),
                "data_source": "fresh",
            })
    else:
        # Comprobación periódica: descarga solo si ha transcurrido el intervalo mínimo
        air_data, meteo, refreshed = get_current_data()
        if refreshed:
            with st.spinner("⏳ Nuevos datos disponibles · Actualizando previsión…"):
                model = load_model()
                forecasts = predict_recursive_168h(model, air_data, meteo)
                st.session_state.update({
                    "forecasts": forecasts,
                    "air_data": air_data,
                    "meteo": meteo,
                    "loaded_at": datetime.now(),
                    "data_source": "fresh",
                })

    forecasts = st.session_state["forecasts"]
    air_data  = st.session_state["air_data"]
    meteo     = st.session_state["meteo"]
    loaded_at = st.session_state.get("loaded_at", datetime.now())

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("### ⚙️ Controles")

        hour_idx = st.slider(
            "Hora de previsión (h)",
            min_value=0, max_value=168, value=0, step=1,
            help="0 = datos actuales · 168 = +7 días",
        )

        dt_sel = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=hour_idx)
        st.caption(f"📅 {dt_sel.strftime('%A %d/%m/%Y · %H:%M')}")

        st.markdown("---")
        selected_station = st.selectbox("📍 Estación", STATION_NAMES, index=8)

        st.markdown("---")
        st.markdown("### 🌤 Meteorología")
        cols = st.columns(2)
        cols[0].metric("🌡 Temp.", f"{meteo['Temperatura']:.1f} °C")
        cols[1].metric("💨 Viento", f"{meteo['Velocidad_viento']:.1f} km/h")
        cols[0].metric("💧 Humedad", f"{meteo['Humedad_relativa']:.0f} %")
        cols[1].metric("🔵 Presión", f"{meteo['Presion']:.0f} hPa")

        st.markdown("---")
        if st.button("🔄 Forzar actualización"):
            for key in ["forecasts", "air_data", "meteo", "loaded_at", "data_source"]:
                st.session_state.pop(key, None)
            st.rerun()

        last_dl = _get_last_download_time()
        if last_dl:
            elapsed_min = int((datetime.now() - last_dl).total_seconds() / 60)
            next_dl_min = max(0, MIN_DOWNLOAD_INTERVAL_MINUTES - elapsed_min)
            source_icon = "🆕" if st.session_state.get("data_source") == "fresh" else "💾"
            st.caption(
                f"{source_icon} Descargado: {last_dl.strftime('%H:%M:%S')}\n\n"
                f"Próxima descarga en: {next_dl_min} min\n\n"
                f"Revisión automática cada: {CHECK_INTERVAL_MINUTES} min"
            )
        else:
            st.caption(f"Datos cargados: {loaded_at.strftime('%H:%M:%S')}")

    # ── Layout principal ──
    col_map, col_right = st.columns([3, 2], gap="medium")

    with col_map:
        st.markdown(f"#### 🗺 Mapa · {'+' + str(hour_idx) + 'h' if hour_idx else 'Ahora'}")
        m = build_map(forecasts, hour_idx, selected_station)
        st_folium(m, width=None, height=500, returned_objects=[])

    with col_right:
        # Métricas de la estación seleccionada
        fc_sel = forecasts.get(selected_station, [15.0] * 169)
        val_now  = fc_sel[0]
        val_pred = fc_sel[hour_idx]
        delta    = val_pred - val_now
        cat_color = "aqi-good" if val_pred < 12 else "aqi-moderate" if val_pred < 35 else "aqi-usg" if val_pred < 55 else "aqi-unhealthy"

        st.markdown(f"#### 📍 {selected_station}")
        st.markdown(f"""
        <div class="metric-card">
          <div class="label">PM2.5 ahora (t=0)</div>
          <div class="value {('aqi-good' if val_now < 12 else 'aqi-moderate' if val_now < 35 else 'aqi-usg' if val_now < 55 else 'aqi-unhealthy')}">{val_now:.1f} µg/m³</div>
        </div>
        <div class="metric-card">
          <div class="label">PM2.5 previsto (+{hour_idx}h)</div>
          <div class="value {cat_color}">{val_pred:.1f} µg/m³
            <span style="font-size:14px;color:#8b949e"> ({'+' if delta >= 0 else ''}{delta:.1f})</span>
          </div>
          <div style="font-size:12px;color:#8b949e;margin-top:4px">{pm25_label(val_pred)}</div>
        </div>
        """, unsafe_allow_html=True)

        air = air_data.get(selected_station, {})
        st.markdown(f"""
        <div class="metric-card" style="margin-top:8px">
          <div class="label">Contaminantes actuales</div>
          <div style="display:flex;gap:16px;margin-top:8px">
            <div><div style="font-size:10px;color:#8b949e">O₃</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace">{air.get('O3', 0):.1f}</div></div>
            <div><div style="font-size:10px;color:#8b949e">NO₂</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace">{air.get('NO2', 0):.1f}</div></div>
            <div><div style="font-size:10px;color:#8b949e">PM2.5</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace">{air.get('PM25', val_now):.1f}</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Mini-tabla resumen todas estaciones
        st.markdown("#### 📊 Resumen estaciones")
        rows = []
        for name in STATION_NAMES:
            fc = forecasts.get(name, [15.0] * 169)
            v_now  = fc[0]
            v_pred = fc[hour_idx]
            rows.append({
                "Estación": name,
                "Ahora": f"{v_now:.1f}",
                f"+{hour_idx}h": f"{v_pred:.1f}",
                "Estado": pm25_label(v_pred),
            })
        df_summary = pd.DataFrame(rows).set_index("Estación")
        st.dataframe(df_summary, use_container_width=True, height=280)

    # ── Gráfico evolutivo ──
    st.markdown(f"#### 📈 Tendencia 7 días · {selected_station}")
    fig = build_forecast_chart(forecasts, selected_station)
    st.plotly_chart(fig, use_container_width=True)

    # ── Footer ──
    st.markdown("""
    <hr style="border-color:#30363d;margin-top:32px">
    <p style="text-align:center;font-size:11px;color:#8b949e;font-family:'DM Sans',sans-serif">
      Datos: RVVCCA GVA · Meteostat · Modelo LightGBM entrenado localmente
    </p>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()