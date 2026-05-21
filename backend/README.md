# Backend · API de predicciones PM2.5 · Valencia

FastAPI que scrapea la red RVVCCA + Meteostat cada hora, ejecuta el pipeline CBLA
(CNN-BiLSTM + XGBoost) y expone las predicciones de 168 h vía HTTP.

## Arrancar local

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
cp .env.example .env            # ajusta valores si quieres

# Copia los modelos a backend/models/ (no están en git):
mkdir models
cp ../cnn_bilstm_attention_h1.keras models/
cp ../xgb_meta_model_h1.json       models/
cp ../scaler_h1.pkl                models/

# Arranque (desde la raíz del proyecto, NO desde backend/):
cd ..
uvicorn backend.main:app --reload --port 8000
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado + timestamp del último snapshot. |
| `GET` | `/stations` | Catálogo de las 10 centralitas (nombre, lat, lon). |
| `GET` | `/snapshot` | Snapshot completo (recomendado para el frontend). |
| `GET` | `/forecast/{station_name}` | 169 valores horarios (t=0 … t+168 h) de PM2.5. |
| `POST` | `/refresh` | Fuerza un re-scrape + re-predict. Header `X-Refresh-Token` si está configurado. |

Documentación interactiva: `http://localhost:8000/docs`

## Arquitectura

```
main.py (FastAPI app)
   ↓ startup
scheduler.py (APScheduler cada N min)
   ↓ ejecuta cada N min
snapshot.py (regenera Snapshot global)
   ↓ usa
scrape.py   (RVVCCA + Meteostat)
predict.py  (CNN-BiLSTM + XGBoost, 168 h recursivo)
```

El primer snapshot se genera al arrancar la API (en `lifespan`).
Cada `REFRESH_INTERVAL_MINUTES` (default 60) el scheduler vuelve a regenerarlo en segundo plano.
Los endpoints leen el snapshot in-memory, así que las respuestas son instantáneas.

## Despliegue en Hugging Face Spaces

1. Crea un nuevo Space con SDK = **Docker**.
2. Copia el contenido de `backend/` al Space (puedes hacer un mirror via git).
3. Sube los modelos a `backend/models/` usando Git LFS, o referencia desde HF Hub.
4. Configura las variables de entorno en la pestaña *Settings* del Space.
