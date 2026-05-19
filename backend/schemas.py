"""Pydantic schemas — contrato HTTP del backend."""
from datetime import datetime
from pydantic import BaseModel, Field


class Station(BaseModel):
    name: str
    lat: float
    lon: float


class Meteo(BaseModel):
    Temperatura: float
    Humedad_relativa: float
    Presion: float
    Velocidad_viento: float
    Direccion_viento: float
    Precipitacion: float


class AirReading(BaseModel):
    O3: float
    NO2: float
    PM25: float


class Snapshot(BaseModel):
    """Estado completo de la red en un instante dado.

    `forecasts` es un dict {nombre_estacion → 169 valores horarios de PM2.5}, donde
    el índice 0 es t=0 (hora actual) y el 168 es t+168h (=7 días).
    `current` recoge las mediciones actuales de O3/NO2/PM2.5 por estación.
    """
    generated_at: datetime
    stations: list[Station]
    meteo: Meteo
    forecasts: dict[str, list[float]]
    current: dict[str, AirReading]


class HealthResponse(BaseModel):
    status: str = "ok"
    last_snapshot: datetime | None = None
    next_refresh_in_min: int = Field(default=0, description="Minutos hasta el próximo refresco programado")
