"""API FastAPI — Calidad del Aire Valencia.

Endpoints:
  GET  /health                  → estado + timestamp del snapshot
  GET  /stations                → catálogo de centralitas
  GET  /snapshot                → snapshot completo (estaciones + meteo + forecasts + current)
  GET  /forecast/{station_name} → forecast 169h de una estación concreta
  POST /refresh                 → fuerza un re-scrape + re-predict (requiere token)
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

from .config import REFRESH_INTERVAL_MINUTES, REFRESH_TOKEN
from .schemas import HealthResponse, Snapshot, Station
from .snapshot import get_snapshot, regenerate_snapshot
from .scheduler import start_scheduler, shutdown_scheduler, get_scheduler
from .stations import STATIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)s · %(name)s · %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Genera el primer snapshot y arranca el scheduler al iniciar la API."""
    logger.info("Arranque de la API · generando snapshot inicial…")
    try:
        regenerate_snapshot()
    except Exception as e:  # noqa: BLE001
        logger.exception("Snapshot inicial falló: %s", e)
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Calidad del Aire · Valencia · API",
    description="API de predicciones PM2.5 a 168 h para la red RVVCCA de Valencia.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS abierto — el frontend Streamlit lo necesita y la API es pública.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health():
    snap = get_snapshot()
    last = snap.generated_at if snap else None
    next_in = 0
    sched = get_scheduler()
    if sched and last is not None:
        # Aproxima minutos restantes hasta el próximo tick del job.
        elapsed = (datetime.now() - last).total_seconds() / 60
        next_in = max(0, int(REFRESH_INTERVAL_MINUTES - elapsed))
    return HealthResponse(status="ok", last_snapshot=last, next_refresh_in_min=next_in)


@app.get("/stations", response_model=list[Station])
def stations():
    return [Station(name=n, lat=lat, lon=lon) for n, (lat, lon) in STATIONS.items()]


@app.get("/snapshot", response_model=Snapshot)
def snapshot():
    snap = get_snapshot()
    if snap is None:
        raise HTTPException(status_code=503, detail="Snapshot todavía no disponible — reintenta en unos segundos.")
    return snap


@app.get("/forecast/{station_name}", response_model=list[float])
def forecast(station_name: str):
    snap = get_snapshot()
    if snap is None:
        raise HTTPException(status_code=503, detail="Snapshot todavía no disponible.")
    if station_name not in snap.forecasts:
        raise HTTPException(status_code=404, detail=f"Estación '{station_name}' no existe.")
    return snap.forecasts[station_name]


@app.post("/refresh", response_model=HealthResponse)
def refresh(x_refresh_token: str | None = Header(default=None, alias="X-Refresh-Token")):
    """Fuerza un re-scrape + re-predict inmediato. Si REFRESH_TOKEN está configurado en
    el .env, exige el header `X-Refresh-Token`."""
    if REFRESH_TOKEN and x_refresh_token != REFRESH_TOKEN:
        raise HTTPException(status_code=401, detail="Token de refresco inválido.")
    snap = regenerate_snapshot()
    return HealthResponse(status="ok", last_snapshot=snap.generated_at, next_refresh_in_min=REFRESH_INTERVAL_MINUTES)
