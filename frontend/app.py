"""app.py — Streamlit · Calidad del Aire PM2.5/NO2/O3 Valencia.

Cliente delgado: lee el snapshot completo del backend FastAPI (3 contaminantes ×
n estaciones, predicción 168 h) y pinta el mapa + panel + gráfica del contaminante
seleccionado.
"""
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, date, time, timedelta

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from api_client import get_snapshot, force_refresh, health, BackendUnavailable, API_URL
from ui import (
    build_map, build_forecast_chart,
    aqi_class, aqi_label,
    POLLUTANT_LABELS, POLLUTANT_UNITS,
)

_DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
              "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fmt_es(dt: datetime, kind: str = "full") -> str:
    """Formatea una fecha con día de la semana en español.

    kind = "full" → "miércoles 21/05/2026 · 14:00"
    kind = "short_day" → "mié 21/05"
    """
    if kind == "full":
        return f"{_DAYS_ES[dt.weekday()]} {dt.day:02d}/{dt.month:02d}/{dt.year} · {dt.strftime('%H:%M')}"
    short = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"][dt.weekday()]
    return f"{short} {dt.day:02d}/{dt.month:02d}"

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

.aqi-1 { color: #00CCCC; }
.aqi-2 { color: #2E9D5B; }
.aqi-3 { color: #D4A017; }
.aqi-4 { color: #E64A19; }
.aqi-5 { color: #960018; }
.aqi-6 { color: #7D2181; }
.aqi-disabled { color: #9e9e9e; }

section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #d0d7de;
}

div[data-testid="stDeployButton"] { display: none !important; }
[data-testid="stToolbarActions"] { display: none !important; }

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


POLLUTANT_OPTIONS = ["PM2.5", "NO₂", "O₃"]
POLLUTANT_KEY = {"PM2.5": "PM25", "NO₂": "NO2", "O₃": "O3"}


def main():
    # ── Header ──
    st.markdown("""
    <h1 style="font-size:1.6rem;margin-bottom:0;color:#1f2328">
      🌿 Calidad del Aire · Valencia
    </h1>
    <p style="color:#57606a;font-size:0.85rem;margin-top:4px;font-family:'DM Sans',sans-serif">
      PM2.5 · NO₂ · O₃ en tiempo real + previsión 168 horas · datos vía API
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

    stations     = snapshot["stations"]
    meteo        = snapshot["meteo"]
    forecasts    = snapshot["forecasts"]                  # dict[pollutant → dict[station → list[169]]]
    current      = snapshot["current"]
    supported    = snapshot["supported_stations"]         # dict[pollutant → list[station]]
    station_names = [s["name"] for s in stations]

    if "selected_station" not in st.session_state or st.session_state.selected_station not in station_names:
        default = "Av. França" if "Av. França" in station_names else station_names[0]
        st.session_state.selected_station = default

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("### ⚙️ Controles")

        pollutant_display = st.radio(
            "🧪 Contaminante",
            POLLUTANT_OPTIONS,
            horizontal=True,
            help="PM2.5: 7 estaciones · NO₂: 9 · O₃: 6",
        )
        pollutant = POLLUTANT_KEY[pollutant_display]
        poll_lbl  = POLLUTANT_LABELS[pollutant]
        units     = POLLUTANT_UNITS[pollutant]

        today = date.today()
        now_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        current_hour = now_hour.hour

        selected_date = st.date_input(
            "📅 Día de previsión",
            value=today,
            min_value=today,
            max_value=today + timedelta(days=7),
            format="DD/MM/YYYY",
            help="Día para la previsión (hasta +7 días)",
        )

        # Hora por defecto: la actual si es hoy, mediodía si es futuro.
        default_hour = current_hour if selected_date == today else 12
        selected_hour = st.slider(
            "⏰ Hora del día",
            min_value=0,
            max_value=23,
            value=default_hour,
            help="Hora a la que quieres ver la previsión (0-23)",
        )

        target_dt = datetime.combine(selected_date, time(selected_hour, 0))
        hour_idx = max(0, min(int((target_dt - now_hour).total_seconds() / 3600), 168))
        dt_sel = now_hour + timedelta(hours=hour_idx)

        # Si lo elegido cae fuera del rango del modelo, avisamos en una caption.
        if dt_sel != target_dt:
            st.caption(f"⚠️ Fuera del rango previsto. Mostrando: {_fmt_es(dt_sel)}")
        else:
            st.caption(f"⏱ Previsión para: {_fmt_es(dt_sel)}")

        st.markdown("---")
        selected_station = st.selectbox(
            "📍 Estación",
            station_names,
            index=station_names.index(st.session_state.selected_station),
        )
        st.session_state.selected_station = selected_station

        show_coverage = st.checkbox(
            "Mostrar área de cobertura",
            value=False,
            help="Dibuja un círculo de 500 m de radio alrededor de cada centralita "
                 "indicando su zona de representatividad espacial aproximada.",
        )

        st.markdown("---")
        st.markdown("### 🌤 Meteorología")

        _CARDINALS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
        dir_deg  = meteo["Direccion_viento"]
        dir_card = _CARDINALS[int((dir_deg + 22.5) // 45) % 8]

        # Flecha rotada que apunta hacia DE DÓNDE viene el viento (convención
        # meteorológica de Open-Meteo). ↑=N (0°), girando en sentido horario.
        wind_arrow = (
            f'<span style="display:inline-block;transform:rotate({dir_deg:.0f}deg);'
            f'color:#1f2328;font-size:14px;line-height:1;margin-left:6px;">↑</span>'
        )

        # Card vertical con filas label↔valor (más simétrico y sin truncado).
        meteo_rows = [
            ("🌡 Temperatura", f"{meteo['Temperatura']:.1f} °C"),
            ("💨 Viento",     f"{meteo['Velocidad_viento']:.1f} km/h · {dir_card} {dir_deg:.0f}°{wind_arrow}"),
            ("💧 Humedad",    f"{meteo['Humedad_relativa']:.0f} %"),
            ("🔵 Presión",    f"{meteo['Presion']:.0f} hPa"),
        ]
        rows_html = "".join(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:6px 0;border-bottom:1px solid #f0f3f6;font-size:13px;">'
            f'<span style="color:#57606a;">{label}</span>'
            f'<span style="font-family:\'Space Mono\',monospace;font-weight:700;color:#1f2328;">{value}</span>'
            f'</div>'
            for label, value in meteo_rows
        )
        st.markdown(
            f'<div style="background:#fff;border:1px solid #d0d7de;border-radius:8px;'
            f'padding:8px 14px;box-shadow:0 1px 3px rgba(31,35,40,0.06);">{rows_html}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")
        if st.button("🔄 Forzar actualización"):
            with st.spinner("Pidiendo al backend que regenere…"):
                try:
                    force_refresh()
                except BackendUnavailable as e:
                    st.error(f"No se pudo refrescar: {e}")
                else:
                    st.rerun()

        try:
            h = health()
            ts = h.get("last_snapshot")
            real_ts = h.get("last_real_data_at")
            caption_lines = []
            if ts:
                caption_lines.append(f"🆕 Snapshot: {datetime.fromisoformat(ts).strftime('%H:%M:%S')}")
            if real_ts:
                caption_lines.append(f"📡 Última lectura GVA: {datetime.fromisoformat(real_ts).strftime('%H:%M')}")
            caption_lines.append(f"Próximo refresco en: {h.get('next_refresh_in_min', 0)} min")
            st.caption("\n\n".join(caption_lines))
        except BackendUnavailable:
            st.caption("⚠️ Backend no responde a /health")

    # Variables derivadas
    forecasts_p   = forecasts.get(pollutant, {})
    supported_p   = supported.get(pollutant, [])
    is_supported  = selected_station in supported_p

    # ── Layout principal ──
    col_map, col_right = st.columns([3, 2], gap="medium")

    with col_map:
        st.markdown(f"#### 🗺 Mapa · {poll_lbl} · {'+' + str(hour_idx) + 'h' if hour_idx else 'Ahora'}")
        m = build_map(stations, forecasts_p, hour_idx, selected_station, pollutant, supported_p, show_coverage)
        map_state = st_folium(
            m,
            width=None,
            height=500,
            returned_objects=["last_object_clicked_tooltip"],
            key="folium_map",
        )
        clicked_raw = map_state.get("last_object_clicked_tooltip") if map_state else None
        if clicked_raw:
            # El tooltip de las no soportadas es "<nombre> · ... no disponible";
            # extraemos sólo el nombre y dejamos al usuario seleccionarla igual.
            clicked = clicked_raw.split(" · ")[0]
            if clicked in station_names and clicked != st.session_state.selected_station:
                st.session_state.selected_station = clicked
                st.rerun()

    # ── Etiquetas de tiempo para los cards ─────────────────────────
    now_str = now_hour.strftime("%H:%M")
    if dt_sel.date() == today:
        pred_time_str = dt_sel.strftime("%H:%M")
    elif dt_sel.date() == today + timedelta(days=1):
        pred_time_str = f"mañana {dt_sel.strftime('%H:%M')}"
    else:
        pred_time_str = f"{_fmt_es(dt_sel, 'short_day')} · {dt_sel.strftime('%H:%M')}"

    last_real_label = ""
    if snapshot.get("last_real_data_at"):
        last_real_dt = datetime.fromisoformat(snapshot["last_real_data_at"])
        hours_ago = max(0, int((datetime.now() - last_real_dt).total_seconds() / 3600))
        if hours_ago > 0:
            last_real_label = f"{last_real_dt.strftime('%H:%M')} · hace {hours_ago} h"
        else:
            last_real_label = last_real_dt.strftime("%H:%M")

    with col_right:
        st.markdown(f"#### 📍 {selected_station}")

        if not is_supported:
            st.markdown(f"""
            <div class="metric-card">
              <div class="label">{poll_lbl}</div>
              <div class="value aqi-disabled">— {units}</div>
              <div style="font-size:12px;color:#57606a;margin-top:4px">
                No disponible para esta estación.<br>
                El modelo no tiene datos de entrenamiento para esta centralita.<br>
                Selecciona otra estación o cambia el contaminante.
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            fc_sel = forecasts_p[selected_station]
            val_now  = fc_sel[0]
            val_pred = fc_sel[hour_idx]
            delta    = val_pred - val_now

            # Card 1: predicción para ahora
            st.markdown(f"""
            <div class="metric-card">
              <div class="label">{poll_lbl} previsto · {now_str}</div>
              <div class="value {aqi_class(val_now, pollutant)}">{val_now:.1f} {units}</div>
              <div style="font-size:12px;color:#57606a;margin-top:4px">{aqi_label(val_now, pollutant)}</div>
            </div>
            """, unsafe_allow_html=True)

            # Card 2: predicción para una fecha futura (solo si hour_idx > 0)
            if hour_idx > 0:
                st.markdown(f"""
                <div class="metric-card">
                  <div class="label">{poll_lbl} previsto · {pred_time_str} (+{hour_idx} h)</div>
                  <div class="value {aqi_class(val_pred, pollutant)}">{val_pred:.1f} {units}
                    <span style="font-size:14px;color:#57606a"> ({'+' if delta >= 0 else ''}{delta:.1f})</span>
                  </div>
                  <div style="font-size:12px;color:#57606a;margin-top:4px">{aqi_label(val_pred, pollutant)}</div>
                </div>
                """, unsafe_allow_html=True)

        # ── Contaminantes actuales (medida real GVA) ─────────────
        # Para los gases en los que la estación está en el modelo: lectura real.
        # Para los gases en los que la estación NO está en el modelo: forzar 0
        # (el dato real existe en la GVA pero el modelo no lo cubre — para evitar
        # que el usuario vea valores contradictorios entre los cards de previsión
        # y las medidas).
        air = current.get(selected_station) or {}

        def _gas_display(gas: str) -> tuple[str, str]:
            v = air.get(gas)
            if v is None:
                return "—", "#9e9e9e"
            if selected_station not in supported.get(gas, []):
                return "—", "#9e9e9e"
            return f"{v:.1f}", "#1f2328"

        o3_txt,   o3_color   = _gas_display("O3")
        no2_txt,  no2_color  = _gas_display("NO2")
        pm25_txt, pm25_color = _gas_display("PM25")

        gva_label = f"Medida GVA · {last_real_label}" if last_real_label else "Medida GVA"
        st.markdown(f"""
        <div class="metric-card" style="margin-top:8px">
          <div class="label">{gva_label}</div>
          <div style="display:flex;gap:16px;margin-top:8px">
            <div><div style="font-size:10px;color:#57606a">O₃</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace;color:{o3_color}">{o3_txt}</div></div>
            <div><div style="font-size:10px;color:#57606a">NO₂</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace;color:{no2_color}">{no2_txt}</div></div>
            <div><div style="font-size:10px;color:#57606a">PM2.5</div>
                 <div style="font-size:18px;font-family:'Space Mono',monospace;color:{pm25_color}">{pm25_txt}</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"#### 📊 Resumen estaciones · {poll_lbl}")
        rows = []
        for name in station_names:
            if name in supported_p:
                fc = forecasts_p[name]
                rows.append({
                    "Estación": name,
                    "Ahora": f"{fc[0]:.1f}",
                    f"+{hour_idx}h": f"{fc[hour_idx]:.1f}",
                    "Estado": aqi_label(fc[hour_idx], pollutant),
                })
            else:
                rows.append({
                    "Estación": name,
                    "Ahora": "—",
                    f"+{hour_idx}h": "—",
                    "Estado": "no disponible",
                })
        df_summary = pd.DataFrame(rows).set_index("Estación")
        st.dataframe(df_summary, width="stretch", height=320)

    st.markdown(f"#### 📈 Tendencia 7 días · {selected_station} · {poll_lbl}")
    fig = build_forecast_chart(forecasts_p, selected_station, pollutant)
    st.plotly_chart(fig, width="stretch")

    st.markdown("""
    <hr style="border-color:#d0d7de;margin-top:32px">
    <p style="text-align:center;font-size:11px;color:#57606a;font-family:'DM Sans',sans-serif">
      Datos: RVVCCA GVA · Open-Meteo · Pipeline CBLA multi-estación (CNN-BiLSTM + XGBoost) servido por API FastAPI
    </p>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
