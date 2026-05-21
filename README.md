# Calidad del Aire · Valencia

Dashboard de predicción PM2.5 (168 h) para la red RVVCCA de Valencia.
Arquitectura **frontend + API**:

```
┌──────────────────┐         HTTP /snapshot         ┌────────────────────────┐
│  frontend/       │ ◄─────────────────────────────►│  backend/              │
│  Streamlit       │                                │  FastAPI               │
│  + Folium        │                                │  + APScheduler         │
│                  │                                │  + CBLA pipeline       │
└──────────────────┘                                │  (CNN-BiLSTM + XGB)    │
                                                    │  + Scraping RVVCCA     │
                                                    │  + Scraping Meteostat  │
                                                    └────────────────────────┘
```

El backend ejecuta el pipeline ML en su propio proceso, refresca el snapshot cada hora
con APScheduler y lo cachea en memoria. La Streamlit es un cliente delgado que sólo
hace `GET /snapshot` y pinta el resultado.

## Ejecución local

Necesitas **dos terminales** simultáneas.

### Terminal 1 — backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env

# Copia los modelos a backend/models/ (no están en git por tamaño):
mkdir models
cp ../cnn_bilstm_attention_h1.keras models/
cp ../xgb_meta_model_h1.json       models/
cp ../scaler_h1.pkl                models/

# Arrancar desde la raíz del proyecto:
cd ..
uvicorn backend.main:app --reload --port 8000
```

Documentación Swagger: `http://localhost:8000/docs`

### Terminal 2 — frontend

```bash
cd frontend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

streamlit run app.py
```

Abre `http://localhost:8501`.

## Estructura del repo

- `backend/` — API FastAPI con scheduler, modelos y scraping.
- `frontend/` — Streamlit cliente delgado que consume la API.
- `cnn_bilstm_attention_h1.keras`, `xgb_meta_model_h1.json`, `scaler_h1.pkl` — modelos
  entrenados (gitignored; copiar a `backend/models/` para arrancar el backend).

## Despliegue

- **Backend** → Hugging Face Spaces (SDK Docker). Ver `backend/README.md`.
- **Frontend** → Streamlit Community Cloud o cualquier hosting que ejecute `streamlit run`.
  Solo necesita la variable de entorno `API_URL` apuntando al Space.
