"""app.py — Streamlit · Calidad del Aire PM2.5 Valencia.

Cliente delgado: lee el snapshot completo del backend FastAPI y pinta el mapa,
panel de métricas y gráfica de tendencia. No tiene lógica de ML ni scraping.
"""
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, date, timedelta

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from api_client import get_snapshot, force_refresh, health, BackendUnavailable, API_URL
from ui import build_map, build_forecast_chart, pm25_class, pm25_label

# ── Configuración de página ──
st.set_page_config(
    page_title="Calidad del Aire · Valencia",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Space Mono', monospace; }

.stApp { background: #f6f8fa; color: #1f2328; }

.metric-card {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 8px;
    box-shadow: 0 1px 3px rgba(31,35,40,0.06);
}
.metric-card .label { font-size: 11px; color: #57606a; text-transform: uppercase; letter-spacing: 1px; }
.metric-card .value { font-size: 28px; font-family: 'Space Mono', monospace; font-weight: 700; }

.aqi-1 { color: #00CCCC; }  /* Buena */
.aqi-2 { color: #2E9D5B; }  /* Razonablemente buena */
.aqi-3 { color: #D4A017; }  /* Regular */
.aqi-4 { color: #E64A19; }  /* Desfavorable */
.aqi-5 { color: #960018; }  /* Muy desfavorable */
.aqi-6 { color: #7D2181; }  /* Extremadamente desfavorable */

section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #d0d7de;
}

/* Ocultar sólo el botón Deploy de Streamlit */
div[data-testid="stDeployButton"] { display: none !important; }
[data-testid="stToolbarActions"] { display: none !important; }

/* Badge "Valencia" en la esquina superior derecha */
.valencia-badge {
    position: fixed;
    top: 12px;
    right: 18px;
    z-index: 999999;
    font-family: 'Space Mono', monospace;
    font-size: 13px;
    font-weight: 700;
    color: #1f2328;
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 6px 12px;
    box-shadow: 0 1px 3px rgba(31,35,40,0.08);
}
</style>
<div class="valencia-badge">📍 Valencia</div>
""", unsafe_allow_html=True)


def main():
    # ── Header ──
    st.markdown("""
    <h1 style="font-size:1.6rem;margin-bottom:0;color:#1f2328">
      🌿 Calidad del Aire · Valencia
    </h1>
    <p style="color:#57606a;font-size:0.85rem;margin-top:4px;font-family:'DM Sans',sans-serif">
      PM2.5 en tiempo real + previsión 168 horas · datos vía API
    </p>
    """, unsafe_allow_html=True)

    # ── Snapshot del backend ──
    try:
        snapshot = get_snapshot()
    except BackendUnavailable as e:
        st.error(f"❌ No se pudo conectar con el backend en `{API_URL}`.\n\n{e}")
        st.info("Asegúrate de que el backend FastAPI está arrancado:\n\n"
                "`uvicorn backend.main:app --reload --port 8000`")
        st.stop()

    stations  = snapshot["stations"]                  # list[{name, lat, lon}]
    meteo     = snapshot["meteo"]
    forecasts = snapshot["forecasts"]                 # dict[name → list[169]]
    current   = snapshot["current"]                   # dict[name → {O3, NO2, PM25}]
    station_names = [s["name"] for s in stations]

    if "selected_station" not in st.session_state or st.session_state.selected_station not in station_names:
        default = "Av. França" if "Av. França" in station_names else station_names[0]
        st.session_state.selected_station = default

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("### ⚙️ Controles")

        today = date.today()
        selected_date = st.date_input(
            "📅 Día de previsión",
            value=today,
            min_value=today,
            max_value=today + timedelta(days=7),
            help="Elige cualquier día desde hoy hasta dentro de 7 días",
        )

        now_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        if selected_date == today:
            hour_idx = 0
            dt_sel = now_hour
        else:
            days_ahead = (selected_date - today).days
            hour_idx = min(days_ahead * 24 + 12, 168)
            dt_sel = now_hour + timedelta(hours=hour_idx)

        st.caption(f"⏱ Previsión para: {dt_sel.strftime('%A %d/%m/%Y · %H:%M')}")

        st.markdown("---")
        selected_station = st.selectbox(
            "📍 Estación",
            station_names,
            index=station_names.index(st.session_state.selected_station),
        )
        st.session_state.selected_station = selected_station

        st.markdown("---")
        st.markdown("### 🌤 Meteorología")
        cols = st.columns(2)
        cols[0].metric("🌡 Temp.",   f"{meteo['Temperatura']:.1f} °C")
        cols[1].metric("💨 Viento", f"{meteo['Velocidad_viento']:.1f} km/h")
        cols[0].metric("💧 Humedad", f"{meteo['Humedad_relativa']:.0f} %")
        cols[1].metric("🔵 Presión", f"{meteo['Presion']:.0f} hPa")

        st.markdown("---")
        if st.button("🔄 Forzar actualización"):
            with st.spinner("Pidiendo al backend que regenere…"):
                try:
                    force_refresh()
                except BackendUnavailable as e:
                    st.error(f"No se pudo refrescar: {e}")
                else:
                    st.rerun()

        # Info del estado del backend
        try:
            h = health()
            ts = h.get("last_snapshot")
            if ts:
                ts_fmt = datetime.fromisoformat(ts).strftime("%H:%M:%S")
                st.caption(
                    f"🆕 Snapshot: {ts_fmt}\n\n"
                    f"Próximo refresco en: {h.get('next_refresh_in_min', 0)} min"
                )
        except BackendUnavailable:
            st.caption("⚠️ Backend no responde a /health")

    # ── Layout principal ──
    col_map, col_right = st.columns([3, 2], gap="medium")

    with col_map:
        st.markdown(f"#### 🗺 Mapa · {'+' + str(hour_idx) + 'h' if hour_idx else 'Ahora'}")
        m = build_map(stations, forecasts, hour_idx, selected_station)
        map_state = st_folium(
            m,
            width=None,
            height=500,
            returned_objects=["last_object_clicked_tooltip"],
            key="folium_map",
        )
        clicked = map_state.get("last_object_clicked_tooltip") if map_state else None
        if clicked and clicked in station_names and clicked != st.session_state.selected_station:
            st.session_state.selected_station = clicked
            st.rerun()

    with col_right:
        fc_sel = forecasts.get(selected_station, [15.0] * 169)
        val_now  = fc_sel[0]
        val_pred = fc_sel[hour_idx]
        delta    = val_pred - val_now
        cat_color = pm25_class(val_pred)

        st.markdown(f"#### 📍 {selected_station}")
        st.markdown(f"""
        <div class="metric-card">
          <div class="label">PM2.5 ahora (t=0)</div>
          <div class="value {pm25_class(val_now)}">{val_now:.1f} µg/m³</div>
        </div>
        <div class="metric-card">
          <div class="label">PM2.5 previsto (+{hour_idx}h)</div>
          <div class="value {cat_color}">{val_pred:.1f} µg/m³
            <span style="font-size:14px;color:#57606a"> ({'+' if delta >= 0 else ''}{delta:.1f})</span>
          </div>
          <div style="font-size:12px;color:#57606a;margin-top:4px">{pm25_label(val_pred)}</div>
        </div>
        """, unsafe_allow_html=True)

        air = current.get(selected_station, {})
        st.markdown(f"""
        <div class="metric-card" style="margin-top:8px">
          <div class="label">Contaminantes actuales</div>
          <div style="display:flex;gap:16px;margin-top:8px">
            <div><div style="font-size:10px;color:#57606a">O₃</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace;color:#1f2328">{air.get('O3', 0):.1f}</div></div>
            <div><div style="font-size:10px;color:#57606a">NO₂</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace;color:#1f2328">{air.get('NO2', 0):.1f}</div></div>
            <div><div style="font-size:10px;color:#57606a">PM2.5</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace;color:#1f2328">{air.get('PM25', val_now):.1f}</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 📊 Resumen estaciones")
        rows = []
        for name in station_names:
            fc = forecasts.get(name, [15.0] * 169)
            rows.append({
                "Estación": name,
                "Ahora": f"{fc[0]:.1f}",
                f"+{hour_idx}h": f"{fc[hour_idx]:.1f}",
                "Estado": pm25_label(fc[hour_idx]),
            })
        df_summary = pd.DataFrame(rows).set_index("Estación")
        st.dataframe(df_summary, width="stretch", height=280)

    st.markdown(f"#### 📈 Tendencia 7 días · {selected_station}")
    fig = build_forecast_chart(forecasts, selected_station)
    st.plotly_chart(fig, width="stretch")

    st.markdown("""
    <hr style="border-color:#d0d7de;margin-top:32px">
    <p style="text-align:center;font-size:11px;color:#57606a;font-family:'DM Sans',sans-serif">
      Datos: RVVCCA GVA · Meteostat · Pipeline CBLA (CNN-BiLSTM + XGBoost) servido por API FastAPI
    </p>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
