"""Helpers de UI para la Streamlit: categorías PM2.5, mapa Folium, gráfico Plotly."""
from datetime import datetime, timedelta

import folium
import plotly.graph_objects as go

# ── Categorías oficiales de calidad del aire para PM2.5 (µg/m³) ──
# Cada tupla: (umbral_superior_exclusivo, etiqueta, color hex, clase CSS).
PM25_LEVELS = [
    (11,    "Buena",                       "#00CCCC", "aqi-1"),
    (21,    "Razonablemente buena",        "#2E9D5B", "aqi-2"),
    (26,    "Regular",                     "#D4A017", "aqi-3"),
    (51,    "Desfavorable",                "#E64A19", "aqi-4"),
    (76,    "Muy desfavorable",            "#960018", "aqi-5"),
    (10000, "Extremadamente desfavorable", "#7D2181", "aqi-6"),
]


def _pm25_bucket(val: float) -> tuple[str, str, str]:
    """Devuelve (etiqueta, color, clase CSS) según el nivel PM2.5."""
    for thr, label, color, cls in PM25_LEVELS:
        if val < thr:
            return label, color, cls
    return PM25_LEVELS[-1][1], PM25_LEVELS[-1][2], PM25_LEVELS[-1][3]


def pm25_color(val: float) -> str:
    return _pm25_bucket(val)[1]


def pm25_label(val: float) -> str:
    return _pm25_bucket(val)[0]


def pm25_class(val: float) -> str:
    return _pm25_bucket(val)[2]


def build_map(stations: list[dict], forecasts: dict, hour_idx: int, selected: str | None) -> folium.Map:
    """Crea el mapa Folium con un CircleMarker por estación coloreado según PM2.5.

    `stations` es una lista de dicts {name, lat, lon} (vienen del endpoint /stations).
    `forecasts` es un dict {station → list[169 floats]}.
    """
    m = folium.Map(
        location=[39.4697, -0.3774],
        zoom_start=12,
        tiles="CartoDB positron",
    )
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    dt_label = (now + timedelta(hours=hour_idx)).strftime("%d/%m/%Y %H:%M")

    for st in stations:
        name = st["name"]
        lat, lon = st["lat"], st["lon"]
        fc = forecasts.get(name, [15.0] * 169)
        current = fc[0]
        predicted = fc[hour_idx] if hour_idx < len(fc) else fc[-1]
        color = pm25_color(predicted)
        is_selected = name == selected

        radius = 14 if is_selected else 10
        border = "#ffffff" if is_selected else "#555555"
        border_w = 3 if is_selected else 1.5

        popup_html = f"""
        <div style="font-family:'DM Sans',sans-serif;min-width:200px;background:#ffffff;
                    color:#1f2328;padding:12px;border-radius:8px;border:1px solid #d0d7de;
                    box-shadow:0 2px 8px rgba(31,35,40,0.12);">
          <b style="font-family:'Space Mono',monospace;font-size:13px">{name}</b><br>
          <hr style="border-color:#d0d7de;margin:6px 0">
          <span style="font-size:11px;color:#57606a">AHORA (t=0)</span><br>
          <span style="font-size:22px;font-weight:700;color:{pm25_color(current)}">{current:.1f} µg/m³</span>
          <br><br>
          <span style="font-size:11px;color:#57606a">PREVISIÓN · {dt_label}</span><br>
          <span style="font-size:22px;font-weight:700;color:{color}">{predicted:.1f} µg/m³</span>
          <br>
          <span style="font-size:11px;color:{color};background:rgba(255,255,255,0.05);
                       padding:2px 6px;border-radius:4px">{pm25_label(predicted)}</span>
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
            tooltip=name,
        ).add_to(m)

    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;
                background:white;border:1px solid #ccc;border-radius:8px;
                padding:12px 16px;font-family:'DM Sans',sans-serif;color:#333;font-size:12px;
                box-shadow:0 2px 8px rgba(0,0,0,0.15);">
      <b style="font-family:'Space Mono',monospace">PM2.5 µg/m³</b><br>
      <span style="color:#00CCCC">●</span> 0–10 · Buena<br>
      <span style="color:#2E9D5B">●</span> 11–20 · Razonablemente buena<br>
      <span style="color:#D4A017">●</span> 21–25 · Regular<br>
      <span style="color:#E64A19">●</span> 26–50 · Desfavorable<br>
      <span style="color:#960018">●</span> 51–75 · Muy desfavorable<br>
      <span style="color:#7D2181">●</span> &ge;76 · Extremadamente desfavorable
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


def build_forecast_chart(forecasts: dict, station: str) -> go.Figure:
    """Gráfico Plotly con la línea de previsión 168h + bandas AQI de fondo."""
    fc = forecasts.get(station, [15.0] * 169)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    times = [now + timedelta(hours=h) for h in range(len(fc))]

    fig = go.Figure()

    # Áreas AQI (fondo)
    for ymin, ymax, color, label in [
        (0,  11,  "rgba(0,204,204,0.10)",   "Buena"),
        (11, 21,  "rgba(46,157,91,0.10)",   "Razonablemente buena"),
        (21, 26,  "rgba(212,160,23,0.10)",  "Regular"),
        (26, 51,  "rgba(230,74,25,0.10)",   "Desfavorable"),
        (51, 76,  "rgba(150,0,24,0.10)",    "Muy desfavorable"),
        (76, 800, "rgba(125,33,129,0.10)",  "Extremadamente desfavorable"),
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
    fig.add_vline(x=times[0], line_dash="dash", line_color="#57606a", line_width=1)
    fig.add_annotation(x=times[0], y=max(fc) * 0.9, text="Ahora",
                       showarrow=False, font=dict(color="#57606a", size=11))

    fig.update_layout(
        title=dict(
            text=f"<b>{station}</b> · Previsión PM2.5 168h",
            font=dict(family="Space Mono", size=14, color="#1f2328"),
        ),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f6f8fa",
        font=dict(family="DM Sans", color="#57606a"),
        xaxis=dict(
            showgrid=True, gridcolor="#eaecef", tickformat="%a %d\n%H:%M",
            color="#57606a", title=None,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#eaecef", title="µg/m³",
            color="#57606a", range=[0, max(max(fc) * 1.15, 60)],
        ),
        margin=dict(l=50, r=20, t=50, b=40),
        height=320,
        legend=dict(bgcolor="#ffffff", bordercolor="#d0d7de"),
        hovermode="x unified",
    )
    return fig
