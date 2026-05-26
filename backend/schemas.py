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
    """Última lectura real publicada por la GVA para esa estación. Cada gas es
    `None` si la centralita no tiene sensor para ese contaminante (p. ej. Centre
    no mide O3, Vivers no mide PM2.5)."""
    O3: float | None = None
    NO2: float | None = None
    PM25: float | None = None


class Snapshot(BaseModel):
    """Estado completo de la red.

    `forecasts[pollutant][station]` = lista de 168 valores horarios consecutivos
    empezando en `forecast_start_at`. Para una hora target T, el índice en la lista
    es `int((T - forecast_start_at).total_seconds() / 3600)`, clamped a [0, 167].

    `supported_stations[pollutant]` = lista canónica de estaciones que el CSV cubre
    para ese contaminante. Actualmente las 9 están en los 3, pero se mantiene la
    estructura por flexibilidad futura.
    """
    generated_at: datetime
    forecast_start_at: datetime
    last_real_data_at: datetime | None = None
    stations: list[Station]
    meteo: Meteo
    current: dict[str, AirReading]
    forecasts: dict[str, dict[str, list[float]]]
    supported_stations: dict[str, list[str]]


class HealthResponse(BaseModel):
    status: str = "ok"
    last_snapshot: datetime | None = None
    last_real_data_at: datetime | None = None
    next_refresh_in_min: int = Field(default=0, description="Minutos hasta el próximo refresco programado")
    pollutants: list[str] = Field(default_factory=list)
