# Calidad del Aire · Valencia

Dashboard de la calidad del aire en la ciudad de Valencia con previsión de hasta 7 días
para **PM2.5, NO₂ y O₃**. Lee las lecturas reales en vivo de la red RVVCCA (GVA) y las
previsiones de un CSV generado por el equipo de modelado del proyecto.

Arquitectura **frontend (Streamlit) + API (FastAPI)**, sin librerías ML pesadas en este
repo — el entrenamiento del modelo y la generación del CSV viven fuera.

```
┌──────────────────────┐  GET /snapshot   ┌──────────────────────────────────┐
│ frontend/ (Streamlit)│ ◄──────────────► │ backend/ (FastAPI + APScheduler) │
│ mapa Folium + Plotly │   POST /refresh  │                                  │
└──────────────────────┘                  └──────────────────────────────────┘
                                                  │
                                                  ▼
                          ┌────────────────────────────────────────────────┐
                          │  Fuentes de datos                              │
                          │  • predicciones_contaminantes.csv  (modelo)    │
                          │  • rvvcca.pica.gva.es              (real-time) │
                          │  • api.open-meteo.com              (meteo)     │
                          └────────────────────────────────────────────────┘
```

## Ejecución local

Hacen falta **dos terminales** simultáneas.

### Terminal 1 — backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (en mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env

# Colocar el CSV de previsiones generado por el equipo de modelado:
mkdir -p data
cp /ruta/al/predicciones_contaminantes.csv data/

# Arrancar la API (desde la raíz del proyecto, NO desde backend/):
cd ..
uvicorn backend.main:app --reload --port 8000
```

Swagger interactivo: <http://localhost:8000/docs>

### Terminal 2 — frontend

```bash
cd frontend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

streamlit run app.py
```

Abre <http://localhost:8501>.

## Estructura del repo

```
backend/
├── main.py             # Endpoints FastAPI: /snapshot /stations /forecast /refresh /health
├── snapshot.py         # Combina las 3 fuentes en una respuesta cacheada in-memory
├── forecast_loader.py  # Lee el CSV de previsiones (con cache por mtime)
├── scrape.py           # Lecturas reales de la GVA (endpoint Pentaho JSON)
├── weather.py          # Meteo actual + forecast desde Open-Meteo
├── stations.py         # Catálogo de centralitas + cobertura física por contaminante
├── scheduler.py        # APScheduler que regenera el snapshot cada 60 min
├── schemas.py          # Pydantic models del contrato HTTP
├── config.py           # Variables de entorno
├── data/               # (gitignored) CSV de previsiones
└── Dockerfile          # Para despliegue en HF Spaces, si se quiere implementar en un futuro

frontend/
├── app.py              # Streamlit thin client
├── ui.py               # Mapa Folium, gráfica Plotly, categorías AQI
└── api_client.py       # Cliente HTTP al backend
```

## Datos

- **9 centralitas RVVCCA** en Valencia ciudad (Av. França, Centre, Vivers, Bulevard
  Sud, etc.). Códigos públicos en `backend/stations.py:STATION_CODES`.
- **3 contaminantes**: PM2.5, NO₂, O₃ — con cobertura física distinta por estación
  (algunas no miden ciertos gases; aparecen en gris en el mapa).
- **168 horas (7 días) de previsión** consecutivas, alineadas al timestamp del CSV.

## Despliegue (no esta activo)

- **Frontend** → Streamlit Community Cloud (gratis, basta apuntar `API_URL` al backend).
- **Backend** → Hugging Face Spaces con SDK Docker (gratis; el `Dockerfile` está listo).

Ver `backend/README.md` para detalles del despliegue del backend.
