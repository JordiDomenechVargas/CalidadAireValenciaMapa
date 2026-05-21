"""Helpers de UI para la Streamlit: categorías AQI por contaminante, mapa Folium, gráfico Plotly."""
from datetime import datetime, timedelta

import folium
import plotly.graph_objects as go

# ── Categorías oficiales GVA por contaminante (µg/m³) ──
# Cada tupla: (umbral_superior_exclusivo, etiqueta, color hex, clase CSS).

PM25_LEVELS = [
    (11,    "Buena",                       "#00CCCC", "aqi-1"),
    (21,    "Razonablemente buena",        "#2E9D5B", "aqi-2"),
    (26,    "Regular",                     "#D4A017", "aqi-3"),
    (51,    "Desfavorable",                "#E64A19", "aqi-4"),
    (76,    "Muy desfavorable",            "#960018", "aqi-5"),
    (10000, "Extremadamente desfavorable", "#7D2181", "aqi-6"),
]

NO2_LEVELS = [
    (41,    "Buena",                       "#00CCCC", "aqi-1"),
    (91,    "Razonablemente buena",        "#2E9D5B", "aqi-2"),
    (121,   "Regular",                     "#D4A017", "aqi-3"),
    (231,   "Desfavorable",                "#E64A19", "aqi-4"),
    (341,   "Muy desfavorable",            "#960018", "aqi-5"),
    (10000, "Extremadamente desfavorable", "#7D2181", "aqi-6"),
]

O3_LEVELS = [
    (51,    "Buena",                       "#00CCCC", "aqi-1"),
    (101,   "Razonablemente buena",        "#2E9D5B", "aqi-2"),
    (131,   "Regular",                     "#D4A017", "aqi-3"),
    (241,   "Desfavorable",                "#E64A19", "aqi-4"),
    (381,   "Muy desfavorable",            "#960018", "aqi-5"),
    (10000, "Extremadamente desfavorable", "#7D2181", "aqi-6"),
]

LEVELS_BY_POLLUTANT = {"PM25": PM25_LEVELS, "NO2": NO2_LEVELS, "O3": O3_LEVELS}

POLLUTANT_LABELS = {"PM25": "PM2.5", "NO2": "NO₂", "O3": "O₃"}
POLLUTANT_UNITS  = {"PM25": "µg/m³", "NO2": "µg/m³", "O3": "µg/m³"}

GRAY_DISABLED = "#9e9e9e"

# Radio común de representatividad espacial para todas las centralitas (metros).
# Valor medio razonable según la Directiva 2008/50/EC: ~500 m cubre el área que
# una centralita urbana típica representa estadísticamente.
COVERAGE_RADIUS_M = 750


def _bucket(val: float, pollutant: str) -> tuple[str, str, str]:
    """Devuelve (etiqueta, color, clase CSS) según el nivel del contaminante."""
    levels = LEVELS_BY_POLLUTANT.get(pollutant, PM25_LEVELS)
    for thr, label, color, cls in levels:
        if val < thr:
            return label, color, cls
    return levels[-1][1], levels[-1][2], levels[-1][3]


def aqi_color(val: float, pollutant: str) -> str: return _bucket(val, pollutant)[1]
def aqi_label(val: float, pollutant: str) -> str: return _bucket(val, pollutant)[0]
def aqi_class(val: float, pollutant: str) -> str: return _bucket(val, pollutant)[2]


def build_map(
    stations: list[dict],
    forecasts_for_pollutant: dict[str, list[float]],
    hour_idx: int,
    selected: str | None,
    pollutant: str,
    supported_stations: list[str],
    show_coverage: bool = False,
) -> folium.Map:
    """Mapa Folium con un CircleMarker por estación.

    - Si la estación está en `supported_stations`: color según AQI del valor previsto.
    - Si no: color gris y tooltip indicando "no disponible".
    """
    m = folium.Map(location=[39.4697, -0.3774], zoom_start=12, tiles="CartoDB positron")
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    dt_label = (now + timedelta(hours=hour_idx)).strftime("%d/%m/%Y %H:%M")
    poll_lbl = POLLUTANT_LABELS[pollutant]
    units    = POLLUTANT_UNITS[pollutant]

    for st in stations:
        name = st["name"]
        lat, lon = st["lat"], st["lon"]
        is_selected  = name == selected
        is_supported = name in supported_stations

        if is_supported:
            fc = forecasts_for_pollutant.get(name, [0.0] * 169)
            current = fc[0]
            predicted = fc[hour_idx] if hour_idx < len(fc) else fc[-1]
            color = aqi_color(predicted, pollutant)
            popup_html = f"""
            <div style="font-family:'DM Sans',sans-serif;min-width:200px;background:#ffffff;
                        color:#1f2328;padding:12px;border-radius:8px;border:1px solid #d0d7de;
                        box-shadow:0 2px 8px rgba(31,35,40,0.12);">
              <b style="font-family:'Space Mono',monospace;font-size:13px">{name}</b><br>
              <hr style="border-color:#d0d7de;margin:6px 0">
              <span style="font-size:11px;color:#57606a">{poll_lbl} AHORA (t=0)</span><br>
              <span style="font-size:22px;font-weight:700;color:{aqi_color(current, pollutant)}">{current:.1f} {units}</span>
              <br><br>
              <span style="font-size:11px;color:#57606a">PREVISIÓN · {dt_label}</span><br>
              <span style="font-size:22px;font-weight:700;color:{color}">{predicted:.1f} {units}</span>
              <br>
              <span style="font-size:11px;color:{color};background:rgba(255,255,255,0.05);
                           padding:2px 6px;border-radius:4px">{aqi_label(predicted, pollutant)}</span>
            </div>
            """
            tooltip = name
        else:
            color = GRAY_DISABLED
            popup_html = f"""
            <div style="font-family:'DM Sans',sans-serif;min-width:200px;background:#ffffff;
                        color:#1f2328;padding:12px;border-radius:8px;border:1px solid #d0d7de;">
              <b style="font-family:'Space Mono',monospace;font-size:13px">{name}</b><br>
              <hr style="border-color:#d0d7de;margin:6px 0">
              <span style="color:#57606a;font-size:12px">
                {poll_lbl} no disponible para esta estación.<br>
                El modelo no tiene datos de entrenamiento para esta centralita.
              </span>
            </div>
            """
            tooltip = f"{name} · {poll_lbl} no disponible"

        radius = 14 if is_selected else 10
        border = "#ffffff" if is_selected else "#555555"
        border_w = 3 if is_selected else 1.5

        # Zona de representatividad (círculo geográfico, radio en metros)
        if show_coverage:
            folium.Circle(
                location=[lat, lon],
                radius=COVERAGE_RADIUS_M,
                color=color,
                weight=1.5 if is_selected else 1,
                fill=True,
                fill_color=color,
                fill_opacity=0.12,
                opacity=0.45,
            ).add_to(m)

        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            color=border,
            weight=border_w,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=tooltip,
        ).add_to(m)

    # Leyenda dinámica según el contaminante
    levels = LEVELS_BY_POLLUTANT[pollutant]
    range_strings = []
    prev_thr = 0
    for thr, label, color, _cls in levels[:-1]:
        range_strings.append((f"{prev_thr}–{thr-1}", label, color))
        prev_thr = thr
    range_strings.append((f"≥{levels[-2][0]}", levels[-1][1], levels[-1][2]))

    legend_rows = "<br>".join(
        f'<span style="color:{c}">●</span> {r} · {lbl}'
        for r, lbl, c in range_strings
    )
    legend_html = f"""
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;
                background:white;border:1px solid #ccc;border-radius:8px;
                padding:12px 16px;font-family:'DM Sans',sans-serif;color:#333;font-size:12px;
                box-shadow:0 2px 8px rgba(0,0,0,0.15);">
      <b style="font-family:'Space Mono',monospace">{poll_lbl} {units}</b><br>
      {legend_rows}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


_DAYS_ES   = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
_MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic"]


def build_forecast_chart(forecasts_for_pollutant: dict, station: str, pollutant: str) -> go.Figure:
    """Gráfico Plotly de la previsión 168 h. Si la estación no está en el dict (no soportada),
    devuelve una figura con texto explicativo."""
    poll_lbl = POLLUTANT_LABELS[pollutant]
    units    = POLLUTANT_UNITS[pollutant]

    if station not in forecasts_for_pollutant:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text=f"<b>{station}</b><br>{poll_lbl} no disponible para esta estación.",
            showarrow=False,
            font=dict(family="DM Sans", size=14, color="#57606a"),
        )
        fig.update_layout(
            paper_bgcolor="#ffffff", plot_bgcolor="#f6f8fa",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            height=320, margin=dict(l=20, r=20, t=20, b=20),
        )
        return fig

    fc = forecasts_for_pollutant[station]
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    times = [now + timedelta(hours=h) for h in range(len(fc))]

    fig = go.Figure()

    levels = LEVELS_BY_POLLUTANT[pollutant]
    prev_thr = 0
    for thr, label, color, _cls in levels:
        # Convertir color hex a rgba con opacidad baja
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        rgba = f"rgba({r},{g},{b},0.10)"
        upper = thr if thr < 10000 else max(max(fc) * 1.2, prev_thr + 100)
        fig.add_hrect(y0=prev_thr, y1=upper, fillcolor=rgba, line_width=0,
                      annotation_text=label, annotation_position="left",
                      annotation_font_color="#8b949e", annotation_font_size=10)
        prev_thr = thr

    fig.add_trace(go.Scatter(
        x=times, y=fc,
        mode="lines",
        name=f"{poll_lbl} previsto",
        line=dict(color="#58a6ff", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(88,166,255,0.06)",
        hovertemplate="%{x|%d/%m %H:%M}<br><b>%{y:.1f} " + units + "</b><extra></extra>",
    ))

    fig.add_vline(x=times[0], line_dash="dash", line_color="#57606a", line_width=1)
    fig.add_annotation(x=times[0], y=max(fc) * 0.9, text="Ahora",
                       showarrow=False, font=dict(color="#57606a", size=11))

    # Ticks personalizados con nombres de día en español (Plotly no respeta locale Python).
    # Uno cada 12 h; el primero y el último siempre presentes.
    tick_idx = list(range(0, len(times), 12))
    if (len(times) - 1) not in tick_idx:
        tick_idx.append(len(times) - 1)
    tickvals = [times[i] for i in tick_idx]
    ticktext = [f"{_DAYS_ES[times[i].weekday()]} {times[i].day:02d}<br>{times[i].strftime('%H:%M')}"
                for i in tick_idx]

    fig.update_layout(
        title=dict(
            text=f"<b>{station}</b> · Previsión {poll_lbl} 168 h",
            font=dict(family="Space Mono", size=14, color="#1f2328"),
        ),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f6f8fa",
        font=dict(family="DM Sans", color="#57606a"),
        xaxis=dict(
            showgrid=True, gridcolor="#eaecef",
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
            color="#57606a", title=None,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#eaecef", title=units,
            color="#57606a", range=[0, max(max(fc) * 1.15, 60)],
        ),
        margin=dict(l=50, r=20, t=50, b=40),
        height=320,
        legend=dict(bgcolor="#ffffff", bordercolor="#d0d7de"),
        hovermode="x unified",
    )
    return fig
