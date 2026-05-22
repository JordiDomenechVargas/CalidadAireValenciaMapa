# Backend · API de calidad del aire de Valencia

FastAPI que combina **tres fuentes** y las sirve al frontend en una única respuesta
cacheada (Snapshot) que se regenera periódicamente con APScheduler:

| Fuente | De dónde sale | Para qué se usa |
|---|---|---|
| Previsiones PM2.5/NO₂/O₃ | `data/predicciones_contaminantes.csv` | Card "previsto" + mapa + gráfica |
| Lecturas reales actuales | endpoint Pentaho JSON de rvvcca.pica.gva.es | Card "Medida GVA" |
| Meteo actual | api.open-meteo.com | Card de Meteorología |

**Sin librerías ML en este servicio**: las predicciones las genera otro equipo y se
entregan ya pre-calculadas en el CSV. Aquí solo se lee, mapea y sirve.

## Arrancar local

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
cp .env.example .env            # ajustar si quieres

# Colocar el CSV de previsiones en backend/data/
mkdir -p data
cp /ruta/al/predicciones_contaminantes.csv data/

# Arranque desde la raíz del proyecto (NO desde backend/):
cd ..
uvicorn backend.main:app --reload --port 8000
```

Swagger: <http://localhost:8000/docs>

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado + timestamps de snapshot y última lectura GVA + lista de contaminantes |
| `GET` | `/stations` | Catálogo de las 9 centralitas con lat/lon |
| `GET` | `/snapshot` | Respuesta principal: contaminantes, previsiones, meteo y lecturas reales |
| `GET` | `/forecast/{pollutant}/{station_name}` | 168 valores horarios de una estación (PM25/NO2/O3) |
| `POST` | `/refresh` | Fuerza una regeneración inmediata. Header opcional `X-Refresh-Token` si está configurado |

## Arquitectura interna

```
main.py (FastAPI app)
   ↓ startup
scheduler.py (APScheduler · cada REFRESH_INTERVAL_MINUTES)
   ↓ dispara
snapshot.py:_build_snapshot()
   ↓ combina
   ┌────────────────────────┬────────────────────────┬─────────────────────────┐
   ▼                        ▼                        ▼                         │
forecast_loader.py    scrape.py                   weather.py                   │
(CSV con cache mtime) (RVVCCA Pentaho JSON)       (Open-Meteo, 240 h hourly)   │
   ↓                                                                            
Snapshot in-memory ──── lo expone main.py vía /snapshot
```

- Al arrancar la API se genera el primer snapshot en `lifespan`.
- Cada `REFRESH_INTERVAL_MINUTES` (default 60) el scheduler lo regenera en background.
- Los endpoints leen el snapshot in-memory → respuesta < 1 ms.
- El CSV se relee con detección de mtime: si tus compañeros no lo han actualizado,
  no se relee (se devuelve la versión cacheada).

## Cobertura por contaminante

El CSV contiene previsiones para 10 estaciones × 3 contaminantes, pero filtramos según
`PHYSICAL_COVERAGE` (centralitas con sensor real de cada gas según la RVVCCA):

- **PM2.5**: 7 estaciones (sin Vivers, sin Bulevard Sud)
- **NO₂**: 9 estaciones (todas)
- **O₃**: 8 estaciones (sin Centre)

Las estaciones sin cobertura física se devuelven en `supported_stations` excluidas para
ese contaminante, y el frontend las pinta en gris en el mapa.

## Despliegue en Hugging Face Spaces

1. Crea un nuevo Space con SDK = **Docker**.
2. Sube el contenido de `backend/` al Space (vía `git push` al remote del Space).
3. Sube el CSV al Space en `data/predicciones_contaminantes.csv` — usa Git LFS si pesa
   más de unos pocos MB, o un job que lo descargue del Drive del equipo (ver TODO).
4. Configura variables de entorno en *Settings*:
   - `REFRESH_INTERVAL_MINUTES=60`
   - `WEATHER_LAT=39.4697`, `WEATHER_LON=-0.3774`, `WEATHER_TZ=Europe/Madrid`
   - `REFRESH_TOKEN` opcional si quieres proteger `POST /refresh`

## Variables de entorno

Ver `.env.example`. Las principales:

| Variable | Default | Para qué |
|---|---|---|
| `REFRESH_INTERVAL_MINUTES` | `60` | Frecuencia del scheduler |
| `REFRESH_TOKEN` | (vacío) | Si lo defines, `POST /refresh` exige `X-Refresh-Token` |
| `WEATHER_LAT`, `WEATHER_LON` | Valencia centro | Coordenadas para Open-Meteo |
| `WEATHER_TZ` | `Europe/Madrid` | Zona horaria de Open-Meteo |
